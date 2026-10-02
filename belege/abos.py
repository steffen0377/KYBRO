"""Abonnements: Anlegen aus Rechnungspositionen, Kündigung, Entwurfsrechnungen.

Das Verhalten folgt der bisherigen PHP-Anwendung, mit zwei Verbesserungen:
Termine werden stets vom Abo-Beginn aus gerechnet (keine Verschiebung am
Monatsende) und die Menge einer Position fließt in den Abo-Preis ein.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from einstellungen.models import Nummernkreis
from einstellungen.services import naechste_belegnummer

from .models import Abo, Abrechnung, Rechnung, RechnungPosition, monate_addieren, runden

STANDARD_KUENDIGUNGSFRIST_TAGE = 30


@transaction.atomic
def abos_aus_rechnung_anlegen(rechnung: Rechnung) -> list[Abo]:
    """Legt je Abo-Position (monatlich/jährlich, mit Artikel) ein Abonnement an.

    Wird beim ersten Verlassen des Entwurfs aufgerufen; ein zweiter Aufruf
    legt nichts doppelt an.
    """
    if Abo.objects.filter(ursprungsrechnung=rechnung).exists():
        return []
    angelegt = []
    for position in rechnung.positionen.select_related("artikel", "preisoption"):
        if not position.ist_abo or position.artikel is None:
            continue  # Abos gibt es nur für echte Artikel, nicht für Freitext-Positionen
        zyklus = Abo.Zyklus.JAEHRLICH if position.abrechnung == Abrechnung.JAEHRLICH else Abo.Zyklus.MONATLICH
        option = position.preisoption
        mindestlaufzeit = option.mindestlaufzeit_monate if option else None
        frist = option.kuendigungsfrist_tage if option and option.kuendigungsfrist_tage is not None else STANDARD_KUENDIGUNGSFRIST_TAGE
        beginn = rechnung.datum
        abo = Abo(
            kunde=rechnung.kunde, artikel=position.artikel, preisoption=option, auftrag=rechnung.auftrag,
            ursprungsrechnung=rechnung, zyklus=zyklus, menge=position.menge,
            # Nach Rabatt je Einheit, damit der Folgepreis dem Preis der ersten Rechnung entspricht.
            preis=runden(position.einzelpreis * (Decimal(100) - position.rabatt) / Decimal(100)),
            beginn=beginn, naechste_abrechnung=monate_addieren(beginn, 12 if zyklus == Abo.Zyklus.JAEHRLICH else 1),
            mindestlaufzeit_monate=mindestlaufzeit, kuendigungsfrist_tage=frist,
            fruehestes_ende=monate_addieren(beginn, mindestlaufzeit) if mindestlaufzeit else None,
        )
        abo.save()
        angelegt.append(abo)
    return angelegt


def kuendigung_berechnen(abo: Abo, eingang: date | None = None) -> dict:
    """Wann endet das Abo bei Kündigung am ``eingang``?

    Frühestens nach Ablauf der Mindestlaufzeit UND der Kündigungsfrist, aufgerundet
    auf den nächsten regulären Abrechnungstermin, damit das Ende immer mit einem
    Abrechnungszeitraum zusammenfällt.
    """
    eingang = eingang or timezone.localdate()
    frueheste = eingang + timedelta(days=abo.kuendigungsfrist_tage or 0)
    if abo.fruehestes_ende and abo.fruehestes_ende > frueheste:
        frueheste = abo.fruehestes_ende
    schritt = abo.zyklus_monate
    k = 0
    wirksam = abo.beginn
    while wirksam < frueheste:
        k += 1
        wirksam = monate_addieren(abo.beginn, k * schritt)
    return {"kuendigung_eingang": eingang, "kuendigung_wirksam": wirksam}


@transaction.atomic
def abo_kuendigen(abo: Abo, eingang: date | None = None) -> Abo:
    if abo.status != Abo.Status.AKTIV:
        raise ValueError("Nur aktive Abonnements können gekündigt werden.")
    ergebnis = kuendigung_berechnen(abo, eingang)
    abo.kuendigung_eingang = ergebnis["kuendigung_eingang"]
    abo.kuendigung_wirksam = ergebnis["kuendigung_wirksam"]
    abo.status = Abo.Status.GEKUENDIGT
    abo.save(update_fields=["kuendigung_eingang", "kuendigung_wirksam", "status", "geaendert"])
    return abo


@transaction.atomic
def abo_kuendigung_zuruecknehmen(abo: Abo) -> Abo:
    if abo.status != Abo.Status.GEKUENDIGT:
        raise ValueError("Nur gekündigte Abonnements können reaktiviert werden.")
    abo.kuendigung_eingang = None
    abo.kuendigung_wirksam = None
    abo.status = Abo.Status.AKTIV
    abo.save(update_fields=["kuendigung_eingang", "kuendigung_wirksam", "status", "geaendert"])
    return abo


def abo_termin_weiterschalten(abo: Abo) -> None:
    """Schreibt den nächsten Abrechnungstermin um einen Zyklus fort (nach Freigabe der Entwurfsrechnung)."""
    abo.naechste_abrechnung = abo.termin_nach(abo.naechste_abrechnung)
    abo.save(update_fields=["naechste_abrechnung", "geaendert"])


@transaction.atomic
def abo_rechnungen_erzeugen(heute: date | None = None) -> list[Rechnung]:
    """Beendet wirksam gekündigte Abos und erzeugt Entwurfsrechnungen für fällige Abos.

    Der Abrechnungstermin wird hier bewusst nicht verändert, sondern erst bei
    Freigabe des Entwurfs. Dadurch ist der Lauf idempotent: Mehrfaches Ausführen
    am selben Tag erzeugt keine doppelten Entwürfe.
    """
    heute = heute or timezone.localdate()
    Abo.objects.filter(status=Abo.Status.GEKUENDIGT, kuendigung_wirksam__lte=heute).update(
        status=Abo.Status.BEENDET, ende=F("kuendigung_wirksam")
    )
    erzeugt = []
    faellige = Abo.objects.select_for_update().select_related("kunde", "artikel").filter(
        status__in=[Abo.Status.AKTIV, Abo.Status.GEKUENDIGT], naechste_abrechnung__lte=heute
    )
    for abo in faellige:
        if abo.kuendigung_wirksam and abo.naechste_abrechnung >= abo.kuendigung_wirksam:
            continue
        if Rechnung.objects.filter(abo=abo, zeitraum_von=abo.naechste_abrechnung).exists():
            continue
        erzeugt.append(_entwurf_fuer_abo(abo, heute))
    return erzeugt


def _entwurf_fuer_abo(abo: Abo, heute: date) -> Rechnung:
    from .services import faelligkeit

    von = abo.naechste_abrechnung
    bis = abo.termin_nach(von) - timedelta(days=1)
    steuersatz = Decimal("0.00") if abo.kunde.steuerbefreit else abo.artikel.steuersatz
    zeitraum = f"{von:%d.%m.%Y} - {bis:%d.%m.%Y}"
    rechnung = Rechnung.objects.create(
        nummer=naechste_belegnummer(Nummernkreis.Art.RECHNUNG, heute),
        kunde=abo.kunde, abo=abo, datum=heute, faellig_am=faelligkeit(heute),
        leistungsdatum=von, zeitraum_von=von, zeitraum_bis=bis, lagerbuchung=False,
        notizen=f"Automatisch erzeugte Abo-Rechnung für den Zeitraum {zeitraum}. Bitte prüfen und freigeben.",
    )
    RechnungPosition.objects.create(
        rechnung=rechnung, position=1, artikel=abo.artikel, artikelnummer=abo.artikel.artikelnummer,
        beschreibung=f"{abo.artikel.name} (Abo {zeitraum})"[:255], einheit=abo.artikel.einheit,
        menge=abo.menge, einzelpreis=abo.preis, steuersatz=steuersatz,
        abrechnung=abo.zyklus, preisoption=abo.preisoption,
    )
    rechnung.summen_neu_berechnen()
    return rechnung
