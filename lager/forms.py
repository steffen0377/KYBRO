from django import forms

from core.forms import BootstrapFormMixin
from stammdaten.models import Artikel

from .services import seriennummern_aus_text


def _lagerartikel(mit_seriennummern: bool):
    return Artikel.objects.filter(
        aktiv=True, lagerfuehrung=True, seriennummern=mit_seriennummern
    ).order_by("name")


class _ArtikelWahl(BootstrapFormMixin, forms.Form):
    mit_seriennummern = False

    artikel = forms.ModelChoiceField(queryset=Artikel.objects.none(), label="Artikel", empty_label="Artikel wählen…")
    notiz = forms.CharField(label="Notiz", max_length=255, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["artikel"].queryset = _lagerartikel(self.mit_seriennummern)
        self.fields["notiz"].widget.attrs["placeholder"] = "Notiz (optional)"


class WareneingangForm(_ArtikelWahl):
    menge = forms.DecimalField(label="Menge", max_digits=10, decimal_places=2, min_value=0.01)
    field_order = ["artikel", "menge", "notiz"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["menge"].widget.attrs["placeholder"] = "Menge"


class KorrekturForm(_ArtikelWahl):
    neuer_bestand = forms.DecimalField(label="Neuer Ist-Bestand", max_digits=10, decimal_places=2, min_value=0)
    field_order = ["artikel", "neuer_bestand", "notiz"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["neuer_bestand"].widget.attrs["placeholder"] = "Neuer Ist-Bestand"


class SeriellEinlagernForm(_ArtikelWahl):
    mit_seriennummern = True

    seriennummern = forms.CharField(
        label="Seriennummern",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Eine Seriennummer pro Zeile"}),
        help_text="Die Anzahl der Zeilen ergibt automatisch die eingelagerte Menge.",
    )
    field_order = ["artikel", "seriennummern", "notiz"]

    def clean_seriennummern(self):
        nummern = seriennummern_aus_text(self.cleaned_data["seriennummern"])
        if not nummern:
            raise forms.ValidationError("Bitte mindestens eine Seriennummer angeben (eine pro Zeile).")
        return nummern
