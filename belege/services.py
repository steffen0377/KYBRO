"""Geschäftslogik der Belege: Nummern, Umwandlungen, Lagerbuchung, Status.

Alle öffentlichen Funktionen laufen in einer Transaktion. Fachliche Fehler
werden als ``BelegFehler`` mit einer für den Anwender lesbaren Meldung gemeldet.
"""

from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from einstellungen.models import Firma, Nummernkreis
from einstellungen.services import naechste_belegnummer
from lager.models import Lagerbewegung, Seriennummer
from lager.services import bestand_aendern

from .models import (
    Abo,
    Angebot,
    Auftrag,
    AuftragPosition,
    Rechnung,
    RechnungPosition,
)


class BelegFehler(Exception):
    """Fachlicher Fehler; die Meldung ist für den Anwender bestimmt."""


# ---------------------------------------------------------------------------
# Positionen
# ---------------------------------------------------------------------------


def positionen_uebernehmen(quelle, ziel, positionsmodell, fremdschluessel: str):
    """Kopiert alle Positionen von ``quelle`` auf ``ziel`` (z. B. Auftrag -> Rechnung)."""
    positionsmodell.objects.bulk_create(
        [positionsmodell(**{fremdschluessel: ziel}, **p.daten_kopieren()) for p in quelle.positionen.all()]
    )


def positionen_nummerieren(beleg):
    for nummer, position in enumerate(beleg.positionen.order_by("position", "pk"), start=1):
        if position.position != nummer:
            position.position = nummer
            position.save(update_fields=["position"])


# ---------------------------------------------------------------------------
# Angebot -> Auftrag
# ---------------------------------------------------------------------------


@transaction.atomic
def auftrag_aus_angebot(angebot: Angebot, benutzer=None) -> tuple[Auftrag, bool]:
    """Liefert den Auftrag zum Angebot; legt ihn an, falls es noch keinen gibt.

    Das Angebot gilt danach als angenommen. Gibt ``(auftrag, neu_angelegt)`` zurück.
    """
    bestehend = Auftrag.objects.filter(angebot=angebot).first()
    if bestehend:
        _angebot_annehmen(angebot)
        return bestehend, False
    heute = timezone.localdate()
    auftrag = Auftrag.objects.create(
        nummer=naechste_belegnummer(Nummernkreis.Art.AUFTRAG, heute),
        angebot=angebot,
        kunde=angebot.kunde,
        datum=heute,
        notizen=angebot.notizen,
        erstellt_von=benutzer,
    )
    positionen_uebernehmen(angebot, auftrag, AuftragPosition, "auftrag")
    auftrag.summen_neu_berechnen()
    _angebot_annehmen(angebot)
    return auftrag, True


def _angebot_annehmen(angebot: Angebot):
    if angebot.status != Angebot.Status.ANGENOMMEN:
        angebot.status = Angebot.Status.ANGENOMMEN
        angebot.save(update_fields=["status"])


@transaction.atomic
def angebot_status_aendern(angebot: Angebot, neuer_status: str, benutzer=None) -> Auftrag | None:
    """Ändert den Status. Der Wechsel auf "angenommen" legt den Auftrag an."""
    if neuer_status not in Angebot.Status.values:
        raise BelegFehler("Unbekannter Status.")
    alt = angebot.status
    if neuer_status == Angebot.Status.ANGENOMMEN and alt != Angebot.Status.ANGENOMMEN:
        return auftrag_aus_angebot(angebot, benutzer)[0]
    angebot.status = neuer_status
    angebot.save(update_fields=["status"])
    return None


# ---------------------------------------------------------------------------
# Rechnung: Lager
# ---------------------------------------------------------------------------


def lager_buchen(rechnung: Rechnung, benutzer=None) -> None:
    """Bucht den Verkauf der Rechnungspositionen aus dem Lager aus.

    Artikel mit Seriennummern werden hier übersprungen: Ihr Bestand sinkt erst,
    wenn die verkauften Seriennummern zugeordnet werden.
    """
    if not rechnung.lagerbuchung:
        return
    for position in rechnung.positionen.select_related("artikel"):
        artikel = position.artikel
        if artikel is None or artikel.seriennummern:
            continue
        bestand_aendern(
            artikel, -position.menge, Lagerbewegung.Typ.VERKAUF, "rechnung", rechnung.pk,
            f"Verkauf über Rechnung {rechnung.nummer}", benutzer,
        )


