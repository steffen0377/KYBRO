"""Erzeugt Entwurfsrechnungen für fällige Abonnements (täglich per Cron/Timer).

Der Lauf ist idempotent und darf beliebig oft pro Tag ausgeführt werden.
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from belege.abos import abo_rechnungen_erzeugen


class Command(BaseCommand):
    help = "Erzeugt Entwurfsrechnungen für alle fälligen Abonnements und beendet gekündigte Abos."

    def add_arguments(self, parser):
        parser.add_argument("--stichtag", help="Datum im Format JJJJ-MM-TT (Standard: heute)")

    def handle(self, *args, **optionen):
        stichtag = None
        if optionen["stichtag"]:
            try:
                stichtag = date.fromisoformat(optionen["stichtag"])
            except ValueError:
                raise CommandError("Ungültiges Datum, erwartet JJJJ-MM-TT.")
        rechnungen = abo_rechnungen_erzeugen(stichtag)
        if not rechnungen:
            self.stdout.write("Keine fälligen Abo-Rechnungen zu erzeugen.")
            return
        self.stdout.write(f"{len(rechnungen)} Entwurfsrechnung(en) erzeugt:")
        for r in rechnungen:
            self.stdout.write(f"  - {r.nummer} (Abo {r.abo_id}, Kunde {r.kunde.anzeigename})")
