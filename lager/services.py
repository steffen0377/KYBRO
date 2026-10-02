"""Lagerlogik: Bestandsänderungen, Wareneingang, Korrektur, Seriennummern.

Alle Funktionen laufen in einer Transaktion und sperren die Artikelzeile
(``select_for_update``), damit gleichzeitige Buchungen keinen Bestand verlieren.
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import F

from stammdaten.models import Artikel

from .models import Lagerbewegung, Seriennummer


class LagerFehler(Exception):
    """Fachlicher Fehler; die Meldung ist für den Anwender bestimmt."""


@transaction.atomic
def bestand_aendern(
    artikel: Artikel,
    delta,
    typ: str,
    bezug_typ: str = "",
    bezug_id: int | None = None,
    notiz: str = "",
    benutzer=None,
):
    """Ändert den Bestand um ``delta`` und protokolliert die Bewegung.

    Artikel ohne Lagerführung (z. B. Dienstleistungen) werden übersprungen;
    dann wird ``None`` zurückgegeben.
    """
    delta = Decimal(delta)
    gesperrt = Artikel.objects.select_for_update().get(pk=artikel.pk)
    if not gesperrt.lagerfuehrung:
        return None
    Artikel.objects.filter(pk=gesperrt.pk).update(bestand=F("bestand") + delta)
    artikel.refresh_from_db(fields=["bestand"])
    return Lagerbewegung.objects.create(
        artikel=gesperrt,
        typ=typ,
        menge=delta,
        bezug_typ=bezug_typ,
        bezug_id=bezug_id,
        notiz=notiz[:255],
        benutzer=benutzer,
    )


@transaction.atomic
def wareneingang(artikel: Artikel, menge, notiz: str = "", benutzer=None):
    """Wareneingang ohne Seriennummern."""
    menge = Decimal(menge)
    if artikel.seriennummern:
        raise LagerFehler(
            'Dieser Artikel benötigt Seriennummern – bitte "Wareneingang mit Seriennummern" nutzen.'
        )
    if not artikel.lagerfuehrung:
        raise LagerFehler("Für diesen Artikel wird kein Lagerbestand geführt.")
    if menge <= 0:
        raise LagerFehler("Die Menge muss größer als 0 sein.")
    return bestand_aendern(
        artikel, menge, Lagerbewegung.Typ.EINLAGERUNG, "manual", None,
        notiz or "Wareneingang", benutzer,
    )


@transaction.atomic
def inventurkorrektur(artikel: Artikel, neuer_bestand, notiz: str = "", benutzer=None):
    """Setzt den Bestand auf den gezählten Ist-Bestand (nur ohne Seriennummern)."""
    neuer_bestand = Decimal(neuer_bestand)
    if artikel.seriennummern:
        raise LagerFehler(
            "Für Artikel mit Seriennummern bitte über die Seriennummern-Verwaltung korrigieren."
        )
    if not artikel.lagerfuehrung:
        raise LagerFehler("Für diesen Artikel wird kein Lagerbestand geführt.")
    if neuer_bestand < 0:
        raise LagerFehler("Der Bestand darf nicht negativ sein.")
    aktuell = Artikel.objects.select_for_update().get(pk=artikel.pk).bestand
    delta = neuer_bestand - aktuell
    if delta == 0:
        return None
    return bestand_aendern(
        artikel, delta, Lagerbewegung.Typ.KORREKTUR, "manual", None,
        notiz or "Manuelle Korrektur", benutzer,
    )


def seriennummern_aus_text(text: str) -> list[str]:
    """Eine Seriennummer pro Zeile; leere Zeilen und Dubletten fallen weg."""
    gesehen: dict[str, None] = {}
    for zeile in text.splitlines():
        nummer = zeile.strip()
        if nummer:
            gesehen.setdefault(nummer, None)
    return list(gesehen)


@transaction.atomic
def seriennummern_einlagern(artikel: Artikel, nummern: list[str], notiz: str = "", benutzer=None):
    """Lagert Seriennummern ein. Gibt (Anzahl eingelagert, bereits vorhandene) zurück."""
    if not artikel.seriennummern:
        raise LagerFehler("Für diesen Artikel ist die Seriennummern-Erfassung nicht aktiviert.")
    if not nummern:
        raise LagerFehler("Bitte mindestens eine Seriennummer angeben (eine pro Zeile).")
    vorhanden = set(
        Seriennummer.objects.filter(artikel=artikel, nummer__in=nummern).values_list("nummer", flat=True)
    )
    neue = [n for n in nummern if n not in vorhanden]
    Seriennummer.objects.bulk_create(
        [Seriennummer(artikel=artikel, nummer=n, notiz=notiz[:255]) for n in neue]
    )
    if neue:
        bestand_aendern(
            artikel, len(neue), Lagerbewegung.Typ.EINLAGERUNG, "manual", None,
            notiz or "Wareneingang", benutzer,
        )
    return len(neue), [n for n in nummern if n in vorhanden]


@transaction.atomic
def seriennummer_defekt(serie: Seriennummer, benutzer=None):
    serie = Seriennummer.objects.select_for_update().select_related("artikel").get(pk=serie.pk)
    if serie.status != Seriennummer.Status.LAGER:
        raise LagerFehler("Seriennummer ist bereits verkauft oder defekt.")
    serie.status = Seriennummer.Status.DEFEKT
    serie.save(update_fields=["status"])
    bestand_aendern(
        serie.artikel, -1, Lagerbewegung.Typ.KORREKTUR, "manual", None,
        f"Als defekt markiert: {serie.nummer}", benutzer,
    )


@transaction.atomic
def seriennummer_entfernen(serie: Seriennummer, benutzer=None):
    serie = Seriennummer.objects.select_for_update().select_related("artikel").get(pk=serie.pk)
    if serie.status != Seriennummer.Status.LAGER:
        raise LagerFehler("Seriennummer ist bereits verkauft oder defekt.")
    artikel, nummer = serie.artikel, serie.nummer
    serie.delete()
    bestand_aendern(
        artikel, -1, Lagerbewegung.Typ.KORREKTUR, "manual", None,
        f"Fälschlich erfasst, entfernt: {nummer}", benutzer,
    )
