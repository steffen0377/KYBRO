"""Anmeldeverfahren: lokal, LDAP oder Kombinationen (Einstellung unter Einstellungen > Authentifizierung).

Bei "Nur LDAP" und nicht erreichbarem Server dürfen sich lokale Administratoren
als Notfallzugang anmelden, damit die Einstellung korrigiert werden kann.
Der Ausfall wird protokolliert.
"""

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from einstellungen.models import Authentifizierung

from . import ldap

log = logging.getLogger(__name__)
User = get_user_model()


class AnmeldeBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if not username or password is None:
            return None
        modus = Authentifizierung.holen().modus
        M = Authentifizierung.Modus
        if modus == M.LDAP:
            return self._nur_ldap(request, username, password)
        if modus == M.LDAP_DANN_LOKAL:
            return self._ldap(request, username, password) or self._lokal(request, username, password)
        if modus == M.LOKAL_DANN_LDAP:
            return self._lokal(request, username, password) or self._ldap(request, username, password)
        return self._lokal(request, username, password)

    def _lokal(self, request, username, password, nur_admin=False):
        benutzer = super().authenticate(request, username=username, password=password)
        if benutzer and nur_admin and not benutzer.is_superuser:
            return None
        return benutzer

    def _ldap(self, request, username, password):
        """LDAP-Anmeldung; ``None`` bei falschen Zugangsdaten oder Ausfall."""
        try:
            return self._ldap_pruefen(username, password)
        except ldap.LdapNichtErreichbar:
            return None

    def _ldap_pruefen(self, username, password):
        daten = ldap.anmelden(username, password)
        if daten is None:
            return None
        benutzer = User.objects.filter(username=username).first()
        if benutzer is None:
            benutzer = User(username=username, auth_source=User.Quelle.LDAP)
            benutzer.set_unusable_password()
        elif not benutzer.is_active:
            return None
        else:
            benutzer.auth_source = User.Quelle.LDAP
        vorname, _, nachname = daten.anzeigename.partition(" ")
        benutzer.first_name, benutzer.last_name = vorname[:150], nachname[:150]
        if daten.email:
            benutzer.email = daten.email
        benutzer.save()
        return benutzer

    def _nur_ldap(self, request, username, password):
        try:
            return self._ldap_pruefen(username, password)
        except ldap.LdapNichtErreichbar as fehler:
            notfall = self._lokal(request, username, password, nur_admin=True)
            log.error(
                "[LDAP] Server nicht erreichbar bei Anmeldung von %r (%s). Notfallzugang: %s",
                username, fehler, "genutzt" if notfall else "nicht möglich",
            )
            if notfall:
                if request is not None:
                    messages.warning(
                        request,
                        "Achtung: Der LDAP-Server war nicht erreichbar. Sie wurden über das lokale "
                        "Administratorkonto als Notfallzugang angemeldet.",
                    )
                return notfall
            if request is not None:
                request.ldap_nicht_erreichbar = True
            return None
