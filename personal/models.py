"""Personalverwaltung: Mitarbeiter, Verträge (mit Historie), Urlaub und Anwesenheit.

Mitarbeiter sind unabhängig von Benutzerkonten (LDAP oder lokal), können aber optional mit genau
einem Benutzer verknüpft werden. Verknüpfte Mitarbeiter sehen ihre eigenen Daten unter „Meine Zeiten“.
"""

import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
import uuid

WOCHENTAGE = [(0, "Mo"), (1, "Di"), (2, "Mi"), (3, "Do"), (4, "Fr"), (5, "Sa"), (6, "So")]


class Mitarbeiter(models.Model):
    personalnummer = models.CharField("Personalnummer", max_length=20, unique=True, editable=False)
    vorname = models.CharField("Vorname", max_length=100)
    nachname = models.CharField("Nachname", max_length=100)
    geburtsdatum = models.DateField("Geburtsdatum", null=True, blank=True)
    strasse = models.CharField("Straße", max_length=200, blank=True)
    plz = models.CharField("PLZ", max_length=10, blank=True)
    ort = models.CharField("Ort", max_length=100, blank=True)
    telefon = models.CharField("Telefon", max_length=50, blank=True)
    email = models.EmailField("E-Mail", blank=True)
    position = models.CharField("Position", max_length=100, blank=True)
    abteilung = models.CharField("Abteilung", max_length=100, blank=True)
    notfallkontakt_name = models.CharField("Notfallkontakt", max_length=150, blank=True)
    notfallkontakt_telefon = models.CharField("Telefon Notfallkontakt", max_length=50, blank=True)
    eintrittsdatum = models.DateField("Eintrittsdatum", null=True, blank=True)
    austrittsdatum = models.DateField("Austrittsdatum", null=True, blank=True)
    benutzer = models.OneToOneField(
        settings.AUTH_USER_MODEL, verbose_name="Verknüpfter Benutzer", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="mitarbeiter",
        help_text="Optional. Erlaubt dem Benutzer, eigene Zeiten und Urlaub zu sehen und Urlaub zu beantragen.",
    )
    notizen = models.TextField("Notizen", blank=True)
    erstellt = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mitarbeiter"
        verbose_name_plural = "Mitarbeiter"
        ordering = ["nachname", "vorname"]

    def __str__(self):
        return f"{self.nachname}, {self.vorname}"

    @property
    def anzeigename(self) -> str:
        return f"{self.vorname} {self.nachname}".strip()

    @property
    def listenname(self) -> str:
        """„Nachname, Vorname“ für Listen und Übersichten."""
        return ", ".join(t for t in (self.nachname, self.vorname) if t)

    def ist_aktiv(self, tag: datetime.date | None = None) -> bool:
        tag = tag or datetime.date.today()
        if self.eintrittsdatum and self.eintrittsdatum > tag:
            return False
        return not (self.austrittsdatum and self.austrittsdatum < tag)

    def clean(self):
        if self.eintrittsdatum and self.austrittsdatum and self.austrittsdatum < self.eintrittsdatum:
            raise ValidationError({"austrittsdatum": "Das Austrittsdatum liegt vor dem Eintrittsdatum."})

    def save(self, *args, **kwargs):
        if self.personalnummer:
            super().save(*args, **kwargs)
            return
        with transaction.atomic():
            self.personalnummer = f"TMP-{uuid.uuid4().hex[:12]}"
            super().save(*args, **kwargs)
            self.personalnummer = f"P-{self.pk:04d}"
            super().save(update_fields=["personalnummer"])


