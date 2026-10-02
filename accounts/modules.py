"""
Module der Anwendung, auf die sich Gruppenrechte beziehen.

Die Liste entspricht ``known_modules()`` der bisherigen PHP-Anwendung. Für
jedes Modul gibt es zwei Rechte: ``<modul>_lesen`` und ``<modul>_schreiben``.
Schreibrecht schließt das Leserecht ein.

Kommt ein neues Modul hinzu, wird es hier eingetragen und anschließend mit
``python manage.py makemigrations accounts`` die zugehörige Migration erzeugt.
"""

MODULE = {
    "artikel": "Artikel",
    "lager": "Lager",
    "kunden": "Kunden",
    "lieferanten": "Lieferanten",
    "angebote": "Angebote",
    "auftraege": "Aufträge",
    "rechnungen": "Rechnungen",
    "abos": "Abonnements",
    "kategorien": "Kategorien",
    "einstellungen": "Einstellungen",
}

AKTION_LESEN = "lesen"
AKTION_SCHREIBEN = "schreiben"
AKTIONEN = (AKTION_LESEN, AKTION_SCHREIBEN)

APP_LABEL = "accounts"


def recht_codename(modul: str, aktion: str) -> str:
    """Codename des Django-Rechts, z. B. ``artikel_schreiben``."""
    if modul not in MODULE:
        raise KeyError(f"Unbekanntes Modul: {modul!r}")
    if aktion not in AKTIONEN:
        raise ValueError(f"Unbekannte Aktion: {aktion!r}")
    return f"{modul}_{aktion}"


def alle_rechte() -> list[tuple[str, str]]:
    """Alle Rechte als Liste von (codename, Anzeigename) für ``Meta.permissions``."""
    rechte = []
    for modul, label in MODULE.items():
        rechte.append((recht_codename(modul, AKTION_LESEN), f"{label}: lesen"))
        rechte.append((recht_codename(modul, AKTION_SCHREIBEN), f"{label}: schreiben"))
    return rechte
