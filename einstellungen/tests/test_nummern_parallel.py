import threading
from datetime import date
from unittest import skipUnless

from django.db import connection, connections
from django.test import TransactionTestCase

from einstellungen.models import Firma
from einstellungen.services import naechste_belegnummer


@skipUnless(connection.vendor == "mysql", "Parallelität wird nur gegen MariaDB geprüft (SQLite sperrt die ganze Datei).")
class ParallelTests(TransactionTestCase):
    """Gleichzeitige Belegnummern dürfen weder doppelt vorkommen noch Deadlocks auslösen."""

    def lauf(self, jahr, anzahl=20):
        ergebnisse, fehler = [], []

        def arbeiter():
            try:
                ergebnisse.append(naechste_belegnummer("rechnung", date(jahr, 5, 1)))
            except Exception as e:  # noqa: BLE001
                fehler.append(repr(e))
            finally:
                connections.close_all()

        threads = [threading.Thread(target=arbeiter) for _ in range(anzahl)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        return ergebnisse, fehler

    def test_erster_beleg_des_jahres(self):
        Firma.holen()
        nummern, fehler = self.lauf(2030)
        self.assertEqual(fehler, [])
        self.assertEqual(len(set(nummern)), 20)
        self.assertEqual(sorted(nummern)[-1], "RE-2030-0020")

    def test_vorhandener_nummernkreis(self):
        naechste_belegnummer("rechnung", date(2030, 1, 1))
        nummern, fehler = self.lauf(2030)
        self.assertEqual(fehler, [])
        self.assertEqual(len(set(nummern)), 20)
