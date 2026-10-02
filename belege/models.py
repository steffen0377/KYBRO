"""Belege: Angebote, Aufträge, Rechnungen und Abonnements."""

import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

CENT = Decimal("0.01")


def runden(betrag: Decimal) -> Decimal:
    """Kaufmännisch auf Cent runden."""
    return Decimal(betrag).quantize(CENT, rounding=ROUND_HALF_UP)


class Abrechnung(models.TextChoices):
    EINMALIG = "einmalig", "Einmalig"
    MONATLICH = "monatlich", "Monatlich"
    JAEHRLICH = "jaehrlich", "Jährlich"


class Beleg(models.Model):
    """Gemeinsame Felder von Angebot, Auftrag und Rechnung."""

    nummer = models.CharField("Nummer", max_length=30, unique=True, editable=False)
    kunde = models.ForeignKey("stammdaten.Kunde", verbose_name="Kunde", on_delete=models.PROTECT, related_name="+")
    datum = models.DateField("Datum", default=timezone.localdate)
    notizen = models.TextField("Notizen", blank=True)
    netto = models.DecimalField("Netto", max_digits=12, decimal_places=2, default=0, editable=False)
    steuer = models.DecimalField("MwSt.", max_digits=12, decimal_places=2, default=0, editable=False)
    brutto = models.DecimalField("Brutto", max_digits=12, decimal_places=2, default=0, editable=False)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    erstellt = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ["-erstellt", "-pk"]

    def __str__(self):
        return self.nummer

    def summen(self) -> "Summen":
        return berechne_summen(self.positionen.all())

    def summen_neu_berechnen(self) -> "Summen":
        """Berechnet die Summen aus den Positionen und speichert sie am Beleg."""
        summen = self.summen()
        self.netto, self.steuer, self.brutto = summen.netto, summen.steuer, summen.brutto
        self.save(update_fields=["netto", "steuer", "brutto"])
        return summen