@transaction.atomic
def lager_zuruecknehmen(rechnung: Rechnung, benutzer=None) -> None:
    """Macht alle Lagerbuchungen dieser Rechnung rückgängig (Entwurf geändert/gelöscht).

    Zugeordnete Seriennummern werden wieder frei.
    """
    for serie in Seriennummer.objects.select_for_update().filter(rechnung=rechnung):
        serie.status = Seriennummer.Status.LAGER
        serie.rechnung = None
        serie.verkauft_am = None
        serie.save(update_fields=["status", "rechnung", "verkauft_am"])
    from django.db.models import Sum

    summen = (
        Lagerbewegung.objects.filter(bezug_typ="rechnung", bezug_id=rechnung.pk)
        .values("artikel")
        .annotate(summe=Sum("menge"))
    )
    from stammdaten.models import Artikel

    for zeile in summen:
        if zeile["summe"]:
            bestand_aendern(
                Artikel.objects.get(pk=zeile["artikel"]), -zeile["summe"], Lagerbewegung.Typ.KORREKTUR,
                "rechnung", rechnung.pk, f"Lagerbuchung zurückgenommen (Rechnung {rechnung.nummer})", benutzer,
            )


def offene_seriennummern(rechnung: Rechnung) -> list[dict]:
    """Seriennummernartikel der Rechnung, für die noch Seriennummern fehlen.

    Jeder Eintrag: ``{"artikel": Artikel, "offen": int}``.
    """
    benoetigt: "OrderedDict[int, dict]" = OrderedDict()
    for position in rechnung.positionen.select_related("artikel"):
        if position.artikel and position.artikel.seriennummern:
            eintrag = benoetigt.setdefault(position.artikel_id, {"artikel": position.artikel, "menge": Decimal(0)})
            eintrag["menge"] += position.menge
    ergebnis = []
    for artikel_id, eintrag in benoetigt.items():
        zugeordnet = Seriennummer.objects.filter(rechnung=rechnung, artikel_id=artikel_id).count()
        offen = int(eintrag["menge"]) - zugeordnet
        if offen > 0:
            ergebnis.append({"artikel": eintrag["artikel"], "offen": offen})
    return ergebnis


@transaction.atomic
def seriennummern_zuordnen(rechnung: Rechnung, auswahl: dict[int, list[int]], benutzer=None) -> list[dict]:
    """Ordnet verkaufte Seriennummern der Rechnung zu und bucht den Bestand aus.

    ``auswahl``: Artikel-ID -> IDs der gewählten Seriennummern. Gibt die noch
    offenen Positionen zurück (leer, wenn alles zugeordnet ist).
    """
    if rechnung.status == Rechnung.Status.STORNIERT:
        raise BelegFehler("Eine stornierte Rechnung kann keine Seriennummern erhalten.")
    offen = {e["artikel"].pk: e["offen"] for e in offene_seriennummern(rechnung)}
    for artikel_id, serien_ids in auswahl.items():
        serien_ids = list(dict.fromkeys(serien_ids))
        if not serien_ids:
            continue
        if artikel_id not in offen:
            raise BelegFehler("Für einen der gewählten Artikel werden keine Seriennummern benötigt.")
        if len(serien_ids) > offen[artikel_id]:
            raise BelegFehler(
                f"Zu viele Seriennummern gewählt: Es werden nur noch {offen[artikel_id]} benötigt."
            )
        serien = list(
            Seriennummer.objects.select_for_update().filter(
                pk__in=serien_ids, artikel_id=artikel_id, status=Seriennummer.Status.LAGER
            )
        )
        if len(serien) != len(serien_ids):
            raise BelegFehler("Mindestens eine gewählte Seriennummer ist nicht mehr im Lager verfügbar.")
        for serie in serien:
            serie.status = Seriennummer.Status.VERKAUFT
            serie.rechnung = rechnung
            serie.verkauft_am = timezone.now()
            serie.save(update_fields=["status", "rechnung", "verkauft_am"])
            bestand_aendern(
                serie.artikel, -1, Lagerbewegung.Typ.VERKAUF, "rechnung", rechnung.pk,
                f"Verkauf über Rechnung {rechnung.nummer} (S/N: {serie.nummer})", benutzer,
            )
    return offene_seriennummern(rechnung)


# ---------------------------------------------------------------------------
# Auftrag -> Rechnung
# ---------------------------------------------------------------------------


def faelligkeit(datum):
    return datum + timedelta(days=Firma.holen().zahlungsziel_tage)


