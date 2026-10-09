"""Welche Kalender es gibt und welche Ereignisse sie enthalten.

* Eigene Kalender (``Kalender``/``Termin``), Schlüssel ``k<id>``.
* Systemkalender aus der Personalverwaltung: ``urlaub`` (genehmigter Urlaub) und ``anwesenheit`` (Homeoffice, Dienstreise,
  Berufsschule, Schulung, Sonderurlaub, Freizeitausgleich). Krankheit, Über-/Fehlstunden und Bemerkungen gehören nie dazu.

Systemkalender sehen nur Benutzer mit Leserecht für „Personal“.
"""

import datetime
from dataclasses import dataclass

from django.utils import timezone

from accounts.modules import AKTION_LESEN

from .models import Kalender, Termin

FENSTER_VOR_TAGE = 90
FENSTER_NACH_TAGE = 540

ANWESENHEIT_IM_KALENDER = {
    "homeoffice": "Homeoffice",
    "dienstreise": "Dienstreise",
    "berufsschule": "Berufsschule",
    "schulung": "Schulung",
    "sonderurlaub": "Sonderurlaub",
    "freizeitausgleich": "Freizeitausgleich",
}


@dataclass(frozen=True)
class Quelle:
    schluessel: str
    name: str
    farbe: str
    beschreibung: str = ""
    system: bool = False


SYSTEMKALENDER = (
    Quelle("urlaub", "Urlaub", "#f59e0b", "Genehmigter Urlaub aller Mitarbeiter", system=True),
    Quelle("anwesenheit", "Anwesenheit", "#10b981", "Homeoffice, Dienstreise, Schulung u. Ä. (ohne Krankheit)", system=True),
)


def standardfenster(heute: datetime.date | None = None) -> tuple[datetime.date, datetime.date]:
    heute = heute or timezone.localdate()
    return heute - datetime.timedelta(days=FENSTER_VOR_TAGE), heute + datetime.timedelta(days=FENSTER_NACH_TAGE)


def alle_quellen() -> list[Quelle]:
    eigene = [Quelle(f"k{k.pk}", k.name, k.farbe, k.beschreibung) for k in Kalender.objects.all()]
    return eigene + list(SYSTEMKALENDER)


def sichtbare_quellen(user) -> list[Quelle]:
    """Die Kalender, die ``user`` sehen darf."""
    if not user.is_authenticated or not user.hat_modulrecht("kalender", AKTION_LESEN):
        return []
    personal = user.hat_modulrecht("personal", AKTION_LESEN)
    return [q for q in alle_quellen() if personal or not q.system]


def quelle(schluessel: str) -> Quelle | None:
    return next((q for q in alle_quellen() if q.schluessel == schluessel), None)


def _tagesende(tag: datetime.date) -> datetime.datetime:
    return timezone.make_aware(datetime.datetime.combine(tag + datetime.timedelta(days=1), datetime.time.min))


def _termin_ereignis(t: Termin) -> dict:
    return {
        "uid": t.uid, "titel": t.titel, "ort": t.ort, "beschreibung": t.beschreibung, "ganztaegig": t.ganztaegig,
        "beginn": timezone.localtime(t.beginn), "ende": timezone.localtime(t.ende), "stempel": t.geaendert,
        "kalender": f"k{t.kalender_id}", "termin_pk": t.pk,
    }


def _eigene(kalender_pk: int, von: datetime.date, bis: datetime.date) -> list[dict]:
    anfang = timezone.make_aware(datetime.datetime.combine(von, datetime.time.min))
    return [
        _termin_ereignis(t)
        for t in Termin.objects.filter(kalender_id=kalender_pk, beginn__lt=_tagesende(bis), ende__gte=anfang)
    ]


def _urlaub(von: datetime.date, bis: datetime.date) -> list[dict]:
    from personal.models import Urlaubsantrag

    ergebnis = []
    for a in Urlaubsantrag.objects.filter(
        status=Urlaubsantrag.Status.GENEHMIGT, von__lte=bis, bis__gte=von
    ).select_related("mitarbeiter"):
        ergebnis.append({
            "uid": f"kybro-urlaub-{a.pk}@kybro", "titel": f"{a.mitarbeiter.listenname}: Urlaub", "ort": "", "beschreibung": "",
            "ganztaegig": True, "beginn": a.von, "ende": a.bis, "stempel": None, "kalender": "urlaub", "termin_pk": None,
        })
    return ergebnis


def _anwesenheit(von: datetime.date, bis: datetime.date) -> list[dict]:
    """Aufeinanderfolgende Tage desselben Status je Mitarbeiter werden zu einem Termin; Wochenenden überbrücken."""
    from personal.models import Anwesenheit

    zeilen = (
        Anwesenheit.objects.filter(status__in=ANWESENHEIT_IM_KALENDER, datum__range=(von, bis))
        .select_related("mitarbeiter").order_by("mitarbeiter_id", "status", "datum")
    )
    ergebnis, aktuell = [], None

    def abschliessen():
        if aktuell:
            m = aktuell["m"]
            ergebnis.append({
                "uid": f"kybro-anw-{m.pk}-{aktuell['status']}-{aktuell['von']:%Y%m%d}@kybro",
                "titel": f"{m.listenname}: {ANWESENHEIT_IM_KALENDER[aktuell['status']]}", "ort": "", "beschreibung": "",
                "ganztaegig": True, "beginn": aktuell["von"], "ende": aktuell["bis"], "stempel": None,
                "kalender": "anwesenheit", "termin_pk": None,
            })

    for z in zeilen:
        luecke = (z.datum - aktuell["bis"]).days if aktuell else None
        zusammen = (
            aktuell and aktuell["m"].pk == z.mitarbeiter_id and aktuell["status"] == z.status
            and (luecke == 1 or (luecke is not None and luecke <= 3 and all(
                (aktuell["bis"] + datetime.timedelta(days=i)).weekday() >= 5 for i in range(1, luecke)
            )))
        )
        if zusammen:
            aktuell["bis"] = z.datum
        else:
            abschliessen()
            aktuell = {"m": z.mitarbeiter, "status": z.status, "von": z.datum, "bis": z.datum}
    abschliessen()
    return ergebnis


def ereignisse(schluessel: str, von: datetime.date, bis: datetime.date) -> list[dict]:
    """Ereignisse des Kalenders ``schluessel`` im Zeitraum (einschließlich ``bis``)."""
    if schluessel == "urlaub":
        return _urlaub(von, bis)
    if schluessel == "anwesenheit":
        return _anwesenheit(von, bis)
    if schluessel.startswith("k") and schluessel[1:].isdigit():
        return _eigene(int(schluessel[1:]), von, bis)
    return []
