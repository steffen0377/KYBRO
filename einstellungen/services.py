"""Belegnummern: Präfix + Jahr + laufende Nummer, z. B. ``RE-2026-0001``."""

from django.db import IntegrityError, transaction
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
    try:
        with transaction.atomic():
            Nummernkreis.objects.get_or_create(art=art, jahr=jahr)
    except IntegrityError:  # gleichzeitig angelegt - die Zeile existiert jetzt
        pass
    kreis = Nummernkreis.objects.select_for_update().get(art=art, jahr=jahr)
    nummer = kreis.naechste_nummer
    kreis.naechste_nummer = nummer + 1
    kreis.save(update_fields=["naechste_nummer"])
    praefix = getattr(Firma.holen(), PRAEFIX_FELD[art])
    return f"{praefix}{jahr}-{nummer:04d}"
