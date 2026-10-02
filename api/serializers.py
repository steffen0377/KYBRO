"""Umwandlung der Datensätze in JSON-taugliche Dictionaries."""

from decimal import Decimal


def _z(wert):
    return None if wert is None else str(wert)


def zeit(wert):
    return wert.isoformat() if wert else None


def kunde(k, mit_kontakten=False) -> dict:
    daten = {
        "id": k.pk, "kundennummer": k.kundennummer, "firma": k.firma, "vorname": k.vorname, "nachname": k.nachname,
        "anzeigename": k.anzeigename, "strasse": k.strasse, "plz": k.plz, "ort": k.ort, "land": k.land,
        "email": k.email, "telefon": k.telefon, "steuerbefreit": k.steuerbefreit, "geaendert": zeit(k.geaendert),
    }
    if mit_kontakten:
        daten["ansprechpartner"] = [
            {"id": a.pk, "vorname": a.vorname, "nachname": a.nachname, "firma": a.firma, "telefon": a.telefon, "email": a.email}
            for a in k.ansprechpartner.all()
        ]
    return daten


def artikel(a) -> dict:
    return {
        "id": a.pk, "artikelnummer": a.artikelnummer, "ean": a.ean, "name": a.name, "beschreibung": a.beschreibung,
        "einheit": a.einheit, "verkaufspreis": _z(a.verkaufspreis), "steuersatz": _z(a.steuersatz),
        "bestand": _z(a.bestand), "lagerfuehrung": a.lagerfuehrung, "seriennummern": a.seriennummern,
        "aktiv": a.aktiv, "geaendert": zeit(a.geaendert),
        "preisoptionen": [
            {"id": o.pk, "abrechnung": o.abrechnung, "preis": _z(o.preis)} for o in a.preisoptionen.all() if o.aktiv
        ],
    }


def position(p) -> dict:
    return {
        "id": p.pk, "client_uuid": str(p.client_uuid) if getattr(p, "client_uuid", None) else None,
        "position": p.position, "artikel_id": p.artikel_id, "artikelnummer": p.artikelnummer,
        "beschreibung": p.beschreibung, "einheit": p.einheit, "menge": _z(p.menge), "einzelpreis": _z(p.einzelpreis),
        "rabatt": _z(p.rabatt), "steuersatz": _z(p.steuersatz), "abrechnung": p.abrechnung, "netto": _z(p.netto),
    }


def beleg(b, **extra) -> dict:
    daten = {
        "id": b.pk, "nummer": b.nummer, "kunde_id": b.kunde_id, "datum": b.datum.isoformat(), "status": b.status,
        "notizen": b.notizen, "netto": _z(b.netto), "steuer": _z(b.steuer), "brutto": _z(b.brutto),
        "positionen": [position(p) for p in b.positionen.all()],
    }
    daten.update(extra)
    return daten


def auftrag(a) -> dict:
    return beleg(
        a, angebot_id=a.angebot_id, client_uuid=str(a.client_uuid) if a.client_uuid else None,
        unterschrieben_am=zeit(a.unterschrieben_am), unterschrieben_von=a.unterschrieben_von,
        hat_unterschrift=bool(a.unterschrift), abgerechnet=a.abgerechnet, geaendert=zeit(a.geaendert),
    )


def rechnung(r) -> dict:
    return beleg(
        r, auftrag_id=r.auftrag_id, faellig_am=r.faellig_am.isoformat() if r.faellig_am else None,
        leistungsdatum=r.leistungsdatum.isoformat() if r.leistungsdatum else None,
    )
