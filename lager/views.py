"""Lagerverwaltung: Übersicht, Wareneingang, Inventur und Seriennummern."""

from django.contrib import messages
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from accounts.mixins import ModulRechtMixin
from stammdaten.models import Artikel

from . import services
from .forms import KorrekturForm, SeriellEinlagernForm, WareneingangForm
from .models import Lagerbewegung, Seriennummer
from .services import LagerFehler

FORMULARE = {
    "wareneingang": WareneingangForm,
    "korrektur": KorrekturForm,
    "seriell": SeriellEinlagernForm,
}


class UebersichtView(ModulRechtMixin, TemplateView):
    modul = "lager"
    template_name = "lager/uebersicht.html"

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        for name, klasse in FORMULARE.items():
            kontext.setdefault(f"form_{name}", klasse())
        serien_artikel = Artikel.objects.filter(aktiv=True, lagerfuehrung=True, seriennummern=True).order_by("name")
        gewaehlt = self.request.GET.get("serien", "")
        artikel = serien_artikel.filter(pk=gewaehlt).first() if gewaehlt.isdigit() else None
        kontext.update(
            seitentitel="Lager",
            serien_artikel=serien_artikel,
            gewaehlter_artikel=artikel,
            seriennummern=Seriennummer.objects.filter(artikel=artikel) if artikel else [],
            bewegungen=Lagerbewegung.objects.select_related("artikel", "benutzer")[:100],
            unterbestand=Artikel.objects.filter(
                aktiv=True, lagerfuehrung=True, bestand__lte=F("mindestbestand")
            ).order_by("name")[:20],
        )
        return kontext


class AktionView(ModulRechtMixin, View):
    """Basis für die schreibenden Lageraktionen (nur POST)."""

    modul = "lager"
    http_method_names = ["post"]

    def zurueck(self, **abfrage):
        url = reverse("lager:uebersicht")
        if abfrage:
            url += "?" + "&".join(f"{k}={v}" for k, v in abfrage.items())
        return redirect(url)


class WareneingangView(AktionView):
    def post(self, request):
        form = WareneingangForm(request.POST)
        if form.is_valid():
            try:
                services.wareneingang(
                    form.cleaned_data["artikel"], form.cleaned_data["menge"],
                    form.cleaned_data["notiz"], request.user,
                )
                messages.success(request, "Wareneingang gebucht.")
            except LagerFehler as fehler:
                messages.error(request, str(fehler))
        else:
            messages.error(request, "Wareneingang nicht gebucht: bitte Artikel und Menge prüfen.")
        return self.zurueck()


class KorrekturView(AktionView):
    def post(self, request):
        form = KorrekturForm(request.POST)
        if form.is_valid():
            try:
                services.inventurkorrektur(
                    form.cleaned_data["artikel"], form.cleaned_data["neuer_bestand"],
                    form.cleaned_data["notiz"], request.user,
                )
                messages.success(request, "Bestand korrigiert.")
            except LagerFehler as fehler:
                messages.error(request, str(fehler))
        else:
            messages.error(request, "Korrektur nicht gespeichert: bitte Artikel und Bestand prüfen.")
        return self.zurueck()


class SeriellEinlagernView(AktionView):
    def post(self, request):
        form = SeriellEinlagernForm(request.POST)
        if not form.is_valid():
            messages.error(
                request, "Bitte Artikel wählen und mindestens eine Seriennummer angeben (eine pro Zeile)."
            )
            return self.zurueck()
        artikel = form.cleaned_data["artikel"]
        try:
            anzahl, doppelt = services.seriennummern_einlagern(
                artikel, form.cleaned_data["seriennummern"], form.cleaned_data["notiz"], request.user
            )
        except LagerFehler as fehler:
            messages.error(request, str(fehler))
            return self.zurueck()
        if doppelt:
            messages.error(request, "Bereits vorhandene Seriennummern übersprungen: " + ", ".join(doppelt))
        if anzahl:
            messages.success(request, f"{anzahl} Seriennummer(n) eingelagert.")
        return self.zurueck(serien=artikel.pk)


class SerieAktionView(AktionView):
    """Aktion auf einer einzelnen Seriennummer."""

    funktion = None
    erfolg = ""

    def post(self, request, pk):
        serie = get_object_or_404(Seriennummer, pk=pk)
        try:
            type(self).funktion(serie, request.user)
            messages.success(request, self.erfolg)
        except LagerFehler as fehler:
            messages.error(request, str(fehler))
        return self.zurueck(serien=serie.artikel_id)


class SerieDefektView(SerieAktionView):
    funktion = staticmethod(services.seriennummer_defekt)
    erfolg = "Seriennummer als defekt markiert und Bestand angepasst."


class SerieEntfernenView(SerieAktionView):
    funktion = staticmethod(services.seriennummer_entfernen)
    erfolg = "Seriennummer entfernt und Bestand angepasst."
