"""Mini-Formulare für Overlays: Kunde, Artikel, Lieferant und Kategorie direkt aus Auswahlfeldern anlegen/ändern.

Das Auswahlfeld (``core/static/core/js/auswahl.js``) lädt das Formular als HTML-Ausschnitt in einen Dialog und sendet
es per ``fetch`` ab. Bei Erfolg antwortet der Server mit JSON ``{ok, id, label, daten}``, bei Fehlern mit dem
Formular samt Fehlermeldungen (Status 422).
"""

from django import forms
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views import View

from accounts.mixins import ModulRechtMixin
from core.forms import BootstrapFormMixin

from .models import Artikel, Kategorie, Kunde, Lieferant


class KundeSchnellForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Kunde
        fields = ["firma", "vorname", "nachname", "strasse", "plz", "ort", "email", "telefon",
                  "steuerbefreit", "befreiungsgrund"]


class LieferantSchnellForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Lieferant
        fields = ["firma", "vorname", "nachname", "strasse", "plz", "ort", "email", "telefon"]


class ArtikelSchnellForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Artikel
        fields = ["name", "einheit", "verkaufspreis", "einkaufspreis", "steuersatz", "lagerfuehrung"]


class KategorieSchnellForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Kategorie
        fields = ["name", "uebergeordnet"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["uebergeordnet"].empty_label = "— keine (Hauptkategorie) —"
        if self.instance.pk:
            ausgeschlossen = self.instance.nachfahren_ids() | {self.instance.pk}
            self.fields["uebergeordnet"].queryset = Kategorie.objects.exclude(pk__in=ausgeschlossen)


def artikel_formulardaten(artikel: Artikel) -> dict:
    """Artikeldaten für die Positionsformulare der Belege (siehe ``beleg_form.js``)."""
    return {
        "id": artikel.pk,
        "name": artikel.name,
        "preis": float(artikel.verkaufspreis),
        "steuersatz": float(artikel.steuersatz),
        "optionen": [
            {"id": o.pk, "abrechnung": o.abrechnung, "preis": float(o.preis)}
            for o in artikel.preisoptionen.all() if o.aktiv
        ],
    }


def _kunde_daten(kunde: Kunde) -> dict:
    return {"id": kunde.pk, "steuerbefreit": kunde.steuerbefreit}


# art -> (Modell, Formular, Rechtemodul, Titel, Funktion für zusätzliche Daten)
ARTEN = {
    "kunde": (Kunde, KundeSchnellForm, "kunden", "Kunde", _kunde_daten),
    "artikel": (Artikel, ArtikelSchnellForm, "artikel", "Artikel", artikel_formulardaten),
    "lieferant": (Lieferant, LieferantSchnellForm, "lieferanten", "Lieferant", None),
    "kategorie": (Kategorie, KategorieSchnellForm, "kategorien", "Kategorie", None),
}


class SchnellFormularView(ModulRechtMixin, View):
    """GET: Formular als HTML-Ausschnitt. POST: speichern und JSON zurückgeben."""

    def _art(self):
        try:
            return ARTEN[self.kwargs["art"]]
        except KeyError:
            raise Http404("Unbekannte Art.")

    def get_modul(self) -> str:
        return self._art()[2]

    def get_aktion(self) -> str:
        return "schreiben"  # schon das Formular selbst dient zum Anlegen/Ändern

    def _formular(self, daten=None):
        modell, formklasse, _modul, titel, _extra = self._art()
        pk = self.kwargs.get("pk")
        objekt = get_object_or_404(modell, pk=pk) if pk else None
        return formklasse(daten, instance=objekt), titel, objekt

    def _anzeigen(self, request, form, titel, objekt, status=200):
        return render(request, "stammdaten/schnell_form.html", {
            "form": form, "titel": f"{titel} {'bearbeiten' if objekt else 'anlegen'}",
            "art": self.kwargs["art"], "objekt": objekt,
        }, status=status)

    def get(self, request, *args, **kwargs):
        form, titel, objekt = self._formular()
        return self._anzeigen(request, form, titel, objekt)

    def post(self, request, *args, **kwargs):
        form, titel, objekt = self._formular(request.POST)
        if not form.is_valid():
            return self._anzeigen(request, form, titel, objekt, status=422)
        gespeichert = form.save()
        extra = self._art()[4]
        return JsonResponse({
            "ok": True, "id": gespeichert.pk, "label": str(gespeichert),
            "daten": extra(gespeichert) if extra else {},
        })
