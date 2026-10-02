"""Formulareinstellungen für PDFs: Vorgaben und Auflösung Belegart -> global -> Vorgabe."""

from .models import Formulareinstellung

BEREICHE = ("angebot", "auftrag", "rechnung")

VORGABEN = {
    "global": {
        "schriftart": "Helvetica",
        "schriftgroesse": "10",
        "rand_oben": "20",
        "rand_unten": "20",
        "rand_links": "20",
        "rand_rechts": "20",
        "briefbogen_verwenden": "1",
        "logo_position": "links",
        "logo_hoehe": "20",
        "akzentfarbe": "#0d6efd",
        "fusszeile": "",
        "seitenzahl": "1",
        "fusszeile_firmenblock": "1",
        "spalten": "pos,artikelnr,bezeichnung,menge,einzelpreis,rabatt,gesamt",
    },
    "angebot": {
        "titel": "Angebot",
        "einleitung": "Vielen Dank für Ihre Anfrage. Wir unterbreiten Ihnen folgendes Angebot:",
        "schluss": "Wir freuen uns auf Ihren Auftrag.",
        "termin_bezeichnung": "Gültig bis",
        "termin_tage": "30",
        "spalten_abweichend": "",
        "steueraufschluesselung": "1",
        "zwischensumme": "1",
    },
    "auftrag": {
        "titel": "Auftragsbestätigung",
        "einleitung": "Wir bestätigen Ihnen folgenden Auftrag:",
        "schluss": "Vielen Dank für Ihren Auftrag.",
        "termin_bezeichnung": "Liefertermin",
        "termin_tage": "14",
        "spalten_abweichend": "",
        "steueraufschluesselung": "1",
        "zwischensumme": "1",
    },
    "rechnung": {
        "titel": "Rechnung",
        "einleitung": "Wir stellen Ihnen folgende Leistungen in Rechnung:",
        "schluss": "Vielen Dank für Ihr Vertrauen.",
        "termin_bezeichnung": "Zahlungsziel",
        "termin_tage": "14",
        "spalten_abweichend": "",
        "steueraufschluesselung": "1",
        "zwischensumme": "1",
    },
}

SCHRIFTARTEN = {
    "Helvetica": "Helvetica, Arial, 'Liberation Sans', sans-serif",
    "Times": "'Times New Roman', Times, 'Liberation Serif', serif",
    "Courier": "'Courier New', Courier, 'Liberation Mono', monospace",
    "DejaVu Sans": "'DejaVu Sans', sans-serif",
}


def einstellungen_laden() -> dict[tuple[str, str], str]:
    return {(e.bereich, e.schluessel): e.wert for e in Formulareinstellung.objects.all()}


def holen(bereich: str, schluessel: str, gespeichert=None) -> str:
    """Wert für ``bereich``; leer = geerbt von ``global``, dann Vorgabe."""
    gespeichert = einstellungen_laden() if gespeichert is None else gespeichert
    for b in (bereich, "global"):
        wert = gespeichert.get((b, schluessel), "")
        if wert != "":
            return wert
    for b in (bereich, "global"):
        if schluessel in VORGABEN.get(b, {}):
            return VORGABEN[b][schluessel]
    return ""


def alle(bereich: str) -> dict[str, str]:
    """Alle aufgelösten Werte eines Bereichs (inkl. globaler Schlüssel)."""
    gespeichert = einstellungen_laden()
    schluessel = set(VORGABEN["global"]) | set(VORGABEN.get(bereich, {}))
    return {k: holen(bereich, k, gespeichert) for k in schluessel}
