"""Stammdaten: Kategorien, Artikel, Kunden und Lieferanten."""

import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction

CENT = Decimal("0.01")


class Kategorie(models.Model):
    name = models.CharField("Name", max_length=100, unique=True)
    uebergeordnet = models.ForeignKey(
        "self",
        verbose_name="Übergeordnete Kategorie",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="unterkategorien",
    )
    erstellt = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Kategorie"
        verbose_name_plural = "Kategorien"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def nachfahren_ids(self) -> set[int]:
        """IDs aller Unterkategorien auf beliebiger Ebene."""
        if self.pk is None:
            return set()
        nach_eltern: dict[int | None, list[int]] = {}
        for pk, eltern in Kategorie.objects.values_list("pk", "uebergeordnet_id"):
            nach_eltern.setdefault(eltern, []).append(pk)
        ergebnis: set[int] = set()
        offen = list(nach_eltern.get(self.pk, []))
        while offen:
            aktuell = offen.pop()
            if aktuell in ergebnis:
                continue
            ergebnis.add(aktuell)
            offen.extend(nach_eltern.get(aktuell, []))
        return ergebnis

    def clean(self):
        super().clean()
        if self.pk and self.uebergeordnet_id:
            if self.uebergeordnet_id == self.pk:
                raise ValidationError(
                    {"uebergeordnet": "Eine Kategorie kann nicht ihre eigene Übergeordnete sein."}
                )
            if self.uebergeordnet_id in self.nachfahren_ids():
                raise ValidationError(
                    {
                        "uebergeordnet": "Die gewählte Übergeordnete ist eine "
                        "Unterkategorie dieser Kategorie."
                    }
                )


class Artikel(models.Model):
    artikelnummer = models.CharField("Artikelnummer", max_length=20, unique=True, editable=False)
    ean = models.CharField("EAN", max_length=20, blank=True, null=True, unique=True)
    han = models.CharField("HAN (Herstellerartikelnummer)", max_length=50, blank=True)
    name = models.CharField("Name", max_length=200)
    beschreibung = models.TextField("Beschreibung", blank=True)
    einheit = models.CharField("Einheit", max_length=20, default="Stk.")
    einkaufspreis = models.DecimalField("Einkaufspreis (€)", max_digits=10, decimal_places=2, default=0)
    verkaufspreis = models.DecimalField("Verkaufspreis (€, netto)", max_digits=10, decimal_places=2, default=0)
    steuersatz = models.DecimalField("MwSt.-Satz (%)", max_digits=5, decimal_places=2, default=Decimal("19.00"))
    bestand = models.DecimalField("Bestand", max_digits=10, decimal_places=2, default=0, editable=False)
    mindestbestand = models.DecimalField("Mindestbestand", max_digits=10, decimal_places=2, default=0)
    lagerfuehrung = models.BooleanField("Lagerbestand verwalten", default=True)
    seriennummern = models.BooleanField("Seriennummern erfassen", default=False)
    aktiv = models.BooleanField("Aktiv", default=True)
    kategorien = models.ManyToManyField(Kategorie, verbose_name="Kategorien", blank=True, related_name="artikel")
    erstellt = models.DateTimeField(auto_now_add=True)
    geaendert = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Artikel"
        verbose_name_plural = "Artikel"
        ordering = ["-aktiv", "name"]

    def __str__(self):
        return f"{self.artikelnummer} {self.name}"

    def save(self, *args, **kwargs):
        # Die Artikelnummer ist die 5-stellige ID und ändert sich nie.
        if not self.artikelnummer:
            with transaction.atomic():
                self.artikelnummer = f"TMP-{uuid.uuid4().hex[:12]}"
                super().save(*args, **kwargs)
                self.artikelnummer = f"{self.pk:05d}"
                super().save(update_fields=["artikelnummer"])
            return
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.seriennummern and not self.lagerfuehrung:
            raise ValidationError(
                {"seriennummern": "Seriennummern setzen die Lagerführung voraus."}
            )

    @property
    def unter_mindestbestand(self) -> bool:
        return self.lagerfuehrung and self.bestand <= self.mindestbestand

    def sonderpreis_fuer(self, kunde) -> "Sonderpreis | None":
        if kunde is None:
            return None
        return self.sonderpreise.filter(kunde=kunde, aktiv=True).first()

    def preis_fuer(self, kunde=None) -> Decimal:
        """Nettopreis für einen Kunden: aktiver Sonderpreis oder Standardpreis."""
        sonder = self.sonderpreis_fuer(kunde)
        if sonder:
            return sonder.preis_auf(self.verkaufspreis)
        return self.verkaufspreis