class Vertrag(models.Model):
    """Ein Vertragsstand mit Gültigkeitszeitraum. Änderungen (z. B. mehr Urlaub) werden als neuer Stand angelegt."""

    class Art(models.TextChoices):
        VOLLZEIT = "vollzeit", "Vollzeit"
        TEILZEIT = "teilzeit", "Teilzeit"
        MINIJOB = "minijob", "Minijob"
        AZUBI = "azubi", "Auszubildende/r"
        WERKSTUDENT = "werkstudent", "Werkstudent/in"
        FREIE_MITARBEIT = "freiberuflich", "Freie Mitarbeit"

    mitarbeiter = models.ForeignKey(Mitarbeiter, on_delete=models.CASCADE, related_name="vertraege")
    gueltig_ab = models.DateField("Gültig ab")
    gueltig_bis = models.DateField("Gültig bis", null=True, blank=True, help_text="Leer = unbefristet gültig.")
    art = models.CharField("Beschäftigungsart", max_length=20, choices=Art.choices, default=Art.VOLLZEIT)
    wochenstunden = models.DecimalField("Wochenstunden", max_digits=5, decimal_places=2, default=40)
    arbeitstage = models.CharField("Arbeitstage", max_length=20, default="0,1,2,3,4")
    urlaubstage_pro_jahr = models.DecimalField("Urlaubstage pro Jahr", max_digits=5, decimal_places=1, default=30)
    probezeit_ende = models.DateField("Probezeit bis", null=True, blank=True)
    befristet_bis = models.DateField("Befristet bis", null=True, blank=True)
    kuendigungsfrist = models.CharField("Kündigungsfrist", max_length=100, blank=True, help_text="z. B. 4 Wochen zum Monatsende")
    notizen = models.TextField("Notizen", blank=True)

    class Meta:
        verbose_name = "Vertrag"
        verbose_name_plural = "Verträge"
        ordering = ["-gueltig_ab"]

    def __str__(self):
        return f"{self.mitarbeiter} ab {self.gueltig_ab:%d.%m.%Y}"

    @property
    def arbeitstage_liste(self) -> list[int]:
        return [int(t) for t in self.arbeitstage.split(",") if t.strip().isdigit()]

    @property
    def arbeitstage_text(self) -> str:
        namen = dict(WOCHENTAGE)
        return ", ".join(namen[t] for t in self.arbeitstage_liste if t in namen)

    def clean(self):
        if self.gueltig_ab and self.gueltig_bis and self.gueltig_bis < self.gueltig_ab:
            raise ValidationError({"gueltig_bis": "Das Ende liegt vor dem Beginn."})
        if self.gueltig_ab and self.mitarbeiter_id:
            ende = self.gueltig_bis or datetime.date.max
            andere = Vertrag.objects.filter(mitarbeiter_id=self.mitarbeiter_id).exclude(pk=self.pk)
            for v in andere:
                if v.gueltig_ab <= ende and (v.gueltig_bis or datetime.date.max) >= self.gueltig_ab:
                    raise ValidationError(
                        f"Der Zeitraum überschneidet sich mit dem Vertragsstand ab {v.gueltig_ab:%d.%m.%Y}."
                    )


class Urlaubsjahr(models.Model):
    """Abweichungen vom berechneten Urlaubsanspruch eines Jahres (Übertrag, manueller Anspruch)."""

    mitarbeiter = models.ForeignKey(Mitarbeiter, on_delete=models.CASCADE, related_name="urlaubsjahre")
    jahr = models.PositiveSmallIntegerField("Jahr")
    anspruch = models.DecimalField(
        "Anspruch (manuell)", max_digits=5, decimal_places=1, null=True, blank=True,
        help_text="Leer = aus dem Vertrag berechnen (anteilig bei Eintritt im Jahr).",
    )
    uebertrag = models.DecimalField("Übertrag aus Vorjahr", max_digits=5, decimal_places=1, default=0)
    notiz = models.CharField("Notiz", max_length=200, blank=True)

    class Meta:
        verbose_name = "Urlaubsjahr"
        verbose_name_plural = "Urlaubsjahre"
        unique_together = [("mitarbeiter", "jahr")]
        ordering = ["-jahr"]


class Urlaubsantrag(models.Model):
    class Status(models.TextChoices):
        BEANTRAGT = "beantragt", "Beantragt"
        GENEHMIGT = "genehmigt", "Genehmigt"
        ABGELEHNT = "abgelehnt", "Abgelehnt"
        STORNIERT = "storniert", "Storniert"

    mitarbeiter = models.ForeignKey(Mitarbeiter, on_delete=models.CASCADE, related_name="urlaubsantraege")
    von = models.DateField("Von")
    bis = models.DateField("Bis")
    status = models.CharField("Status", max_length=12, choices=Status.choices, default=Status.BEANTRAGT)
    bemerkung = models.CharField("Bemerkung", max_length=300, blank=True)
    entschieden_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    entschieden_am = models.DateTimeField(null=True, blank=True)
    erstellt = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Urlaubsantrag"
        verbose_name_plural = "Urlaubsanträge"
        ordering = ["-von"]

    def __str__(self):
        return f"{self.mitarbeiter}: {self.von:%d.%m.%Y}–{self.bis:%d.%m.%Y}"

    @property
    def zaehlt(self) -> bool:
        return self.status in (self.Status.BEANTRAGT, self.Status.GENEHMIGT)

    def clean(self):
        if self.von and self.bis:
            if self.bis < self.von:
                raise ValidationError({"bis": "Das Ende liegt vor dem Beginn."})
            if self.mitarbeiter_id and self.status in (self.Status.BEANTRAGT, self.Status.GENEHMIGT):
                ueberschneidung = Urlaubsantrag.objects.filter(
                    mitarbeiter_id=self.mitarbeiter_id, von__lte=self.bis, bis__gte=self.von,
                    status__in=[self.Status.BEANTRAGT, self.Status.GENEHMIGT],
                ).exclude(pk=self.pk)
                if ueberschneidung.exists():
                    raise ValidationError("Für diesen Zeitraum gibt es bereits einen Urlaubsantrag.")


