from django import forms
from django.forms import inlineformset_factory

from core.forms import BootstrapFormMixin, suchauswahl

from .models import (
    Ansprechpartner,
    Artikel,
    ArtikelLieferant,
    Kategorie,
    Kunde,
    Lieferant,
    Preisoption,
    Sonderpreis,
)


class KategorieForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Kategorie
        fields = ["name", "uebergeordnet"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["uebergeordnet"].empty_label = "— keine (Hauptkategorie) —"
        suchauswahl(self.fields["uebergeordnet"], "kategorie")
        if self.instance.pk:
            ausgeschlossen = self.instance.nachfahren_ids() | {self.instance.pk}
            self.fields["uebergeordnet"].queryset = Kategorie.objects.exclude(pk__in=ausgeschlossen)


class ArtikelForm(BootstrapFormMixin, forms.ModelForm):
    anfangsbestand = forms.DecimalField(
        label="Anfangsbestand", required=False, max_digits=10, decimal_places=2, initial=0
    )

    class Meta:
        model = Artikel
        fields = [
            "ean", "han", "name", "beschreibung", "einheit", "einkaufspreis",
            "verkaufspreis", "steuersatz", "lagerfuehrung", "mindestbestand",
            "seriennummern", "kategorien", "aktiv",
        ]
        widgets = {
            "beschreibung": forms.Textarea(attrs={"rows": 2}),
            "kategorien": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            del self.fields["anfangsbestand"]
        self.fields["ean"].widget.attrs["placeholder"] = "z. B. 4006381333931"

    def clean_ean(self):
        return (self.cleaned_data.get("ean") or "").strip() or None

    def clean_einheit(self):
        return (self.cleaned_data.get("einheit") or "").strip() or "Stk."

    def clean(self):
        daten = super().clean()
        # Ohne Lagerführung gibt es weder Seriennummern noch Anfangsbestand.
        if not daten.get("lagerfuehrung"):
            daten["seriennummern"] = False
            self.instance.seriennummern = False
            if "anfangsbestand" in self.fields:
                daten["anfangsbestand"] = 0
        return daten


class _ZeilenForm(BootstrapFormMixin, forms.ModelForm):
    pass


class ArtikelLieferantForm(_ZeilenForm):
    class Meta:
        model = ArtikelLieferant
        fields = ["lieferant", "lieferanten_artikelnummer", "hek"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        suchauswahl(self.fields["lieferant"], "lieferant")


class SonderpreisForm(_ZeilenForm):
    class Meta:
        model = Sonderpreis
        fields = ["kunde", "art", "wert", "aktiv"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        suchauswahl(self.fields["kunde"], "kunde")


class PreisoptionForm(_ZeilenForm):
    class Meta:
        model = Preisoption
        fields = ["abrechnung", "preis", "mindestlaufzeit_monate", "kuendigungsfrist_tage", "aktiv"]


def _formset(model, form, **kwargs):
    return inlineformset_factory(Artikel, model, form=form, extra=1, can_delete=True, **kwargs)


LieferantenFormSet = _formset(ArtikelLieferant, ArtikelLieferantForm)
SonderpreisFormSet = _formset(Sonderpreis, SonderpreisForm)
PreisoptionFormSet = _formset(Preisoption, PreisoptionForm)


class KundeForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Kunde
        fields = [
            "firma", "vorname", "nachname", "strasse", "plz", "ort", "land", "email",
            "telefon", "steuernummer", "ust_id", "zahlungsart", "steuerbefreit",
            "befreiungsgrund", "notizen", "iban", "bic", "bank",
        ]
        widgets = {"notizen": forms.Textarea(attrs={"rows": 2})}


class AnsprechpartnerForm(_ZeilenForm):
    class Meta:
        model = Ansprechpartner
        fields = ["nachname", "vorname", "firma", "telefon", "email"]


AnsprechpartnerFormSet = inlineformset_factory(
    Kunde, Ansprechpartner, form=AnsprechpartnerForm, extra=1, can_delete=True
)


class LieferantForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Lieferant
        fields = [
            "firma", "vorname", "nachname", "strasse", "plz", "ort", "land", "email",
            "telefon", "steuernummer", "kundennummer_beim_lieferanten", "zahlungsart", "notizen",
        ]
        widgets = {"notizen": forms.Textarea(attrs={"rows": 2})}
