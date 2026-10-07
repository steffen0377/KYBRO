import datetime

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from core.forms import BootstrapFormMixin, suchauswahl

from .kalender import BUNDESLAENDER, Kalender
from .models import WOCHENTAGE, Anwesenheit, Mitarbeiter, PersonalEinstellung, Sondertag, Stundenkorrektur, Urlaubsantrag, Urlaubsjahr, Vertrag
from .services import ist_arbeitstag, tage_zwischen

DATUM = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
ZEIT = forms.TimeInput(attrs={"type": "time"}, format="%H:%M")


class MitarbeiterForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Mitarbeiter
        fields = [
            "vorname", "nachname", "geburtsdatum", "strasse", "plz", "ort", "telefon", "email",
            "position", "abteilung", "eintrittsdatum", "austrittsdatum",
            "notfallkontakt_name", "notfallkontakt_telefon", "benutzer", "notizen",
        ]
        widgets = {
            "geburtsdatum": DATUM, "eintrittsdatum": DATUM, "austrittsdatum": DATUM,
            "notizen": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        benutzer = get_user_model().objects.filter(is_active=True)
        frei = Q(mitarbeiter__isnull=True)
        if self.instance.pk and self.instance.benutzer_id:
            frei |= Q(pk=self.instance.benutzer_id)
        self.fields["benutzer"].queryset = benutzer.filter(frei).order_by("username")
        self.fields["benutzer"].label_from_instance = lambda u: f"{u.anzeigename} ({u.username})"
        self.fields["benutzer"].empty_label = "— kein Login verknüpft —"
        suchauswahl(self.fields["benutzer"])


class VertragForm(BootstrapFormMixin, forms.ModelForm):
    arbeitstage = forms.MultipleChoiceField(
        label="Arbeitstage", choices=WOCHENTAGE, widget=forms.CheckboxSelectMultiple, initial=[0, 1, 2, 3, 4],
    )

    class Meta:
        model = Vertrag
        fields = [
            "gueltig_ab", "gueltig_bis", "art", "wochenstunden", "arbeitstage", "urlaubstage_pro_jahr",
            "probezeit_ende", "befristet_bis", "kuendigungsfrist", "notizen",
        ]
        widgets = {
            "gueltig_ab": DATUM, "gueltig_bis": DATUM, "probezeit_ende": DATUM, "befristet_bis": DATUM,
            "notizen": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, mitarbeiter=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.mitarbeiter = mitarbeiter or self.instance.mitarbeiter
        if self.instance.pk:
            self.initial["arbeitstage"] = [str(t) for t in self.instance.arbeitstage_liste]
        self.fields["urlaubstage_pro_jahr"].localize = True

    def clean_arbeitstage(self):
        tage = sorted(int(t) for t in self.cleaned_data["arbeitstage"])
        if not tage:
            raise forms.ValidationError("Mindestens ein Arbeitstag ist nötig.")
        return ",".join(str(t) for t in tage)


class UrlaubsjahrForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Urlaubsjahr
        fields = ["anspruch", "uebertrag", "notiz"]


class UrlaubsantragForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Urlaubsantrag
        fields = ["mitarbeiter", "von", "bis", "bemerkung"]
        widgets = {"von": DATUM, "bis": DATUM}

    def __init__(self, *args, mitarbeiter=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Überschneidungen mit vorhandenem Urlaub löst die View durch Aufteilen des Antrags.
        self.instance.ueberschneidung_pruefen = False
        if mitarbeiter:
            del self.fields["mitarbeiter"]
            self.instance.mitarbeiter = mitarbeiter
        else:
            self.fields["mitarbeiter"].queryset = Mitarbeiter.objects.filter(
                Q(austrittsdatum__isnull=True) | Q(austrittsdatum__gte=datetime.date.today())
            )
            suchauswahl(self.fields["mitarbeiter"])


class StundenkorrekturForm(BootstrapFormMixin, forms.ModelForm):
    stunden = forms.DecimalField(
        label="Stunden", max_digits=6, decimal_places=2, localize=True,
        help_text=Stundenkorrektur._meta.get_field("stunden").help_text,
    )

    class Meta:
        model = Stundenkorrektur
        fields = ["mitarbeiter", "datum", "stunden", "bemerkung"]
        widgets = {"datum": DATUM}

    def __init__(self, *args, mitarbeiter=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["datum"].initial = datetime.date.today
        self.fields["bemerkung"].required = True
        if mitarbeiter:
            del self.fields["mitarbeiter"]
            self.instance.mitarbeiter = mitarbeiter
        else:
            self.fields["mitarbeiter"].queryset = Mitarbeiter.objects.filter(
                Q(austrittsdatum__isnull=True) | Q(austrittsdatum__gte=datetime.date.today())
            )
            suchauswahl(self.fields["mitarbeiter"])

    def clean_stunden(self):
        stunden = self.cleaned_data["stunden"]
        if stunden == 0:
            raise forms.ValidationError("Bitte eine Stundenzahl ungleich 0 angeben.")
        return stunden


class AnwesenheitForm(BootstrapFormMixin, forms.Form):
    mitarbeiter = forms.ModelChoiceField(Mitarbeiter.objects.all(), label="Mitarbeiter")
    datum = forms.DateField(label="Datum (von)", widget=DATUM, initial=datetime.date.today)
    datum_bis = forms.DateField(
        label="Datum (bis)", widget=DATUM, required=False,
        help_text="Optional: mehrere Tage auf einmal eintragen (nur Arbeitstage).",
    )
    status = forms.ChoiceField(label="Status", choices=Anwesenheit.Status.choices)
    von = forms.TimeField(label="Kommen", widget=ZEIT, required=False)
    bis = forms.TimeField(label="Gehen", widget=ZEIT, required=False)
    notiz = forms.CharField(label="Notiz", max_length=200, required=False)
    entfernen = forms.BooleanField(label="Eintrag entfernen", required=False)

    def __init__(self, *args, mitarbeiter=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fixiert = mitarbeiter
        if mitarbeiter:
            del self.fields["mitarbeiter"]
        else:
            suchauswahl(self.fields["mitarbeiter"])

    def clean(self):
        daten = super().clean()
        if daten.get("datum") and daten.get("datum_bis"):
            if daten["datum_bis"] < daten["datum"]:
                self.add_error("datum_bis", "Das Ende liegt vor dem Beginn.")
            elif (daten["datum_bis"] - daten["datum"]).days > 92:
                self.add_error("datum_bis", "Bitte höchstens drei Monate auf einmal eintragen.")
        if daten.get("von") and daten.get("bis") and daten["bis"] <= daten["von"]:
            self.add_error("bis", "Gehen muss nach Kommen liegen.")
        return daten

    def speichern(self) -> int:
        d = self.cleaned_data
        m = self.fixiert or d["mitarbeiter"]
        ende = d.get("datum_bis") or d["datum"]
        vertraege = list(m.vertraege.all())
        kalender = Kalender()
        # Bei Zeiträumen werden freie Tage und Feiertage übersprungen; ein einzelner Tag wird immer eingetragen.
        tage = [
            t for t in tage_zwischen(d["datum"], ende)
            if ende == d["datum"] or (ist_arbeitstag(vertraege, t) and kalender.anteil(t) > 0)
        ]
        for t in tage:
            if d["entfernen"]:
                Anwesenheit.objects.filter(mitarbeiter=m, datum=t).delete()
            else:
                Anwesenheit.objects.update_or_create(
                    mitarbeiter=m, datum=t,
                    defaults={"status": d["status"], "von": d.get("von"), "bis": d.get("bis"), "notiz": d.get("notiz", "")},
                )
        return len(tage)


class PersonalEinstellungForm(BootstrapFormMixin, forms.ModelForm):
    bundesland = forms.ChoiceField(
        label="Bundesland", required=False, choices=[("", "— keine gesetzlichen Feiertage —")] + BUNDESLAENDER,
        help_text="Bestimmt die gesetzlichen Feiertage für Urlaubsberechnung und Anwesenheitsübersicht.",
    )

    class Meta:
        model = PersonalEinstellung
        fields = ["bundesland"]


class SondertagForm(BootstrapFormMixin, forms.ModelForm):
    urlaubsanteil = forms.TypedChoiceField(
        label="Art", choices=[("0", "Feiertag (kein Urlaubstag)"), ("0.5", "Halber Tag (0,5 Urlaubstage)")],
        coerce=lambda w: __import__("decimal").Decimal(w),
    )

    class Meta:
        model = Sondertag
        fields = ["name", "tag", "monat", "jahr", "urlaubsanteil"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["urlaubsanteil"] = "0.5" if self.instance.urlaubsanteil else "0"