class ArtikelLieferant(models.Model):
    artikel = models.ForeignKey(Artikel, on_delete=models.CASCADE, related_name="lieferanten")
    lieferant = models.ForeignKey("Lieferant", verbose_name="Lieferant", on_delete=models.CASCADE, related_name="artikel")
    lieferanten_artikelnummer = models.CharField("Artikelnummer beim Lieferanten", max_length=50, blank=True)
    hek = models.DecimalField("Unser HEK (€)", max_digits=10, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Lieferant eines Artikels"
        verbose_name_plural = "Lieferanten eines Artikels"
        constraints = [
            models.UniqueConstraint(fields=["artikel", "lieferant"], name="eindeutig_artikel_lieferant")
        ]


class Sonderpreis(models.Model):
    class Art(models.TextChoices):
        FIX = "fixed", "Fixpreis (€)"
        PROZENT = "percent", "Rabatt (%)"

    artikel = models.ForeignKey(Artikel, on_delete=models.CASCADE, related_name="sonderpreise")
    kunde = models.ForeignKey("Kunde", verbose_name="Kunde", on_delete=models.CASCADE, related_name="sonderpreise")
    art = models.CharField("Art", max_length=10, choices=Art.choices, default=Art.FIX)
    wert = models.DecimalField("Wert", max_digits=10, decimal_places=2, default=0)
    aktiv = models.BooleanField("Aktiv", default=True)

    class Meta:
        verbose_name = "Sonderpreis"
        verbose_name_plural = "Sonderpreise"
        constraints = [
            models.UniqueConstraint(fields=["artikel", "kunde"], name="eindeutig_sonderpreis_je_kunde")
        ]

    def preis_auf(self, standardpreis: Decimal) -> Decimal:
        if self.art == self.Art.PROZENT:
            rabatt = (standardpreis * self.wert / 100).quantize(CENT)
            return max(standardpreis - rabatt, Decimal("0.00"))
        return self.wert


class Preisoption(models.Model):
    """Verkaufsmodell eines Artikels: Einmalkauf oder Abo (monatlich/jährlich)."""

    class Abrechnung(models.TextChoices):
        EINMALIG = "einmalig", "Einmalig"
        MONATLICH = "monatlich", "Monatlich"
        JAEHRLICH = "jaehrlich", "Jährlich"

    artikel = models.ForeignKey(Artikel, on_delete=models.CASCADE, related_name="preisoptionen")
    abrechnung = models.CharField("Modell", max_length=10, choices=Abrechnung.choices, default=Abrechnung.EINMALIG)
    preis = models.DecimalField("Preis (€)", max_digits=10, decimal_places=2, default=0)
    mindestlaufzeit_monate = models.PositiveIntegerField("Mindestlaufzeit (Monate)", null=True, blank=True)
    kuendigungsfrist_tage = models.PositiveIntegerField("Kündigungsfrist (Tage)", null=True, blank=True)
    aktiv = models.BooleanField("Aktiv", default=True)
    sortierung = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Preisoption"
        verbose_name_plural = "Preisoptionen"
        ordering = ["sortierung", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["artikel", "abrechnung"], name="eindeutig_option_je_modell")
        ]

    @property
    def ist_abo(self) -> bool:
        return self.abrechnung != self.Abrechnung.EINMALIG

    def clean(self):
        super().clean()
        if not self.ist_abo:
            self.mindestlaufzeit_monate = None
            self.kuendigungsfrist_tage = None


class Adresse(models.Model):
    """Gemeinsame Felder von Kunde und Lieferant."""

    firma = models.CharField("Firma", max_length=150, blank=True)
    vorname = models.CharField("Vorname", max_length=100, blank=True)
    nachname = models.CharField("Nachname", max_length=100, blank=True)
    strasse = models.CharField("Straße & Nr.", max_length=150, blank=True)
    plz = models.CharField("PLZ", max_length=20, blank=True)
    ort = models.CharField("Ort", max_length=100, blank=True)
    land = models.CharField("Land", max_length=100, default="Deutschland", blank=True)
    email = models.EmailField("E-Mail", max_length=150, blank=True)
    telefon = models.CharField("Telefon", max_length=50, blank=True)
    steuernummer = models.CharField("Steuernummer", max_length=50, blank=True)
    notizen = models.TextField("Notizen", blank=True)
    erstellt = models.DateTimeField(auto_now_add=True)

    NUMMER_PRAEFIX = ""

    class Meta:
        abstract = True

    @property
    def anzeigename(self) -> str:
        return self.firma or f"{self.vorname} {self.nachname}".strip()

    def __str__(self):
        return self.anzeigename or "(ohne Namen)"

    def clean(self):
        super().clean()
        if not self.firma.strip() and not self.nachname.strip():
            raise ValidationError("Bitte Firma oder Nachname angeben.")

    def _nummer_vergeben(self, feld: str, *args, **kwargs):
        """Speichert und vergibt beim ersten Speichern die Nummer aus der ID."""
        if getattr(self, feld):
            super().save(*args, **kwargs)
            return
        with transaction.atomic():
            setattr(self, feld, f"TMP-{uuid.uuid4().hex[:12]}")
            super().save(*args, **kwargs)
            setattr(self, feld, f"{self.NUMMER_PRAEFIX}{self.pk:05d}")
            super().save(update_fields=[feld])


