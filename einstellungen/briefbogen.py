"""Briefbogen aus frei platzierbaren Elementen (Bilder und Textblöcke) für die PDF-Erzeugung.

``elemente_fuer_pdf`` liefert die Elemente samt fertig berechneter CSS-Positionen für das WeasyPrint-Template;
``unterer_rand_mm`` sorgt dafür, dass der fließende Belegtext nicht in Fußzeilenelemente hineinläuft.
"""

import logging
import math
from pathlib import Path

from . import formulare
from .models import BriefbogenElement, Firma

log = logging.getLogger(__name__)

SEITENHOEHE_MM = 297
SEITENBREITE_MM = 210
FUSSBEREICH_AB = SEITENHOEHE_MM * 2 / 3  # Elemente unterhalb dieser Linie gelten als Fußzeile
FUSSBEREICH_PUFFER_MM = 6
ZEILENABSTAND = 1.15

# Platzhalter in Textblöcken -> Feld der Firma
PLATZHALTER = {
    "%CompanyName%": "firmenname",
    "%CompanyStrasse%": "strasse",
    "%CompanyPlz%": "plz",
    "%CompanyOrt%": "ort",
    "%CompanyLand%": "land",
    "%CompanySteuernummer%": "steuernummer",
    "%CompanyUstIdNr%": "ust_id",
    "%CompanyKontoinhaber%": "kontoinhaber",
    "%CompanyIban%": "iban",
    "%CompanyBic%": "bic",
    "%CompanyBank%": "bank",
    "%CompanyEmail%": "email",
    "%CompanyTelefon%": "telefon",
}


def iban_formatiert(iban: str) -> str:
    """IBAN in 4er-Gruppen (nur zur Anzeige)."""
    roh = (iban or "").replace(" ", "")
    return " ".join(roh[i:i + 4] for i in range(0, len(roh), 4))


def platzhalter_ersetzen(text: str, firma: Firma) -> str:
    """Ersetzt bekannte Platzhalter; unbekannte %...%-Ausdrücke bleiben sichtbar stehen."""
    for platzhalter, feld in PLATZHALTER.items():
        if platzhalter in text:
            wert = getattr(firma, feld, "") or ""
            text = text.replace(platzhalter, iban_formatiert(wert) if feld == "iban" else str(wert))
    return text


def _zeilen_schaetzen(text: str, schriftgroesse: int, breite_mm: float) -> int:
    """Zeilenzahl eines Textes bei gegebener Breite (grobe, eher großzügige Schätzung)."""
    zeichen_je_zeile = max(1, int(breite_mm / (schriftgroesse * 0.5 / 72 * 25.4)))
    return sum(max(1, math.ceil(len(z) / zeichen_je_zeile)) for z in text.split("\n"))


def _bildhoehe_mm(element: BriefbogenElement) -> float:
    if element.hoehe_mm is not None:
        return float(element.hoehe_mm)
    try:
        breite_px, hoehe_px = element.bild.width, element.bild.height
        return float(element.breite_mm) * hoehe_px / breite_px if breite_px else float(element.breite_mm)
    except Exception:
        return float(element.breite_mm)


def zeilenhoehe(element: BriefbogenElement) -> float:
    """Zeilenabstand als Faktor der Schriftgröße (Standard 1,15)."""
    return float(element.zeilenhoehe) if element.zeilenhoehe else ZEILENABSTAND


def hoehe_mm(element: BriefbogenElement, firma: Firma) -> float:
    if element.typ == BriefbogenElement.Typ.BILD:
        return _bildhoehe_mm(element) if element.bild else 0.0
    if element.hoehe_mm is not None:
        return float(element.hoehe_mm)
    groesse = element.schriftgroesse or 10
    zeilen = _zeilen_schaetzen(platzhalter_ersetzen(element.text, firma), groesse, float(element.breite_mm))
    return zeilen * groesse / 72 * 25.4 * zeilenhoehe(element)


def unterer_rand_mm(firma: Firma, minimum: float) -> float:
    """Unterer Seitenrand, der Fußzeilenelemente freihält (mindestens ``minimum``)."""
    rand = float(minimum)
    for element in BriefbogenElement.objects.all():
        y = float(element.y_mm)
        if y < FUSSBEREICH_AB:
            continue
        hoehe = hoehe_mm(element, firma)
        oberkante = y if element.vertikale_ausrichtung == BriefbogenElement.Vertikal.OBEN else y - hoehe
        rand = max(rand, SEITENHOEHE_MM - oberkante + FUSSBEREICH_PUFFER_MM)
    return round(rand, 1)


def _mm(wert) -> str:
    return f"{float(wert):.2f}mm"


def elemente_fuer_pdf(firma: Firma, rand_links: float, rand_oben: float, rand_unten: float) -> list[dict]:
    """Elemente mit CSS (``stil``); Positionen in mm ab der Papierecke oben links.

    Die Elemente liegen in einem laufenden Element im Seitenrand-Feld oben links (siehe ``beleg.html``). Anders als
    ``position: fixed`` werden sie dort nicht am Satzspiegel abgeschnitten, auch wenn sie im Seitenrand stehen
    (Fußzeile, Absenderzeile). Die Randparameter bleiben nur aus Kompatibilitätsgründen in der Signatur.
    """
    ergebnis = []
    for element in BriefbogenElement.objects.all():
        links = float(element.x_mm)
        stil = [f"left:{links:.2f}mm", f"width:{_mm(element.breite_mm)}"]
        unten = element.vertikale_ausrichtung == BriefbogenElement.Vertikal.UNTEN
        if unten:
            # Oberkante aus der Höhe errechnen und die Höhe fest vorgeben.
            hoehe = hoehe_mm(element, firma)
            stil.append(f"top:{float(element.y_mm) - hoehe:.2f}mm")
            stil.append(f"height:{hoehe:.2f}mm")
        else:
            stil.append(f"top:{float(element.y_mm):.2f}mm")
        eintrag = {"typ": element.typ}
        if element.typ == BriefbogenElement.Typ.BILD:
            if not element.bild:
                continue
            try:
                eintrag["bild"] = Path(element.bild.path).as_uri()
            except Exception:
                log.warning("Briefbogen-Bild nicht lesbar: %s", element.bild.name)
                continue
            if element.hoehe_mm is not None:
                if not unten:
                    stil.append(f"height:{_mm(element.hoehe_mm)}")
                stil.append("object-fit:" + ("contain" if element.seitenverhaeltnis_beibehalten else "fill"))
        else:
            if not element.text.strip():
                continue
            eintrag["text"] = platzhalter_ersetzen(element.text, firma)
            schrift = formulare.SCHRIFTARTEN.get(element.schriftart or "", formulare.SCHRIFTARTEN["Helvetica"])
            stil += [
                f"font-family:{schrift}", f"font-size:{element.schriftgroesse or 10}pt",
                f"line-height:{zeilenhoehe(element):g}", "white-space:pre-wrap",
                f"text-align:{ {'mitte': 'center', 'rechts': 'right'}.get(element.ausrichtung, 'left') }",
            ]
            if element.schriftfarbe:
                stil.append(f"color:{element.schriftfarbe}")
            if element.hoehe_mm is not None and not unten:
                stil.append(f"height:{_mm(element.hoehe_mm)}")
            if unten:
                # Text sitzt bündig an der Unterkante, auch wenn die geschätzte Höhe nicht genau stimmt.
                stil += ["display:flex", "flex-direction:column", "justify-content:flex-end"]
        eintrag["stil"] = ";".join(stil)
        ergebnis.append(eintrag)
    return ergebnis
