"""Token-Anmeldung der mobilen API (JWT, HS256) und Sperre nach Fehlversuchen.

Die Sperre gilt für die Kombination aus Benutzername und IP-Adresse (nicht nur
je Benutzername), damit niemand durch gezielte Fehlversuche ein fremdes Konto
sperren kann.
"""

import functools
import json
import time
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import LoginVersuch

MAX_FEHLVERSUCHE = 5
SPERRFENSTER_MINUTEN = 15
User = get_user_model()


def erfolg(daten, status=200):
    return JsonResponse({"success": True, "data": daten}, status=status, json_dumps_params={"ensure_ascii": False})


def fehler(meldung, status=400):
    return JsonResponse({"success": False, "error": meldung}, status=status, json_dumps_params={"ensure_ascii": False})


def token_erzeugen(user) -> tuple[str, int]:
    gueltig = settings.API_TOKEN_GUELTIGKEIT_TAGE * 86400
    jetzt = int(time.time())
    nutzlast = {"sub": str(user.pk), "username": user.get_username(), "iat": jetzt, "exp": jetzt + gueltig}
    return jwt.encode(nutzlast, settings.API_TOKEN_SCHLUESSEL, algorithm="HS256"), gueltig


def benutzer_aus_token(token: str):
    """Gültiger, aktiver Benutzer zum Token oder ``None``."""
    try:
        nutzlast = jwt.decode(token, settings.API_TOKEN_SCHLUESSEL, algorithms=["HS256"], options={"require": ["exp", "sub"]})
        return User.objects.filter(pk=int(nutzlast["sub"]), is_active=True).first()
    except (jwt.PyJWTError, ValueError):
        return None


def client_ip(request) -> str:
    return request.META.get("REMOTE_ADDR", "unbekannt")


def ist_gesperrt(benutzername: str, ip: str) -> bool:
    seit = timezone.now() - timedelta(minutes=SPERRFENSTER_MINUTEN)
    anzahl = LoginVersuch.objects.filter(benutzername=benutzername, ip_adresse=ip, erfolg=False, zeitpunkt__gt=seit).count()
    return anzahl >= MAX_FEHLVERSUCHE


def versuch_protokollieren(benutzername: str, ip: str, erfolgreich: bool) -> None:
    LoginVersuch.objects.create(benutzername=benutzername, ip_adresse=ip, erfolg=erfolgreich)
    LoginVersuch.objects.filter(zeitpunkt__lt=timezone.now() - timedelta(days=1)).delete()


def json_koerper(request) -> dict:
    if not request.body:
        return {}
    try:
        daten = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        raise ApiFehler("Ungültiges JSON im Request-Body.", 400)
    if not isinstance(daten, dict):
        raise ApiFehler("Der Request-Body muss ein JSON-Objekt sein.", 400)
    return daten


class ApiFehler(Exception):
    def __init__(self, meldung, status=400):
        super().__init__(meldung)
        self.meldung, self.status = meldung, status


def api_ansicht(*, methoden, rechte=()):
    """Dekorator: Methodenprüfung, Token, Modulrechte und Lizenz; einheitliche JSON-Fehler.

    ``rechte``: Paare (modul, aktion), z. B. ``(("auftraege", "lesen"),)``.
    ``methoden`` darf auch ein Dict {Methode: rechte} sein, wenn GET und POST verschiedene Rechte brauchen.
    """

    def dekorator(funktion):
        @csrf_exempt
        @functools.wraps(funktion)
        def huelle(request, *args, **kwargs):
            erlaubt = methoden if isinstance(methoden, dict) else {m: rechte for m in methoden}
            if request.method not in erlaubt:
                return fehler("Methode nicht erlaubt.", 405)
            kopf = request.META.get("HTTP_AUTHORIZATION", "")
            if not kopf.lower().startswith("bearer "):
                return fehler("Kein Authentifizierungs-Token übermittelt.", 401)
            user = benutzer_aus_token(kopf[7:].strip())
            if user is None:
                return fehler("Token ungültig oder abgelaufen.", 401)
            from accounts.modules import LIZENZ_MODUL

            for modul, aktion in erlaubt[request.method]:
                if not user.hat_modulrecht(modul, aktion):
                    return fehler("Zugriff verweigert: Es fehlt die Berechtigung für dieses Modul.", 403)
                lizenzmodul = LIZENZ_MODUL.get(modul)
                if lizenzmodul and settings.LIZENZ_PRUEFUNG:
                    from einstellungen.lizenzen import modul_lizenziert, modulname

                    if not modul_lizenziert(lizenzmodul):
                        return fehler(f"Für das Modul {modulname(lizenzmodul)} liegt keine gültige Lizenz vor.", 402)
            request.user = user
            try:
                return funktion(request, *args, **kwargs)
            except ApiFehler as f:
                return fehler(f.meldung, f.status)

        return huelle

    return dekorator


@csrf_exempt
def anmelden(request):
    """POST {"username", "password"} -> Token. Nutzt dieselbe Prüfung wie die Weboberfläche (inkl. LDAP)."""
    if request.method != "POST":
        return fehler("Nur POST erlaubt.", 405)
    try:
        daten = json_koerper(request)
    except ApiFehler as f:
        return fehler(f.meldung, f.status)
    benutzername = str(daten.get("username", "")).strip()
    passwort = daten.get("password", "")
    if not benutzername or not passwort or not isinstance(passwort, str):
        return fehler("Benutzername und Passwort erforderlich.", 400)
    ip = client_ip(request)
    if ist_gesperrt(benutzername, ip):
        return fehler(f"Zu viele Fehlversuche. Bitte in {SPERRFENSTER_MINUTEN} Minuten erneut versuchen.", 429)
    user = authenticate(request, username=benutzername, password=passwort)
    versuch_protokollieren(benutzername, ip, user is not None)
    if user is None:
        return fehler("Benutzername oder Passwort ist falsch.", 401)
    token, gueltig = token_erzeugen(user)
    return erfolg({
        "token": token, "expires_in": gueltig,
        "user": {"id": user.pk, "username": user.get_username(), "name": user.anzeigename, "admin": user.ist_admin},
    })
