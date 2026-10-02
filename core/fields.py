"""Eigene Modellfelder."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models

PRAEFIX = "enc1:"


def _fernet() -> Fernet:
    schluessel = hashlib.sha256(("kybro-feld:" + settings.SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(schluessel))


class VerschluesseltesTextFeld(models.TextField):
    """Speichert Geheimnisse (z. B. SMTP-Passwort) verschlüsselt in der Datenbank.

    Der Schlüssel wird aus ``SECRET_KEY`` abgeleitet. Ändert sich der SECRET_KEY,
    lassen sich die Werte nicht mehr lesen und müssen neu eingegeben werden
    (das Feld liefert dann einen leeren Text statt eines Fehlers).
    """

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if not value:
            return ""
        return PRAEFIX + _fernet().encrypt(value.encode()).decode()

    def from_db_value(self, value, expression, connection):
        if not value:
            return ""
        if not value.startswith(PRAEFIX):
            return value
        try:
            return _fernet().decrypt(value[len(PRAEFIX):].encode()).decode()
        except InvalidToken:
            return ""
