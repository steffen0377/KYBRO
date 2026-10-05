from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils import timezone

from core.forms import BootstrapFormMixin, suchauswahl
from einstellungen.models import Firma
from stammdaten.models import Artikel, Kunde

from .models import (
    Angebot,
    AngebotPosition,
    Rechnung,
    RechnungPosition,
)


class DatumWidget(forms.DateInput):
    input_type = "date"

    def __init__(self, **kwargs):
        super().__init__(format="%Y-%m-%d", **kwargs)


class _KopfForm(BootstrapFormMixin, forms.ModelForm):
    kunde = forms.ModelChoiceField(queryset=Kunde.objects.all(), label="Kunde", empty_label="Kunde wählen…")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kunde"].label_from_instance = lambda k: k.anzeigename
        suchauswahl(self.fields["kunde"], "kunde")
        # Kunden mit Steuerbefreiung markieren, damit das Formular die MwSt. auf 0 setzen kann.
        self.steuerbefreite_kunden = list(
            Kunde.objects.filter(steuerbefreit=True).values_list("pk", flat=True)
        )


class AngebotForm(_KopfForm):
    class Meta:
        model = Angebot
        fields = ["kunde", "datum", "gueltig_bis", "notizen"]
        widgets = {"datum": DatumWidget(), "gueltig_bis": DatumWidget(), "notizen": forms.Textarea(attrs={"rows": 2})}


class RechnungForm(_KopfForm):
    class Meta:
        model = Rechnung
        fields = ["kunde", "datum", "leistungsdatum", "faellig_am", "notizen"]
        widgets = {
            "datum": DatumWidget(), "leistungsdatum": DatumWidget(), "faellig_am": DatumWidget(),
            "notizen": forms.Textarea(attrs={"rows": 2}),
        }


class PositionForm(BootstrapFormMixin, forms.ModelForm):
    """Eine Belegposition. Eine Zeile ohne Artikel und ohne Beschreibung gilt als leer."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        artikel = Artikel.objects.filter(aktiv=True)
        if self.instance.pk and self.instance.artikel_id:
            artikel = Artikel.objects.filter(aktiv=True) | Artikel.objects.filter(pk=self.instance.artikel_id)
        self.fields["artikel"].queryset = artikel.order_by("name")
        self.fields["artikel"].empty_label = "— manuell —"
        suchauswahl(self.fields["artikel"], "artikel")
        self.fields["beschreibung"].required = False
        self.fields["artikel"].widget.attrs["class"] += " artikel-wahl"
        self.fields["beschreibung"].widget.attrs["class"] += " feld-beschreibung"
        self.fields["menge"].widget.attrs["class"] += " feld-menge"
        self.fields["einzelpreis"].widget.attrs["class"] += " feld-preis"
        self.fields["rabatt"].widget.attrs["class"] += " feld-rabatt"
        self.fields["steuersatz"].widget.attrs["class"] += " feld-steuer"
        self.fields["abrechnung"].widget.attrs["class"] += " feld-abrechnung"
        if not self.instance.pk:
            self.fields["steuersatz"].initial = Firma.holen().standard_steuersatz

    def has_changed(self):
        daten = self.data.get(self.add_prefix("beschreibung"), "").strip()
        wahl = self.data.get(self.add_prefix("artikel"), "")
        if not self.instance.pk and not daten and not wahl:
            return False
        return super().has_changed()

    def clean(self):
        daten = super().clean()
        artikel = daten.get("artikel")
        if not (daten.get("beschreibung") or "").strip():
            if artikel:
                daten["beschreibung"] = artikel.name
            else:
                self.add_error("beschreibung", "Bitte eine Beschreibung angeben.")
        option = daten.get("preisoption")
        if option:
            if artikel is None or option.artikel_id != artikel.pk:
                self.add_error("preisoption", "Das Preismodell gehört nicht zum gewählten Artikel.")
            elif daten.get("abrechnung") != option.abrechnung:
                self.add_error("abrechnung", "Modell und Preisoption passen nicht zusammen.")
        elif daten.get("abrechnung") and daten.get("abrechnung") != "einmalig" and artikel is None:
            self.add_error("abrechnung", "Abo-Modelle gibt es nur für Artikel.")
        return daten

    def save(self, commit=True):
        position = super().save(commit=False)
        if position.artikel_id:
            position.artikelnummer = position.artikel.artikelnummer
            position.einheit = position.artikel.einheit
        else:
            position.artikelnummer = ""
        if commit:
            position.save()
        return position


class BasePositionFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        vorhanden = [
            f for f in self.forms
            if f.cleaned_data and not f.cleaned_data.get("DELETE") and f.cleaned_data.get("beschreibung")
        ]
        if not vorhanden:
            raise forms.ValidationError("Bitte mindestens eine Position angeben.")

    def speichern(self, kunde):
        """Speichert die Positionen. Bei steuerbefreiten Kunden wird die MwSt. immer auf 0 gesetzt
        (nicht über manipulierte Anfragen zu umgehen)."""
        instanzen = self.save(commit=False)
        for geloescht in self.deleted_objects:
            geloescht.delete()
        for position in instanzen:
            if kunde.steuerbefreit:
                position.steuersatz = 0
            position.save()
        if kunde.steuerbefreit:
            self.instance.positionen.exclude(steuersatz=0).update(steuersatz=0)
        return instanzen


def positionen_formset(beleg_modell, positionsmodell):
    return inlineformset_factory(
        beleg_modell, positionsmodell, form=PositionForm, formset=BasePositionFormSet, extra=1, can_delete=True,
        fields=["artikel", "beschreibung", "menge", "einzelpreis", "rabatt", "steuersatz", "abrechnung", "preisoption"],
        widgets={"preisoption": forms.HiddenInput},
    )


AngebotPositionenFormSet = positionen_formset(Angebot, AngebotPosition)
RechnungPositionenFormSet = positionen_formset(Rechnung, RechnungPosition)


class StatusForm(forms.Form):
    status = forms.ChoiceField(label="Status")

    def __init__(self, choices, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = choices
        self.fields["status"].widget.attrs["class"] = "form-select"
