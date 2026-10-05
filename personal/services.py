"""Berechnungen für Verträge, Arbeitstage und Urlaub."""

import datetime
from decimal import ROUND_HALF_UP, Decimal

from .kalender import Kalender
from .models import Anwesenheit, Mitarbeiter, Urlaubsantrag, Urlaubsjahr, Vertrag

STANDARD_ARBEITSTAGE = [0, 1, 2, 3, 4]


def vertrag_am(vertraege, tag: datetime.date):
    for v in vertraege:
        if v.gueltig_ab <= tag and (v.gueltig_bis is None or v.gueltig_bis >= tag):
            return v
    return None


def ist_arbeitstag(vertraege, tag: datetime.date) -> bool:
    v = vertrag_am(vertraege, tag)
    tage = v.arbeitstage_liste if v else STANDARD_ARBEITSTAGE
    return tag.weekday() in tage


def tage_zwischen(von: datetime.date, bis: datetime.date):
    for i in range((bis - von).days + 1):
        yield von + datetime.timedelta(days=i)


def arbeitstage(mitarbeiter: Mitarbeiter, von: datetime.date, bis: datetime.date) -> list[datetime.date]:
    vertraege = list(mitarbeiter.vertraege.all())
    return [t for t in tage_zwischen(von, bis) if ist_arbeitstag(vertraege, t)]


def _halbe(wert: Decimal) -> Decimal:
    return (wert * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / 2


def urlaub_anspruch(mitarbeiter: Mitarbeiter, jahr: int) -> Decimal:
    """Manueller Anspruch, sonst Vertragsanspruch (anteilig bei Eintritt oder Austritt im Jahr)."""
    manuell = Urlaubsjahr.objects.filter(mitarbeiter=mitarbeiter, jahr=jahr).first()
    if manuell and manuell.anspruch is not None:
        return manuell.anspruch
    anfang, ende = datetime.date(jahr, 1, 1), datetime.date(jahr, 12, 31)
    vertraege = list(mitarbeiter.vertraege.all())
    v = vertrag_am(vertraege, anfang) or next(
        (x for x in sorted(vertraege, key=lambda x: x.gueltig_ab) if anfang <= x.gueltig_ab <= ende), None
    )
    if not v:
        return Decimal("0")
    monate = 12
    if mitarbeiter.eintrittsdatum and mitarbeiter.eintrittsdatum > anfang and mitarbeiter.eintrittsdatum.year == jahr:
        monate -= mitarbeiter.eintrittsdatum.month - 1
    if mitarbeiter.austrittsdatum and mitarbeiter.austrittsdatum.year == jahr:
        monate -= 12 - mitarbeiter.austrittsdatum.month
    monate = max(monate, 0)
    if monate == 12:
        return v.urlaubstage_pro_jahr
    return _halbe(v.urlaubstage_pro_jahr * monate / 12)


def _urlaubstage(mitarbeiter: Mitarbeiter, von: datetime.date, bis: datetime.date, kalender: Kalender, vertraege) -> dict:
    """Urlaubskosten je Tag (1, 0,5 an halben Tagen, 0 an Feiertagen) für alle Arbeitstage im Zeitraum."""
    return {t: kalender.anteil(t) for t in tage_zwischen(von, bis) if ist_arbeitstag(vertraege, t)}


def urlaubstage_im_jahr(mitarbeiter: Mitarbeiter, jahr: int, stati, kalender: Kalender | None = None) -> Decimal:
    kalender = kalender or Kalender()
    anfang, ende = datetime.date(jahr, 1, 1), datetime.date(jahr, 12, 31)
    vertraege = list(mitarbeiter.vertraege.all())
    gezaehlt = {}
    for a in mitarbeiter.urlaubsantraege.filter(status__in=stati, von__lte=ende, bis__gte=anfang):
        gezaehlt.update(_urlaubstage(mitarbeiter, max(a.von, anfang), min(a.bis, ende), kalender, vertraege))
    return sum(gezaehlt.values(), Decimal("0"))


def antrag_tage(mitarbeiter: Mitarbeiter, antrag: Urlaubsantrag, kalender: Kalender | None = None) -> Decimal:
    kalender = kalender or Kalender()
    vertraege = list(mitarbeiter.vertraege.all())
    return sum(_urlaubstage(mitarbeiter, antrag.von, antrag.bis, kalender, vertraege).values(), Decimal("0"))


def urlaubskonto(mitarbeiter: Mitarbeiter, jahr: int, kalender: Kalender | None = None) -> dict:
    kalender = kalender or Kalender()
    jahresdaten = Urlaubsjahr.objects.filter(mitarbeiter=mitarbeiter, jahr=jahr).first()
    anspruch = urlaub_anspruch(mitarbeiter, jahr)
    uebertrag = jahresdaten.uebertrag if jahresdaten else Decimal("0")
    genommen = urlaubstage_im_jahr(mitarbeiter, jahr, [Urlaubsantrag.Status.GENEHMIGT], kalender)
    beantragt = urlaubstage_im_jahr(mitarbeiter, jahr, [Urlaubsantrag.Status.BEANTRAGT], kalender)
    return {
        "jahr": jahr, "anspruch": anspruch, "uebertrag": uebertrag, "gesamt": anspruch + uebertrag,
        "genommen": genommen, "beantragt": beantragt,
        "rest": anspruch + uebertrag - genommen, "rest_nach_antraegen": anspruch + uebertrag - genommen - beantragt,
    }


def monatsuebersicht(mitarbeiter_liste, jahr: int, monat: int, kalender: Kalender | None = None) -> dict:
    """Matrix Mitarbeiter x Tage mit Status (Kürzel) für die Monatsansicht."""
    import calendar

    kalender = kalender or Kalender()
    anzahl = calendar.monthrange(jahr, monat)[1]
    tage = [datetime.date(jahr, monat, t) for t in range(1, anzahl + 1)]
    erster, letzter = tage[0], tage[-1]
    zeilen = []
    for m in mitarbeiter_liste:
        vertraege = list(m.vertraege.all())
        eintraege = {a.datum: a for a in m.anwesenheiten.filter(datum__range=(erster, letzter))}
        urlaub = {}
        for a in m.urlaubsantraege.filter(
            status__in=[Urlaubsantrag.Status.GENEHMIGT, Urlaubsantrag.Status.BEANTRAGT], von__lte=letzter, bis__gte=erster
        ):
            for t in tage_zwischen(max(a.von, erster), min(a.bis, letzter)):
                urlaub[t] = a.status
        zellen = []
        for t in tage:
            if t in eintraege:
                e = eintraege[t]
                zellen.append({"datum": t, "status": e.status, "text": e.get_status_display()})
            elif (feiertag := kalender.info(t)) and feiertag[1] == 0 and ist_arbeitstag(vertraege, t):
                zellen.append({"datum": t, "status": "feiertag", "text": feiertag[0]})
            elif t in urlaub and ist_arbeitstag(vertraege, t):
                zellen.append({
                    "datum": t, "status": "urlaub" if urlaub[t] == "genehmigt" else "urlaub_offen",
                    "text": "Urlaub" if urlaub[t] == "genehmigt" else "Urlaub (beantragt)",
                })
            elif not ist_arbeitstag(vertraege, t) or not m.ist_aktiv(t):
                zellen.append({"datum": t, "status": "frei", "text": ""})
            else:
                halb = kalender.info(t)
                zellen.append({"datum": t, "status": "", "text": f"{halb[0]} (halber Tag)" if halb else ""})
        zeilen.append({"mitarbeiter": m, "zellen": zellen})
    return {"tage": tage, "zeilen": zeilen}
