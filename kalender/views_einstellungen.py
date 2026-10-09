"""Einstellungen → Kalender: Verbindung zu einem CalDAV-Server, Zuordnung der Kalender und manueller Abgleich."""

from django import forms
from django.contrib import messages
from django.shortcuts import redirect
from django.views.generic import TemplateView

from core.forms import BootstrapFormMixin
from einstellungen.views import EinstellungenMixin

from . import abgleich, quellen
from .caldav import CalDavFehler
from .models import CalDavVerbindung, Zuordnung

SESSION_SCHLUESSEL = "caldav_kalender"


class CalDavForm(BootstrapFormMixin, forms.ModelForm):
    passwort = forms.CharField(
        label="Passwort", required=False, widget=forms.PasswordInput(render_value=False),
        help_text="Leer lassen, um das gespeicherte Passwort beizubehalten. Bei Nextcloud ein App-Passwort des Dienstkontos verwenden.",
    )

    class Meta:
        model = CalDavVerbindung
        fields = ["aktiv", "url", "benutzer", "passwort", "tls_pruefen"]

    def clean_passwort(self):
        return self.cleaned_data["passwort"] or self.instance.passwort


def _einzeilig(text: str) -> str:
    return " – ".join(zeile for zeile in text.splitlines() if zeile)


class CalDavView(EinstellungenMixin, TemplateView):
    register = "kalender"
    seitentitel = "Einstellungen"
    template_name = "kalender/caldav.html"

    # --- Anzeige ---------------------------------------------------------------------------

    def get_context_data(self, form=None, **kwargs):
        kontext = super().get_context_data(**kwargs)
        verbindung = CalDavVerbindung.holen()
        zugeordnet = {z.quelle: z for z in Zuordnung.objects.all()}
        entdeckt = self.request.session.get(SESSION_SCHLUESSEL, [])
        zeilen = []
        for q in quellen.alle_quellen():
            z = zugeordnet.get(q.schluessel)
            optionen = list(entdeckt)
            if z and z.ziel_url not in {o["url"] for o in optionen}:
                optionen.append({"url": z.ziel_url, "name": z.ziel_name or z.ziel_url})
            zeilen.append({"quelle": q, "ziel": z.ziel_url if z else "", "optionen": optionen})
        kontext.update(
            form=form or CalDavForm(instance=verbindung), verbindung=verbindung, zeilen=zeilen, entdeckt=bool(entdeckt),
            titel="CalDAV-Anbindung (Nextcloud, Radicale u. a.)",
        )
        return kontext

    # --- Aktionen --------------------------------------------------------------------------

    def post(self, request, *args, **kwargs):
        aktion = request.POST.get("aktion", "speichern")
        if aktion in ("speichern", "testen"):
            return self._verbindung(request, aktion == "testen")
        if aktion == "zuordnung":
            return self._zuordnung(request)
        if aktion == "abgleichen":
            return self._abgleichen(request)
        return redirect("einstellungen:kalender")

    def _verbindung(self, request, testen: bool):
        verbindung = CalDavVerbindung.holen()
        form = CalDavForm(request.POST, instance=verbindung)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        verbindung = form.save()
        if not testen:
            messages.success(request, "Einstellungen gespeichert.")
            return redirect("einstellungen:kalender")
        try:
            client = abgleich.client_fuer(verbindung)
            liste = client.kalender()
        except CalDavFehler as fehler:
            request.session.pop(SESSION_SCHLUESSEL, None)
            messages.error(request, f"Verbindung fehlgeschlagen: {fehler}")
        else:
            request.session[SESSION_SCHLUESSEL] = liste
            request.session["caldav_home"] = client.home
            messages.success(request, f"Verbindung in Ordnung. {len(liste)} Kalender gefunden.")
        return redirect("einstellungen:kalender")

    def _zuordnung(self, request):
        verbindung = CalDavVerbindung.holen()
        entdeckt = {o["url"]: o["name"] for o in request.session.get(SESSION_SCHLUESSEL, [])}
        bestehend = {z.quelle: z for z in Zuordnung.objects.all()}
        erlaubt = dict(entdeckt) | {z.ziel_url: z.ziel_name for z in bestehend.values()}
        auswahl, neu = {}, {}
        for q in quellen.alle_quellen():
            ziel = request.POST.get(f"ziel_{q.schluessel}", "")
            if ziel and ziel not in erlaubt:
                messages.error(request, f"Unbekannter Zielkalender für „{q.name}“. Bitte zuerst „Verbindung testen“.")
                return redirect("einstellungen:kalender")
            if ziel:
                auswahl[q.schluessel] = ziel
            name = request.POST.get(f"neu_{q.schluessel}", "").strip()
            if name and not ziel:
                neu[q.schluessel] = name
        if not verbindung.eingerichtet:
            messages.error(request, "Bitte zuerst die Verbindung einrichten und speichern.")
            return redirect("einstellungen:kalender")
        client = abgleich.client_fuer(verbindung)
        try:
            for schluessel, name in neu.items():  # neue Zielkalender auf dem Server anlegen
                client.home = request.session.get("caldav_home") or None
                angelegt = client.kalender_anlegen(name)
                auswahl[schluessel] = angelegt["url"]
                erlaubt[angelegt["url"]] = angelegt["name"]
                request.session.setdefault(SESSION_SCHLUESSEL, []).append(angelegt)
                request.session.modified = True
        except CalDavFehler as fehler:
            messages.error(request, f"Zielkalender konnte nicht angelegt werden: {fehler}")
            return redirect("einstellungen:kalender")
        ziele = list(auswahl.values())
        if len(ziele) != len(set(ziele)):
            messages.error(request, "Jeder Zielkalender darf nur einem KYBRO-Kalender zugeordnet werden.")
            return redirect("einstellungen:kalender")
        probleme = []
        for schluessel, z in bestehend.items():
            if auswahl.get(schluessel) != z.ziel_url:  # abgewählt oder geändert: alte Termine vom Server entfernen
                probleme += abgleich.zuordnung_entfernen(z, client)
        for schluessel, ziel in auswahl.items():
            Zuordnung.objects.update_or_create(quelle=schluessel, defaults={"ziel_url": ziel, "ziel_name": erlaubt.get(ziel, "")})
        messages.success(request, "Zuordnung gespeichert.")
        if probleme:
            messages.warning(request, "Einige alte Termine konnten nicht entfernt werden: " + "; ".join(probleme[:3]))
        return redirect("einstellungen:kalender")

    def _abgleichen(self, request):
        ergebnis = abgleich.abgleichen()
        (messages.error if ergebnis["fehler"] else messages.success)(request, "Abgleich: " + _einzeilig(ergebnis["text"]))
        return redirect("einstellungen:kalender")
