"""Gesetzliche Feiertage je Bundesland und konfigurierte Sondertage.

Die gesetzlichen Feiertage werden ohne Zusatzpaket berechnet (Osterformel nach Gauß). Zusätzlich gelten die unter
Einstellungen › Personal gepflegten Sondertage: eigene Feiertage (Urlaubsanteil 0) und halbe Tage (z. B. 24.12. und 31.12.).
Ein Sondertag überschreibt einen gesetzlichen Feiertag am selben Datum.
"""

import datetime
from decimal import Decimal

BUNDESLAENDER = [
    ("BW", "Baden-Württemberg"), ("BY", "Bayern"), ("BE", "Berlin"), ("BB", "Brandenburg"), ("HB", "Bremen"),
    ("HH", "Hamburg"), ("HE", "Hessen"), ("MV", "Mecklenburg-Vorpommern"), ("NI", "Niedersachsen"),
    ("NW", "Nordrhein-Westfalen"), ("RP", "Rheinland-Pfalz"), ("SL", "Saarland"), ("SN", "Sachsen"),
    ("ST", "Sachsen-Anhalt"), ("SH", "Schleswig-Holstein"), ("TH", "Thüringen"),
]

EINS = Decimal("1")
NULL = Decimal("0")


def ostersonntag(jahr: int) -> datetime.date:
    a, b, c = jahr % 19, jahr // 100, jahr % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    el = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * el) // 451
    monat = (h + el - 7 * m + 114) // 31
    tag = (h + el - 7 * m + 114) % 31 + 1
    return datetime.date(jahr, monat, tag)


def gesetzliche_feiertage(jahr: int, land: str) -> dict[datetime.date, str]:
    """Gesetzliche Feiertage des Bundeslands ``land`` (Kürzel, z. B. ``NW``). Ohne Bundesland: leer."""
    if not land:
        return {}
    ostern = ostersonntag(jahr)
    tage = datetime.timedelta
    f = {
        datetime.date(jahr, 1, 1): "Neujahr",
        ostern - tage(days=2): "Karfreitag",
        ostern + tage(days=1): "Ostermontag",
        datetime.date(jahr, 5, 1): "Tag der Arbeit",
        ostern + tage(days=39): "Christi Himmelfahrt",
        ostern + tage(days=50): "Pfingstmontag",
        datetime.date(jahr, 10, 3): "Tag der Deutschen Einheit",
        datetime.date(jahr, 12, 25): "1. Weihnachtstag",
        datetime.date(jahr, 12, 26): "2. Weihnachtstag",
    }
    if land in ("BW", "BY", "ST"):
        f[datetime.date(jahr, 1, 6)] = "Heilige Drei Könige"
    if land == "BE" and jahr >= 2019 or land == "MV" and jahr >= 2023:
        f[datetime.date(jahr, 3, 8)] = "Internationaler Frauentag"
    if land in ("BW", "BY", "HE", "NW", "RP", "SL"):
        f[ostern + tage(days=60)] = "Fronleichnam"
    if land in ("BY", "SL"):
        f[datetime.date(jahr, 8, 15)] = "Mariä Himmelfahrt"
    if land == "TH" and jahr >= 2019:
        f[datetime.date(jahr, 9, 20)] = "Weltkindertag"
    if land in ("BB", "MV", "SN", "ST", "TH") or land in ("HB", "HH", "NI", "SH") and jahr >= 2018:
        f[datetime.date(jahr, 10, 31)] = "Reformationstag"
    if land in ("BW", "BY", "NW", "RP", "SL"):
        f[datetime.date(jahr, 11, 1)] = "Allerheiligen"
    if land == "SN":
        # Buß- und Bettag: Mittwoch vor dem 23. November.
        tag = datetime.date(jahr, 11, 22)
        while tag.weekday() != 2:
            tag -= tage(days=1)
        f[tag] = "Buß- und Bettag"
    return f


class Kalender:
    """Feiertage und Urlaubsgewichte für beliebige Tage (einmal je Berechnung anlegen, dann wiederverwenden)."""

    def __init__(self):
        from .models import PersonalEinstellung, Sondertag

        self.bundesland = PersonalEinstellung.laden().bundesland
        self.sondertage = list(Sondertag.objects.all())
        self._jahre: dict[int, dict[datetime.date, tuple[str, Decimal]]] = {}

    def _jahr(self, jahr: int) -> dict[datetime.date, tuple[str, Decimal]]:
        if jahr not in self._jahre:
            tage = {d: (name, NULL) for d, name in gesetzliche_feiertage(jahr, self.bundesland).items()}
            for s in self.sondertage:
                if s.jahr in (None, jahr):
                    try:
                        tage[datetime.date(jahr, s.monat, s.tag)] = (s.name, s.urlaubsanteil)
                    except ValueError:  # 29.2. in einem Nicht-Schaltjahr
                        pass
            self._jahre[jahr] = tage
        return self._jahre[jahr]

    def info(self, tag: datetime.date) -> tuple[str, Decimal] | None:
        """(Name, Urlaubsanteil) falls der Tag ein Feiertag (0) oder halber Tag (0,5) ist."""
        return self._jahr(tag.year).get(tag)

    def anteil(self, tag: datetime.date) -> Decimal:
        """Wie viel Urlaub ein Arbeitstag kostet: 1, bei halben Tagen 0,5, an Feiertagen 0."""
        gefunden = self.info(tag)
        return gefunden[1] if gefunden else EINS

    def feiertage(self, jahr: int) -> list[tuple[datetime.date, str, Decimal]]:
        return sorted((d, n, a) for d, (n, a) in self._jahr(jahr).items())