class Kunde(Adresse):
    class Zahlungsart(models.TextChoices):
        UEBERWEISUNG = "ueberweisung", "Überweisung"
        LASTSCHRIFT = "lastschrift", "Lastschrift"

    NUMMER_PRAEFIX = "K-"

    kundennummer = models.CharField("Kundennummer", max_length=20, unique=True, editable=False)
    ust_id = models.CharField("USt-IdNr.", max_length=20, blank=True)
    iban = models.CharField("IBAN", max_length=50, blank=True)
    bic = models.CharField("BIC", max_length=30, blank=True)
    bank = models.CharField("Bank", max_length=100, blank=True)
    zahlungsart = models.CharField(
        "Zahlungsmethode", max_length=15, choices=Zahlungsart.choices, default=Zahlungsart.UEBERWEISUNG
    )
    steuerbefreit = models.BooleanField("Kunde ist steuerbefreit (0 % MwSt.)", default=False)
    befreiungsgrund = models.CharField("Befreiungsgrund", max_length=255, blank=True)
    geaendert = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Kunde"
        verbose_name_plural = "Kunden"
        ordering = ["firma", "nachname"]

    def save(self, *args, **kwargs):
        self._nummer_vergeben("kundennummer", *args, **kwargs)

    def clean(self):
        super().clean()
        if self.steuerbefreit and not self.befreiungsgrund.strip():
            raise ValidationError(
                {
                    "befreiungsgrund": "Bei Steuerbefreiung ist der Befreiungsgrund "
                    "Pflicht (z. B. § 4 Nr. 21a UStG)."
                }
            )

    @property
    def offene_summe(self) -> Decimal:
        """Summe der Rechnungen, die weder bezahlt noch storniert sind."""
        from django.apps import apps

        if not apps.is_installed("belege"):
            return Decimal("0.00")
        Rechnung = apps.get_model("belege", "Rechnung")
        summe = (
            Rechnung.objects.filter(kunde=self)
            .exclude(status__in=["bezahlt", "storniert"])
            .aggregate(s=models.Sum("brutto"))["s"]
        )
        return summe or Decimal("0.00")


class Ansprechpartner(models.Model):
    kunde = models.ForeignKey(Kunde, on_delete=models.CASCADE, related_name="ansprechpartner")
    nachname = models.CharField("Nachname", max_length=100, blank=True)
    vorname = models.CharField("Vorname", max_length=100, blank=True)
    firma = models.CharField("Firma", max_length=150, blank=True)
    telefon = models.CharField("Telefonnummer", max_length=50, blank=True)
    email = models.EmailField("E-Mailadresse", max_length=150, blank=True)

    class Meta:
        verbose_name = "Ansprechpartner"
        verbose_name_plural = "Ansprechpartner"
        ordering = ["pk"]


class Lieferant(Adresse):
    class Zahlungsart(models.TextChoices):
        UEBERWEISUNG = "ueberweisung", "Überweisung"
        LASTSCHRIFT = "lastschrift", "Lastschrift"
        ZENTRALREGULIERT = "zentralreguliert", "Zentralreguliert"

    NUMMER_PRAEFIX = "L-"

    lieferantennummer = models.CharField("Lieferantennummer", max_length=20, unique=True, editable=False)
    kundennummer_beim_lieferanten = models.CharField("Unsere Kundennummer beim Lieferanten", max_length=50, blank=True)
    zahlungsart = models.CharField(
        "Zahlungsmethode", max_length=20, choices=Zahlungsart.choices, default=Zahlungsart.UEBERWEISUNG
    )

    class Meta:
        verbose_name = "Lieferant"
        verbose_name_plural = "Lieferanten"
        ordering = ["firma", "nachname"]

    def save(self, *args, **kwargs):
        self._nummer_vergeben("lieferantennummer", *args, **kwargs)
