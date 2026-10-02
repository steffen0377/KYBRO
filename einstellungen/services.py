"""Belegnummern: Präfix + Jahr + laufende Nummer, z. B. ``RE-2026-0001``."""

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Firma, Nummernkreis

PRAEFIX_FELD = {
    Nummernkreis.Art.ANGEBOT: "praefix_angebot",
    Nummernkreis.Art.AUFTRAG: "praefix_auftrag",
    Nummernkreis.Art.RECHNUNG: "praefix_rechnung",
}


@transaction.atomic
def naechste_belegnummer(art: str, datum=None) -> str:
    """Vergibt die nächste Nummer der Belegart und zählt den Nummernkreis hoch.

    Muss innerhalb der Transaktion aufgerufen werden, die den Beleg speichert
    (``transaction.atomic`` verschachtelt sich): Bricht das Speichern ab, wird
    auch die Nummer nicht verbraucht. Die Zeile des Nummernkreises ist gesperrt,
    gleichzeitige Aufrufe erhalten daher nie dieselbe Nummer.
    """
    art = Nummernkreis.Art(art)
    jahr = (datum or timezone.localdate()).year
    kreise = Nummernkreis.objects.filter(art=art, jahr=jahr)
    # Vorhandene Zeile: sofort exklusiv hochzählen. Nur für den ersten Beleg eines Jahres
    # wird der Kreis angelegt, und zwar unter der Sperre der Firmenzeile, damit gleichzeitige
    # Anlagen nicht gegeneinander laufen (sonst Deadlocks unter MariaDB).
    if not kreise.exists():
        Firma.holen()
        Firma.objects.select_for_update().get(pk=1)
        # Sperrende Abfrage sieht auch das, was ein Wartender inzwischen angelegt hat.
        if kreise.select_for_update().first() is None:
            Nummernkreis.objects.create(art=art, jahr=jahr)
    kreise.update(naechste_nummer=F("naechste_nummer") + 1)
    nummer = kreise.get().naechste_nummer - 1
    praefix = getattr(Firma.holen(), PRAEFIX_FELD[art])
    return f"{praefix}{jahr}-{nummer:04d}"