class Stundenkorrektur(models.Model):
    """Über-/Fehlstunden ohne Zeiterfassung: Stunden (auch negativ) mit Begründung, mit Genehmigung wie beim Urlaub."""

    Status = Urlaubsantrag.Status

    mitarbeiter = models.ForeignKey(Mitarbeiter, on_delete=models.CASCADE, related_name="stundenkorrekturen")
    datum = models.DateField("Datum")
    stunden = models.DecimalField(
        "Stunden", max_digits=6, decimal_places=2,
        help_text="Überstunden positiv, Fehlstunden negativ (z. B. -1,5). Dezimalstunden: 1,5 = 1 Std. 30 Min.",
    )
    bemerkung = models.CharField("Bemerkung", max_length=300)
    status = models.CharField("Status", max_length=12, choices=Status.choices, default=Status.BEANTRAGT)
    entschieden_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    entschieden_am = models.DateTimeField(null=True, blank=True)
    erstellt = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Über-/Fehlstunden"
        verbose_name_plural = "Über-/Fehlstunden"
        ordering = ["-datum", "-pk"]

    def __str__(self):
        return f"{self.mitarbeiter}: {self.stunden} Std. am {self.datum:%d.%m.%Y}"

    def clean(self):
        if self.stunden is not None and self.stunden == 0:
            raise ValidationError({"stunden": "Bitte eine Stundenzahl ungleich 0 angeben."})
        if self.bemerkung is not None and not self.bemerkung.strip():
            raise ValidationError({"bemerkung": "Die Bemerkung ist ein Pflichtfeld."})


class Anwesenheit(models.Model):
    """Status eines Mitarbeiters an einem Tag. Urlaub ergibt sich aus genehmigten Urlaubsanträgen."""

    class Status(models.TextChoices):
        ANWESEND = "anwesend", "Anwesend"
        HOMEOFFICE = "homeoffice", "Homeoffice"
        DIENSTREISE = "dienstreise", "Dienstreise"
        KRANK = "krank", "Krank"
        SONDERURLAUB = "sonderurlaub", "Sonderurlaub"
        FREIZEITAUSGLEICH = "freizeitausgleich", "Freizeitausgleich"
        BERUFSSCHULE = "berufsschule", "Berufsschule"
        SCHULUNG = "schulung", "Schulung"

    mitarbeiter = models.ForeignKey(Mitarbeiter, on_delete=models.CASCADE, related_name="anwesenheiten")
    datum = models.DateField("Datum")
    status = models.CharField("Status", max_length=20, choices=Status.choices, default=Status.ANWESEND)
    von = models.TimeField("Kommen", null=True, blank=True)
    bis = models.TimeField("Gehen", null=True, blank=True)
    notiz = models.CharField("Notiz", max_length=200, blank=True)

    class Meta:
        verbose_name = "Anwesenheit"
        verbose_name_plural = "Anwesenheiten"
        unique_together = [("mitarbeiter", "datum")]
        ordering = ["-datum"]

    def clean(self):
        if self.von and self.bis and self.bis <= self.von:
            raise ValidationError({"bis": "Gehen muss nach Kommen liegen."})

    @property
    def stunden(self):
        if not (self.von and self.bis):
            return None
        d = datetime.date.today()
        diff = datetime.datetime.combine(d, self.bis) - datetime.datetime.combine(d, self.von)
        return round(diff.total_seconds() / 3600, 2)


class PersonalEinstellung(models.Model):
    """Einstellungen der Personalverwaltung (genau ein Datensatz)."""

    bundesland = models.CharField(
        "Bundesland", max_length=2, blank=True,
        help_text="Bestimmt die gesetzlichen Feiertage. Leer = keine gesetzlichen Feiertage.",
    )

    class Meta:
        verbose_name = "Personal-Einstellung"
        verbose_name_plural = "Personal-Einstellungen"

    @classmethod
    def laden(cls) -> "PersonalEinstellung":
        return cls.objects.get_or_create(pk=1)[0]


class Sondertag(models.Model):
    """Eigener Feiertag (kostet keinen Urlaub) oder halber Tag (kostet 0,5 Urlaubstage), jährlich oder einmalig."""

    ANTEILE = [(0, "Feiertag (kein Urlaubstag)"), (0.5, "Halber Tag (0,5 Urlaubstage)")]

    name = models.CharField("Bezeichnung", max_length=100)
    tag = models.PositiveSmallIntegerField("Tag", validators=[MinValueValidator(1), MaxValueValidator(31)])
    monat = models.PositiveSmallIntegerField("Monat", validators=[MinValueValidator(1), MaxValueValidator(12)])
    jahr = models.PositiveSmallIntegerField(
        "Nur im Jahr", null=True, blank=True, help_text="Leer = jedes Jahr.",
    )
    urlaubsanteil = models.DecimalField("Urlaubsanteil", max_digits=2, decimal_places=1, default=0)

    class Meta:
        verbose_name = "Sondertag"
        verbose_name_plural = "Sondertage"
        ordering = ["monat", "tag", "jahr"]

    def __str__(self):
        return f"{self.name} ({self.tag}.{self.monat}.)"

    def clean(self):
        if self.tag and self.monat:
            try:
                datetime.date(self.jahr or 2000, self.monat, self.tag)
            except ValueError:
                raise ValidationError("Dieses Datum gibt es nicht.")
