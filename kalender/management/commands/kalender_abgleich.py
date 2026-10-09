from django.core.management.base import BaseCommand, CommandError

from kalender import abgleich
from kalender.models import CalDavVerbindung


class Command(BaseCommand):
    help = "Gleicht die KYBRO-Kalender mit dem eingerichteten CalDAV-Server ab (z. B. alle 10 Minuten per systemd-Timer)."

    def handle(self, *args, **optionen):
        verbindung = CalDavVerbindung.holen()
        if not verbindung.aktiv:
            self.stdout.write("Kalender-Abgleich ist nicht aktiviert.")
            return
        ergebnis = abgleich.abgleichen(verbindung)
        self.stdout.write(ergebnis["text"])
        if ergebnis["fehler"]:
            raise CommandError("Der Abgleich hatte Fehler.")
