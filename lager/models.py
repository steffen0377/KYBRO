from django.conf import settings
from django.db import models


class Lagerbewegung(models.Model):
    class Typ(models.TextChoices):
        EINLAGERUNG = "einlagerung", "Einlagerung"
        AUSLAGERUNG = "auslagerung", "Auslagerung"
        KORREKTUR = "korrektur", "Korrektur"
        VERKAUF = "verkauf", "Verkauf"

    artikel = models.ForeignKey("stammdaten.Artikel", on_delete=models.PROTECT, related_name="bewegungen")
    typ = models.CharField("Typ", max_length=15, choices=Typ.choices)
    menge = models.DecimalField("Menge", max_digits=10, decimal_places=2)
    bezug_typ = models.CharField("Bezug", max_length=30, blank=True)
    bezug_id = models.PositiveBigIntegerField(null=True, blank=True)
    notiz = models.CharField("Notiz", max_length=255, blank=True)
    benutzer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    erstellt = models.DateTimeField("Datum", auto_now_add=True)

    class Meta:
        verbose_name = "Lagerbewegung"
        verbose_name_plural = "Lagerbewegungen"
        ordering = ["-erstellt", "-pk"]


class Seriennummer(models.Model):
    class Status(models.TextChoices):
        LAGER = "lager", "Lager"
        VERKAUFT = "verkauft", "Verkauft"
        DEFEKT = "defekt", "Defekt"

    artikel = models.ForeignKey("stammdaten.Artikel", on_delete=models.CASCADE, related_name="seriennummern_liste")
    nummer = models.CharField("Seriennummer", max_length=100)
    status = models.CharField("Status", max_length=10, choices=Status.choices, default=Status.LAGER)
    notiz = models.CharField("Notiz", max_length=255, blank=True)
    rechnung = models.ForeignKey(
        "belege.Rechnung", null=True, blank=True, on_delete=models.SET_NULL, related_name="seriennummern"
    )
    verkauft_am = models.DateTimeField(null=True, blank=True)
    erstellt = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Seriennummer"
        verbose_name_plural = "Seriennummern"
        ordering = ["status", "-erstellt"]
        constraints = [
            models.UniqueConstraint(fields=["artikel", "nummer"], name="eindeutig_seriennummer_je_artikel")
        ]

    def __str__(self):
        return self.nummer
