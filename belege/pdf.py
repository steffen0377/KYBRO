"""PDF-Erzeugung für Angebote, Aufträge und Rechnungen (WeasyPrint).

Layout und Texte kommen aus den Formulareinstellungen (Belegart -> global ->
Vorgabe). Rechnungen erhalten zusätzlich das ZUGFeRD-XML (EN 16931).
"""

import logging
from decimal import Decimal
from pathlib import Path

from django.template.loader import render_to_string
from weasyprint import HTML

from einstellungen import briefbogen, formulare
from einstellungen.models import Firma

from . import zugferd
from .models import Angebot, Auftrag, Rechnung, berechne_summen

log = logging.getLogger(__name__)

ARTEN = {Angebot: "angebot", Auftrag: "auftrag", Rechnung: "rechnung"}
SPALTEN_ALLE = ["pos", "artikelnr", "bezeichnung", "menge", "einzelpreis", "rabatt", "gesamt"]


def zahl(wert, stellen=2) -> str:
    """Deutsche Zahl: 1.234,50 (Nachkommastellen ohne Zwang bei Mengen)."""
    text = f"{Decimal(wert):,.{stellen}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def menge_text(wert) -> str:
    text = zahl(wert, 2)
    return text[:-3] if text.endswith(",00") else text


def geld(wert) -> str:
    return f"{zahl(wert)} €"


def datum_text(d) -> str:
    return d.strftime("%d.%m.%Y") if d else ""


def _beleginfos(beleg, art):
    """Datumszeilen oberhalb der Positionen."""
    zeilen = [("Datum", datum_text(beleg.datum))]
    if art == "angebot":
        gueltig = beleg.gueltig_bis
        if gueltig:
            zeilen.append(("Gültig bis", datum_text(gueltig)))
    elif art == "rechnung":
        if beleg.zeitraum_von and beleg.zeitraum_bis:
            zeilen.append(("Leistungszeitraum", f"{datum_text(beleg.zeitraum_von)} – {datum_text(beleg.zeitraum_bis)}"))
        elif beleg.leistungsdatum:
            zeilen.append(("Leistungsdatum", datum_text(beleg.leistungsdatum)))
        if beleg.faellig_am:
            zeilen.append(("Zahlungsziel", datum_text(beleg.faellig_am)))
    return zeilen


def kontext(beleg) -> dict:
    art = ARTEN[type(beleg)]
    e = formulare.alle(art)
    firma = Firma.holen()
    positionen = list(beleg.positionen.all())
    summen = berechne_summen(positionen)
    spalten = [s for s in (e.get("spalten_abweichend") or e["spalten"]).split(",") if s in SPALTEN_ALLE]
    if "bezeichnung" not in spalten:
        spalten.insert(0, "bezeichnung")
    kunde = beleg.kunde
    empfaenger = [kunde.firma] if kunde.firma else []
    if kunde.vorname or kunde.nachname:
        empfaenger.append(f"{kunde.vorname} {kunde.nachname}".strip())
    empfaenger += [kunde.strasse, f"{kunde.plz} {kunde.ort}".strip()]
    if kunde.land and kunde.land.lower() not in ("deutschland", "germany"):
        empfaenger.append(kunde.land)
    rand_unten = briefbogen.unterer_rand_mm(firma, float(e["rand_unten"]))
    elemente = briefbogen.elemente_fuer_pdf(firma, float(e["rand_links"]), float(e["rand_oben"]), rand_unten)
    return {
        "art": art, "beleg": beleg, "firma": firma, "e": e,
        "titel": e["titel"], "positionen": positionen, "summen": summen, "spalten": spalten,
        "empfaenger": [z for z in empfaenger if z], "infos": _beleginfos(beleg, art),
        "schrift": formulare.SCHRIFTARTEN.get(e["schriftart"], formulare.SCHRIFTARTEN["Helvetica"]),
        "briefbogen": elemente, "rand_unten": rand_unten,
        "mehrere_steuersaetze": len(summen.gruppen) > 1,
        "befreiung": kunde.steuerbefreit, "befreiungsgrund": (kunde.befreiungsgrund or "").strip(),
        "rand_oben": e["rand_oben"],
    }


def beleg_pdf(beleg) -> bytes:
    """Fertiges PDF; Rechnungen enthalten das ZUGFeRD-XML (PDF/A-3)."""
    ctx = kontext(beleg)
    html = render_to_string("belege/pdf/beleg.html", ctx)
    pdf = HTML(string=html, base_url=str(Path.cwd())).write_pdf()
    if isinstance(beleg, Rechnung):
        pdf = zugferd.in_pdf_einbetten(pdf, zugferd.rechnung_xml(beleg))
    return pdf


def briefbogen_vorschau() -> bytes:
    """Leere A4-Seite nur mit den Briefbogen-Elementen (zum Prüfen der Positionen)."""
    e = formulare.alle("rechnung")
    firma = Firma.holen()
    rand_unten = briefbogen.unterer_rand_mm(firma, float(e["rand_unten"]))
    ctx = {
        "e": e, "firma": firma, "rand_unten": rand_unten, "vorschau": True,
        "briefbogen": briefbogen.elemente_fuer_pdf(firma, float(e["rand_links"]), float(e["rand_oben"]), rand_unten),
    }
    return HTML(string=render_to_string("belege/pdf/briefbogen_vorschau.html", ctx)).write_pdf()


def dateiname(beleg) -> str:
    return f"{beleg.nummer}.pdf"