@transaction.atomic
def rechnung_aus_auftrag(auftrag: Auftrag, benutzer=None) -> Rechnung:
    """Erstellt aus dem Auftrag eine Rechnung im Entwurfsstatus.

    Der Lagerbestand sinkt sofort (außer bei Seriennummernartikeln, siehe
    ``lager_buchen``); der Auftrag gilt danach als abgeschlossen.
    """
    if auftrag.status == Auftrag.Status.STORNIERT:
        raise BelegFehler("Ein stornierter Auftrag kann nicht abgerechnet werden.")
    if auftrag.abgerechnet:
        raise BelegFehler("Zu diesem Auftrag existiert bereits eine Rechnung.")
    heute = timezone.localdate()
    rechnung = Rechnung.objects.create(
        nummer=naechste_belegnummer(Nummernkreis.Art.RECHNUNG, heute),
        angebot=auftrag.angebot,
        auftrag=auftrag,
        kunde=auftrag.kunde,
        datum=heute,
        faellig_am=faelligkeit(heute),
        notizen=auftrag.notizen,
        erstellt_von=benutzer,
    )
    positionen_uebernehmen(auftrag, rechnung, RechnungPosition, "rechnung")
    rechnung.summen_neu_berechnen()
    lager_buchen(rechnung, benutzer)
    auftrag.status = Auftrag.Status.ABGESCHLOSSEN
    auftrag.save(update_fields=["status"])
    return rechnung


@transaction.atomic
def rechnung_aus_angebot(angebot: Angebot, benutzer=None) -> tuple[Auftrag, Rechnung]:
    """Schnellweg Angebot -> Auftrag (falls nötig) -> Rechnung."""
    auftrag, _ = auftrag_aus_angebot(angebot, benutzer)
    return auftrag, rechnung_aus_auftrag(auftrag, benutzer)


# ---------------------------------------------------------------------------
# Rechnung: Anlegen, Ändern, Löschen, Status
# ---------------------------------------------------------------------------


@transaction.atomic
def rechnung_nach_bearbeiten(rechnung: Rechnung, neu: bool, benutzer=None) -> None:
    """Nachbereitung, nachdem Kopf und Positionen einer Entwurfsrechnung gespeichert wurden.

    Neue Rechnung: Nummer wurde bereits vergeben. Bei jeder Speicherung werden
    Summen berechnet und das Lager neu gebucht (alte Buchungen werden zuvor
    zurückgenommen, damit Änderungen den Bestand nicht verfälschen).
    """
    positionen_nummerieren(rechnung)
    rechnung.summen_neu_berechnen()
    if not neu:
        lager_zuruecknehmen(rechnung, benutzer)
    lager_buchen(rechnung, benutzer)


@transaction.atomic
def rechnung_loeschen(rechnung: Rechnung, benutzer=None) -> None:
    if not rechnung.ist_entwurf:
        raise BelegFehler("Nur Entwürfe können gelöscht werden.")
    lager_zuruecknehmen(rechnung, benutzer)
    rechnung.delete()


@transaction.atomic
def rechnung_status_aendern(rechnung: Rechnung, neuer_status: str, benutzer=None) -> None:
    """Ändert den Status einer Rechnung.

    * Zurück in den Entwurf ist nicht möglich (GoBD: ausgestellte Rechnungen bleiben unverändert).
    * Beim ersten Verlassen des Entwurfs werden Abonnements aus den Positionen angelegt,
      bzw. bei einer Abo-Rechnung wird der nächste Abrechnungstermin fortgeschrieben.
    * Ein Entwurf, der direkt storniert wird, war nie ausgestellt: Seine Lagerbuchungen
      werden zurückgenommen und es entstehen keine Abonnements.
    """
    from .abos import abo_termin_weiterschalten, abos_aus_rechnung_anlegen

    if neuer_status not in Rechnung.Status.values:
        raise BelegFehler("Unbekannter Status.")
    alt = rechnung.status
    if neuer_status == alt:
        return
    if neuer_status == Rechnung.Status.ENTWURF:
        raise BelegFehler("Eine ausgestellte Rechnung kann nicht zurück in den Entwurf gesetzt werden.")
    if alt == Rechnung.Status.ENTWURF:
        if rechnung.abo_id:
            abo_termin_weiterschalten(rechnung.abo)
        elif neuer_status == Rechnung.Status.STORNIERT:
            lager_zuruecknehmen(rechnung, benutzer)
        else:
            abos_aus_rechnung_anlegen(rechnung)
    rechnung.status = neuer_status
    rechnung.save(update_fields=["status"])
