"""Eigene Kalender mit Terminen und der persönliche Zugangsschlüssel für Kalender-Abos."""

import secrets
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


def neue_uid() -> str:
    return f"{uuid.uuid4()}@kybro"


class Kalender(models.Model):
    """Ein eigener Kalender. Die Systemkalender „Urlaub“ und „Anwesenheit“ werden aus der Personalverwaltung erzeugt
    und sind nicht als Datensatz gespeichert (siehe ``kalender.quellen``)."""

    name = models.CharField("Name", max_length=80, unique=True)
    farbe = models.CharField("Farbe", max_length=7, default="#3b82f6", help_text="Hexwert, z. B. #3b82f6")
    beschreibung = models.CharField("Beschreibung", max_length=200, blank=True)

    class Meta:
        verbose_name = "Kalender"
        verbose_name_plural = "Kalender"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        farbe = (self.farbe or "").strip()
        if len(farbe) != 7 or not farbe.startswith("#") or any(z not in "0123456789abcdefABCDEF" for z in farbe[1:]):
            raise ValidationError({"farbe": "Bitte eine Farbe im Format #rrggbb angeben."})
        self.farbe = farbe.lower()


class Termin(models.Model):
    """Ein Termin. Ganztägige Termine zählen nur nach Datum, das Ende ist dann der letzte Tag (einschließlich)."""

    kalender = models.ForeignKey(Kalender, on_delete=models.CASCADE, related_name="termine")
    titel = models.CharField("Titel", max_length=150)
    ort = models.CharField("Ort", max_length=150, blank=True)
    beschreibung = models.TextField("Beschreibung", blank=True)
    ganztaegig = models.BooleanField("Ganztägig", default=False)
    beginn = models.DateTimeField("Beginn")
    ende = models.DateTimeField("Ende")
    uid = models.CharField(max_length=80, unique=True, default=neue_uid, editable=False)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    erstellt = models.DateTimeField(auto_now_add=True)
    geaendert = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Termin"
        verbose_name_plural = "Termine"
        ordering = ["beginn", "pk"]
        indexes = [models.Index(fields=["beginn", "ende"])]

    def __str__(self):
        return f"{self.titel} ({self.beginn:%d.%m.%Y})"

    def clean(self):
        if self.beginn and self.ende and self.ende < self.beginn:
            raise ValidationError("Das Ende liegt vor dem Beginn.")


def neuer_schluessel() -> str:
    return secrets.token_urlsafe(32)


class KalenderZugang(models.Model):
    """Persönlicher Schlüssel in der Abo-Adresse (``webcal://…/kalender/feed/<Schlüssel>/…``).

    Wer den Schlüssel kennt, kann die Kalender des Benutzers lesen, aber nichts ändern. Er lässt sich jederzeit erneuern.
    """

    benutzer = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="kalender_zugang")
    schluessel = models.CharField(max_length=64, unique=True, default=neuer_schluessel, editable=False)
    erstellt = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Kalender-Zugang"
        verbose_name_plural = "Kalender-Zugänge"

    def __str__(self):
        return f"Kalender-Zugang von {self.benutzer}"

    def erneuern(self) -> None:
        self.schluessel = neuer_schluessel()
        self.save(update_fields=["schluessel"])
