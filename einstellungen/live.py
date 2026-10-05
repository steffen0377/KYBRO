"""Umschalten vom Testbetrieb in den Live-Betrieb.

Gelöscht werden alle Geschäftsdaten (Belege, Abonnements, Lager, Artikel, Kunden, Lieferanten) samt
hochgeladener Unterschriften sowie die Belegnummern-Zähler und Protokolle der Mobile-API.
Erhalten bleiben Firmendaten, Briefbogen-Elemente, SMTP, Formulareinstellungen, Lizenzen, die
Anmeldeeinstellungen (LDAP), Benutzer und Gruppen sowie die Personalverwaltung.
"""

import logging

from django.db import transaction

from api.models import LoginVersuch
from belege.models import Abo, Angebot, Auftrag, Rechnung
from lager.models import Lagerbewegung, Seriennummer
from stammdaten.models import Artikel, Kategorie, Kunde, Lieferant

from .models import Firma, Nummernkreis

log = logging.getLogger(__name__)


class LiveSchonAktiv(Exception):
    pass


def live_aktivieren(benutzer=None) -> dict[str, int]:
    """Löscht die Testdaten und schaltet auf Live. Gibt die Anzahl gelöschter Datensätze je Bereich zurück."""
    with transaction.atomic():
        firma = Firma.objects.select_for_update().get_or_create(pk=1)[0]
        if firma.betriebsmodus == Firma.Betrieb.LIVE:
            raise LiveSchonAktiv("Die Installation ist bereits im Live-Betrieb.")

        # Unterschriften sind Dateien: erst die Dateien, dann die Datensätze entfernen.
        dateien = [a.unterschrift for a in Auftrag.objects.exclude(unterschrift="")]

        # Reihenfolge wegen der Verknüpfungen (Belege vor Kunden/Artikeln).
        anzahl = {}
        for name, modell in (
            ("Seriennummern", Seriennummer), ("Lagerbewegungen", Lagerbewegung), ("Abonnements", Abo),
            ("Rechnungen", Rechnung), ("Aufträge", Auftrag), ("Angebote", Angebot),
            ("Artikel", Artikel), ("Kategorien", Kategorie), ("Kunden", Kunde), ("Lieferanten", Lieferant),
            ("Nummernkreise", Nummernkreis), ("API-Anmeldeversuche", LoginVersuch),
        ):
            anzahl[name] = modell.objects.count()
            modell.objects.all().delete()

        firma.betriebsmodus = Firma.Betrieb.LIVE
        firma.save(update_fields=["betriebsmodus"])
        transaction.on_commit(lambda: [datei.delete(save=False) for datei in dateien])

    log.warning("[LIVE] Live-Betrieb aktiviert von %s; gelöscht: %s", benutzer or "unbekannt", anzahl)
    return anzahl
