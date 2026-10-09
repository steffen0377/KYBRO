import datetime

from django import forms
from django.utils import timezone

from core.forms import BootstrapFormMixin

from .models import Kalender, Termin

DATUM = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
ZEIT = forms.TimeInput(attrs={"type": "time"}, format="%H:%M")


class KalenderForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Kalender
        fields = ["name", "farbe", "beschreibung"]
        widgets = {"farbe": forms.TextInput(attrs={"type": "color"})}


class TerminForm(BootstrapFormMixin, forms.ModelForm):
    beginn_datum = forms.DateField(label="Beginn", widget=DATUM)
    beginn_zeit = forms.TimeField(label="Uhrzeit", widget=ZEIT, required=False)
    ende_datum = forms.DateField(label="Ende", widget=DATUM)
    ende_zeit = forms.TimeField(label="Uhrzeit", widget=ZEIT, required=False)

    class Meta:
        model = Termin
        fields = ["kalender", "titel", "ort", "beschreibung", "ganztaegig"]
        widgets = {"beschreibung": forms.Textarea(attrs={"rows": 3})}
        help_texts = {"ganztaegig": "Bei ganztägigen Terminen zählen nur die Datumsangaben (Ende = letzter Tag)."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        t = self.instance
        if t.pk:
            beginn, ende = timezone.localtime(t.beginn), timezone.localtime(t.ende)
            self.initial.update(
                beginn_datum=beginn.date(), ende_datum=ende.date(),
                beginn_zeit=None if t.ganztaegig else beginn.time().replace(second=0, microsecond=0),
                ende_zeit=None if t.ganztaegig else ende.time().replace(second=0, microsecond=0),
            )
        self.fields["kalender"].empty_label = None
        # Zuerst Datum, dann Uhrzeit nebeneinander (Anordnung im Template)

    def clean(self):
        daten = super().clean()
        von, bis = daten.get("beginn_datum"), daten.get("ende_datum")
        if not von or not bis:
            return daten
        if daten.get("ganztaegig"):
            zeit_von = zeit_bis = datetime.time.min
        else:
            zeit_von, zeit_bis = daten.get("beginn_zeit"), daten.get("ende_zeit")
            if zeit_von is None:
                self.add_error("beginn_zeit", "Bitte eine Uhrzeit angeben (oder „Ganztägig“ ankreuzen).")
            if zeit_bis is None:
                self.add_error("ende_zeit", "Bitte eine Uhrzeit angeben (oder „Ganztägig“ ankreuzen).")
            if zeit_von is None or zeit_bis is None:
                return daten
        beginn = timezone.make_aware(datetime.datetime.combine(von, zeit_von))
        ende = timezone.make_aware(datetime.datetime.combine(bis, zeit_bis))
        if ende < beginn:
            self.add_error("ende_datum", "Das Ende liegt vor dem Beginn.")
        self.instance.beginn, self.instance.ende = beginn, ende
        return daten