class Position(models.Model):
    """Gemeinsame Felder einer Belegposition (Momentaufnahme der Artikeldaten)."""

    position = models.PositiveIntegerField("Pos.", default=1)
    artikel = models.ForeignKey(
        "stammdaten.Artikel", verbose_name="Artikel", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    artikelnummer = models.CharField("Artikelnummer", max_length=20, blank=True)
    beschreibung = models.CharField("Beschreibung", max_length=255)
    einheit = models.CharField("Einheit", max_length=20, default="Stk.")
    menge = models.DecimalField("Menge", max_digits=10, decimal_places=2, default=1)
    einzelpreis = models.DecimalField("Einzelpreis (netto)", max_digits=10, decimal_places=2, default=0)
    rabatt = models.DecimalField(
        "Rabatt (%)", max_digits=5, decimal_places=2, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    steuersatz = models.DecimalField("MwSt. (%)", max_digits=5, decimal_places=2, default=Decimal("19.00"))
    abrechnung = models.CharField("Modell", max_length=10, choices=Abrechnung.choices, default=Abrechnung.EINMALIG)
    preisoption = models.ForeignKey(
        "stammdaten.Preisoption", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        abstract = True
        ordering = ["position", "pk"]

    def __str__(self):
        return f"{self.position}. {self.beschreibung}"

    @property
    def netto(self) -> Decimal:
        """Nettobetrag der Position nach Rabatt, auf Cent gerundet."""
        return runden(self.menge * self.einzelpreis * (Decimal(100) - self.rabatt) / Decimal(100))

    @property
    def ist_abo(self) -> bool:
        return self.abrechnung != Abrechnung.EINMALIG

    def daten_kopieren(self) -> dict:
        return {
            "position": self.position, "artikel_id": self.artikel_id, "artikelnummer": self.artikelnummer,
            "beschreibung": self.beschreibung, "einheit": self.einheit, "menge": self.menge,
            "einzelpreis": self.einzelpreis, "rabatt": self.rabatt, "steuersatz": self.steuersatz,
            "abrechnung": self.abrechnung, "preisoption_id": self.preisoption_id,
        }


class Summen:
    """Summen eines Belegs, getrennt nach Steuersatz (für PDF und E-Rechnung)."""

    def __init__(self, gruppen: dict[Decimal, Decimal]):
        # gruppen: Steuersatz -> Summe der Nettobeträge
        self.gruppen = {
            satz: {"netto": netto, "steuer": runden(netto * satz / Decimal(100))}
            for satz, netto in sorted(gruppen.items())
        }
        self.netto = sum((g["netto"] for g in self.gruppen.values()), Decimal("0.00"))
        self.steuer = sum((g["steuer"] for g in self.gruppen.values()), Decimal("0.00"))
        self.brutto = self.netto + self.steuer


def berechne_summen(positionen) -> Summen:
    """Steuer wird je Steuersatz auf die Summe der gerundeten Zeilen-Nettobeträge berechnet
    (wie bei der E-Rechnung nach EN 16931 gefordert), nicht je Zeile."""
    gruppen: dict[Decimal, Decimal] = {}
    for position in positionen:
        satz = Decimal(position.steuersatz).quantize(CENT)
        gruppen[satz] = gruppen.get(satz, Decimal("0.00")) + position.netto
    return Summen(gruppen)


# ---------------------------------------------------------------------------
# Angebot
# ---------------------------------------------------------------------------


class Angebot(Beleg):
    class Status(models.TextChoices):
        ENTWURF = "entwurf", "Entwurf"
        VERSENDET = "versendet", "Versendet"
        ANGENOMMEN = "angenommen", "Angenommen"
        ABGELEHNT = "abgelehnt", "Abgelehnt"

    gueltig_bis = models.DateField("Gültig bis", null=True, blank=True)
    status = models.CharField("Status", max_length=12, choices=Status.choices, default=Status.ENTWURF)

    class Meta(Beleg.Meta):
        verbose_name = "Angebot"
        verbose_name_plural = "Angebote"

    @property
    def bearbeitbar(self) -> bool:
        """Ein Angebot bleibt bearbeitbar, bis daraus ein Auftrag entstanden ist."""
        return not hasattr(self, "auftrag")


class AngebotPosition(Position):
    angebot = models.ForeignKey(Angebot, on_delete=models.CASCADE, related_name="positionen")

    class Meta(Position.Meta):
        verbose_name = "Angebotsposition"
        verbose_name_plural = "Angebotspositionen"


# ---------------------------------------------------------------------------
# Auftrag
# ---------------------------------------------------------------------------


class Auftrag(Beleg):
    class Status(models.TextChoices):
        OFFEN = "offen", "Offen"
        IN_BEARBEITUNG = "in_bearbeitung", "In Bearbeitung"
        UNTERSCHRIEBEN = "unterschrieben", "Unterschrieben"
        ABGESCHLOSSEN = "abgeschlossen", "Abgeschlossen"
        STORNIERT = "storniert", "Storniert"

    angebot = models.OneToOneField(
        Angebot, verbose_name="Angebot", null=True, blank=True, on_delete=models.SET_NULL, related_name="auftrag"
    )
    status = models.CharField("Status", max_length=15, choices=Status.choices, default=Status.OFFEN)
    unterschrift = models.ImageField("Unterschrift", upload_to="unterschriften/", blank=True)
    unterschrieben_am = models.DateTimeField(null=True, blank=True)
    unterschrieben_von = models.CharField("Unterschrieben von", max_length=150, blank=True)
    # Von der mobilen App vergebene ID: macht das erneute Senden eines Auftrags unschädlich.
    client_uuid = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    geaendert = models.DateTimeField(auto_now=True)

    class Meta(Beleg.Meta):
        verbose_name = "Auftrag"
        verbose_name_plural = "Aufträge"

    @property
    def abgerechnet(self) -> bool:
        return self.rechnungen.exclude(status=Rechnung.Status.STORNIERT).exists()


class AuftragPosition(Position):
    auftrag = models.ForeignKey(Auftrag, on_delete=models.CASCADE, related_name="positionen")
    client_uuid = models.UUIDField(null=True, blank=True, unique=True, editable=False)

    class Meta(Position.Meta):
        verbose_name = "Auftragsposition"
        verbose_name_plural = "Auftragspositionen"


# ---------------------------------------------------------------------------
# Rechnung
# ---------------------------------------------------------------------------


class Rechnung(Beleg):
    class Status(models.TextChoices):
        ENTWURF = "entwurf", "Entwurf"
        VERSENDET = "versendet", "Versendet"
        BEZAHLT = "bezahlt", "Bezahlt"
        UEBERFAELLIG = "ueberfaellig", "Überfällig"
        STORNIERT = "storniert", "Storniert"

    angebot = models.ForeignKey(
        Angebot, null=True, blank=True, on_delete=models.SET_NULL, related_name="rechnungen"
    )
    auftrag = models.ForeignKey(
        Auftrag, null=True, blank=True, on_delete=models.SET_NULL, related_name="rechnungen"
    )
    abo = models.ForeignKey(
        "Abo", verbose_name="Abonnement", null=True, blank=True, on_delete=models.SET_NULL, related_name="rechnungen"
    )
    leistungsdatum = models.DateField("Leistungsdatum", null=True, blank=True)
    zeitraum_von = models.DateField("Leistungszeitraum von", null=True, blank=True)
    zeitraum_bis = models.DateField("Leistungszeitraum bis", null=True, blank=True)
    faellig_am = models.DateField("Fällig bis", null=True, blank=True)
    status = models.CharField("Status", max_length=12, choices=Status.choices, default=Status.ENTWURF)
    # Aus Abonnements erzeugte Rechnungen buchen keinen Lagerbestand.
    lagerbuchung = models.BooleanField(default=True, editable=False)

    class Meta(Beleg.Meta):
        verbose_name = "Rechnung"
        verbose_name_plural = "Rechnungen"
        constraints = [
            models.UniqueConstraint(
                # Mehrere Rechnungen ohne Abo (NULL) bleiben erlaubt; je Abo und Zeitraum
                # gibt es nur eine Rechnung (schützt den Abo-Lauf vor Doppelabrechnung).
                fields=["abo", "zeitraum_von"], name="eindeutig_abo_rechnung_je_zeitraum",
            )
        ]

    @property
    def ist_entwurf(self) -> bool:
        return self.status == self.Status.ENTWURF

    @property
    def ist_ueberfaellig(self) -> bool:
        if self.status == self.Status.UEBERFAELLIG:
            return True
        return (
            self.status == self.Status.VERSENDET
            and self.faellig_am is not None
            and self.faellig_am < timezone.localdate()
        )

    def als_bezahlt_markieren(self, benutzer=None):
        from . import services

        services.rechnung_status_aendern(self, self.Status.BEZAHLT)


class RechnungPosition(Position):
    rechnung = models.ForeignKey(Rechnung, on_delete=models.CASCADE, related_name="positionen")

    class Meta(Position.Meta):
        verbose_name = "Rechnungsposition"
        verbose_name_plural = "Rechnungspositionen"


# ---------------------------------------------------------------------------
# Abonnement
# ---------------------------------------------------------------------------


def monate_addieren(datum: date, monate: int) -> date:
    """Addiert Monate; ein nicht vorhandener Tag (31.) rutscht auf den Monatsletzten."""
    import calendar

    gesamt = datum.year * 12 + (datum.month - 1) + monate
    jahr, monat = divmod(gesamt, 12)
    monat += 1
    return date(jahr, monat, min(datum.day, calendar.monthrange(jahr, monat)[1]))


class Abo(models.Model):
    class Zyklus(models.TextChoices):
        MONATLICH = "monatlich", "Monatlich"
        JAEHRLICH = "jaehrlich", "Jährlich"

    class Status(models.TextChoices):
        AKTIV = "aktiv", "Aktiv"
        GEKUENDIGT = "gekuendigt", "Gekündigt"
        BEENDET = "beendet", "Beendet"

    kunde = models.ForeignKey("stammdaten.Kunde", verbose_name="Kunde", on_delete=models.PROTECT, related_name="abos")
    artikel = models.ForeignKey("stammdaten.Artikel", verbose_name="Artikel", on_delete=models.PROTECT, related_name="abos")
    preisoption = models.ForeignKey(
        "stammdaten.Preisoption", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    auftrag = models.ForeignKey(Auftrag, null=True, blank=True, on_delete=models.SET_NULL, related_name="abos")
    ursprungsrechnung = models.ForeignKey(
        Rechnung, verbose_name="Ursprungsrechnung", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    zyklus = models.CharField("Abrechnung", max_length=10, choices=Zyklus.choices)
    menge = models.DecimalField("Menge", max_digits=10, decimal_places=2, default=1)
    preis = models.DecimalField("Preis je Zyklus (netto)", max_digits=10, decimal_places=2, default=0)
    beginn = models.DateField("Beginn")
    naechste_abrechnung = models.DateField("Nächste Abrechnung")
    ende = models.DateField("Ende", null=True, blank=True)
    mindestlaufzeit_monate = models.PositiveIntegerField("Mindestlaufzeit (Monate)", null=True, blank=True)
    kuendigungsfrist_tage = models.PositiveIntegerField("Kündigungsfrist (Tage)", null=True, blank=True)
    fruehestes_ende = models.DateField("Frühestes Vertragsende", null=True, blank=True)
    status = models.CharField("Status", max_length=12, choices=Status.choices, default=Status.AKTIV)
    kuendigung_eingang = models.DateField("Kündigung eingegangen am", null=True, blank=True)
    kuendigung_wirksam = models.DateField("Kündigung wirksam zum", null=True, blank=True)
    notizen = models.TextField("Notizen", blank=True)
    erstellt = models.DateTimeField(auto_now_add=True)
    geaendert = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Abonnement"
        verbose_name_plural = "Abonnements"
        ordering = ["naechste_abrechnung", "pk"]

    def __str__(self):
        return f"Abo {self.pk}: {self.artikel.name} für {self.kunde}"

    @property
    def zyklus_monate(self) -> int:
        return 12 if self.zyklus == self.Zyklus.JAEHRLICH else 1

    def termin_nach(self, termin: date) -> date:
        """Der Abrechnungstermin nach ``termin``, immer vom Beginn aus gerechnet
        (so driftet ein Termin am 31. nicht dauerhaft auf den 28.)."""
        schritt = self.zyklus_monate
        monate = (termin.year - self.beginn.year) * 12 + termin.month - self.beginn.month
        k = max(monate // schritt, 0)
        kandidat = monate_addieren(self.beginn, k * schritt)
        while kandidat <= termin:
            k += 1
            kandidat = monate_addieren(self.beginn, k * schritt)
        return kandidat
