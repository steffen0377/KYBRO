"""Erzeugt iCalendar-Texte (RFC 5545) für Termine; ganz ohne Zusatzbibliothek.

Zeitpunkte werden in UTC geschrieben, ganztägige Termine als Datum (Ende ausschließlich). Dadurch braucht der
Kalender keine Zeitzonendefinitionen.
"""

import datetime

from django.utils import timezone

PRODID = "-//KYBRO//Kalender//DE"
STABILER_STEMPEL = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)


def _escape(text: str) -> str:
    return (
        (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
    )


def _falten(zeile: str) -> list[str]:
    """Zeilen länger als 75 Oktette werden umbrochen (Folgezeilen beginnen mit einem Leerzeichen)."""
    daten = zeile.encode("utf-8")
    if len(daten) <= 75:
        return [zeile]
    teile, aktuell, laenge = [], "", 0
    for zeichen in zeile:
        n = len(zeichen.encode("utf-8"))
        grenze = 75 if not teile else 74
        if laenge + n > grenze:
            teile.append(aktuell)
            aktuell, laenge = "", 0
        aktuell += zeichen
        laenge += n
    teile.append(aktuell)
    return [teile[0]] + [" " + t for t in teile[1:]]


def _utc(zeit: datetime.datetime) -> str:
    if timezone.is_naive(zeit):
        zeit = timezone.make_aware(zeit)
    return zeit.astimezone(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _vevent(e: dict) -> list[str]:
    zeilen = ["BEGIN:VEVENT", f"UID:{e['uid']}", f"DTSTAMP:{_utc(e.get('stempel') or STABILER_STEMPEL)}"]
    if e["ganztaegig"]:
        erster = e["beginn"].date() if isinstance(e["beginn"], datetime.datetime) else e["beginn"]
        letzter = e["ende"].date() if isinstance(e["ende"], datetime.datetime) else e["ende"]
        zeilen.append(f"DTSTART;VALUE=DATE:{erster:%Y%m%d}")
        zeilen.append(f"DTEND;VALUE=DATE:{letzter + datetime.timedelta(days=1):%Y%m%d}")
        zeilen.append("TRANSP:TRANSPARENT")
    else:
        zeilen.append(f"DTSTART:{_utc(e['beginn'])}")
        zeilen.append(f"DTEND:{_utc(e['ende'])}")
    zeilen.append(f"SUMMARY:{_escape(e['titel'])}")
    if e.get("ort"):
        zeilen.append(f"LOCATION:{_escape(e['ort'])}")
    if e.get("beschreibung"):
        zeilen.append(f"DESCRIPTION:{_escape(e['beschreibung'])}")
    zeilen.append("END:VEVENT")
    return zeilen


def kalender_text(ereignisse: list[dict], name: str = "", farbe: str = "") -> str:
    """Ein ganzer Kalender (für das Abo)."""
    zeilen = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    if name:
        zeilen += [f"X-WR-CALNAME:{_escape(name)}", f"NAME:{_escape(name)}"]
    if farbe:
        zeilen += [f"X-APPLE-CALENDAR-COLOR:{farbe}", f"COLOR:{farbe}"]
    zeilen += ["REFRESH-INTERVAL;VALUE=DURATION:PT1H", "X-PUBLISHED-TTL:PT1H"]
    for e in ereignisse:
        zeilen += _vevent(e)
    zeilen.append("END:VCALENDAR")
    return "\r\n".join(z2 for z in zeilen for z2 in _falten(z)) + "\r\n"


def ereignis_text(e: dict) -> str:
    """Ein einzelner Termin als eigene iCalendar-Datei (für den Abgleich per CalDAV, ohne METHOD)."""
    zeilen = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN"] + _vevent(e) + ["END:VCALENDAR"]
    return "\r\n".join(z2 for z in zeilen for z2 in _falten(z)) + "\r\n"
