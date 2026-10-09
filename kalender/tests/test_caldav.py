"""Gegenprobe mit einem echten CalDAV-Server: Radicale läuft für die Dauer des Tests im Prozess.

Die Tests werden übersprungen, wenn Radicale nicht installiert ist (``pip install radicale``, siehe requirements-dev.txt).
"""

import datetime
import tempfile
import threading
import unittest
from wsgiref.simple_server import WSGIRequestHandler, make_server

from django.test import TestCase
from django.utils import timezone

from kalender import abgleich, quellen
from kalender.caldav import CalDavClient, CalDavFehler
from kalender.models import CalDavVerbindung, Kalender, SyncEintrag, Termin, Zuordnung
from personal.models import Mitarbeiter, Urlaubsantrag

try:
    from radicale import Application, config as radicale_config
except ImportError:  # pragma: no cover
    Application = None

D = datetime.date


class LeiseHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass


def aware(jahr, monat, tag, std=0):
    return timezone.make_aware(datetime.datetime(jahr, monat, tag, std))


@unittest.skipIf(Application is None, "radicale ist nicht installiert")
class RadicaleTestCase(TestCase):
    """Startet pro Testklasse einen Radicale-Server (Benutzer ``sync``, Passwort ``geheim``)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.verz = tempfile.TemporaryDirectory()
        htpasswd = f"{cls.verz.name}/users"
        with open(htpasswd, "w") as datei:
            datei.write("sync:geheim\n")
        konfig = radicale_config.load()
        konfig.update({
            "auth": {"type": "htpasswd", "htpasswd_filename": htpasswd, "htpasswd_encryption": "plain"},
            "storage": {"filesystem_folder": f"{cls.verz.name}/daten"},
            "logging": {"level": "error"},
        }, "test")
        cls.server = make_server("127.0.0.1", 0, Application(konfig), handler_class=LeiseHandler)
        cls.faden = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.faden.start()
        cls.basis = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.verz.cleanup()
        super().tearDownClass()

    def dav(self, passwort="geheim"):
        return CalDavClient(self.basis, "sync", passwort)


class ClientTests(RadicaleTestCase):
    def test_falsches_passwort(self):
        with self.assertRaisesRegex(CalDavFehler, "Anmeldung abgelehnt"):
            self.dav("falsch").kalender()

    def test_kalender_anlegen_finden_und_termine(self):
        c = self.dav()
        neu = c.kalender_anlegen("KYBRO Test & Co")
        self.assertIn("KYBRO Test & Co", [k["name"] for k in c.kalender()])
        self.assertEqual(c.vorhandene(neu["url"]), set())
        c.speichern(neu["url"], "abc@kybro", "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//\r\nBEGIN:VEVENT\r\nUID:abc@kybro\r\n"
                    "DTSTAMP:20260101T000000Z\r\nDTSTART;VALUE=DATE:20261005\r\nDTEND;VALUE=DATE:20261006\r\nSUMMARY:Test\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
        self.assertEqual(c.vorhandene(neu["url"]), {"abc@kybro.ics"})
        c.loeschen(neu["url"], "abc@kybro")
        c.loeschen(neu["url"], "gibt-es-nicht@kybro")  # 404 ist in Ordnung
        self.assertEqual(c.vorhandene(neu["url"]), set())

    def test_nicht_erreichbar(self):
        with self.assertRaisesRegex(CalDavFehler, "nicht erreichbar"):
            CalDavClient("http://127.0.0.1:9", "a", "b", timeout=2).kalender()

    def test_adresse_ohne_schema(self):
        with self.assertRaisesRegex(CalDavFehler, "https://"):
            CalDavClient("server.example", "a", "b").kalender()


class AdressfindungTests(unittest.TestCase):
    """Nextcloud-Verhalten ohne Server nachgestellt: die Adresse ohne Pfad antwortet nicht, /remote.php/dav schon."""

    def test_nextcloud_pfad_wird_ergaenzt(self):
        from unittest import mock

        import lxml.etree as et

        aufrufe = []

        def propfind(self, url, eigenschaften, tiefe=0):
            aufrufe.append(url)
            if url == "https://cloud.example.de":
                raise CalDavFehler("PROPFIND /: Server antwortete 405.")
            if "current-user-principal" in eigenschaften:
                knoten = et.fromstring('<d:current-user-principal xmlns:d="DAV:"><d:href>/remote.php/dav/principals/users/sync/</d:href></d:current-user-principal>')
                return [{"href": url, "props": {knoten.tag: knoten}}]
            knoten = et.fromstring('<c:calendar-home-set xmlns:c="urn:ietf:params:xml:ns:caldav" xmlns:d="DAV:"><d:href>/remote.php/dav/calendars/sync/</d:href></c:calendar-home-set>')
            return [{"href": url, "props": {knoten.tag: knoten}}]

        with mock.patch.object(CalDavClient, "_propfind", propfind):
            client = CalDavClient("https://cloud.example.de", "sync", "x")
            self.assertEqual(client.kalenderheim(), "https://cloud.example.de/remote.php/dav/calendars/sync/")
        self.assertEqual(aufrufe[0], "https://cloud.example.de")
        self.assertTrue(aufrufe[1].endswith("/remote.php/dav/"))

    def test_ohne_dienst_klare_meldung(self):
        from unittest import mock

        with mock.patch.object(CalDavClient, "_propfind", lambda self, url, e, tiefe=0: [{"href": url, "props": {}}]):
            with self.assertRaisesRegex(CalDavFehler, "kein CalDAV-Dienst"):
                CalDavClient("http://x.example/dav/", "a", "b").kalenderheim()


class AbgleichTests(RadicaleTestCase):
    def setUp(self):
        self.c = self.dav()
        self.ziel = self.c.kalender_anlegen(f"KYBRO Abgleich {self.id().rsplit('.', 1)[-1]}")
        self.team = Kalender.objects.create(name="Team")
        self.verbindung = CalDavVerbindung.objects.create(
            aktiv=True, url=self.basis, benutzer="sync", passwort="geheim"
        )
        self.z = Zuordnung.objects.create(quelle=f"k{self.team.pk}", ziel_url=self.ziel["url"], ziel_name=self.ziel["name"])

    def lauf(self):
        return abgleich.abgleichen(self.verbindung)

    def test_anlegen_aendern_loeschen_und_unveraendert(self):
        t = Termin.objects.create(kalender=self.team, titel="Workshop", beginn=timezone.now() + datetime.timedelta(days=2),
                                  ende=timezone.now() + datetime.timedelta(days=2, hours=2))
        erst = self.lauf()
        self.assertEqual((erst["angelegt"], erst["geaendert"], erst["geloescht"], erst["fehler"]), (1, 0, 0, 0))
        self.assertEqual(self.c.vorhandene(self.ziel["url"]), {f"{t.uid}.ics"})
        zweit = self.lauf()
        self.assertEqual((zweit["angelegt"], zweit["geaendert"], zweit["geloescht"]), (0, 0, 0))  # nichts zu tun
        t.titel = "Workshop 2"
        t.save()
        self.assertEqual(self.lauf()["geaendert"], 1)
        t.delete()
        dritt = self.lauf()
        self.assertEqual(dritt["geloescht"], 1)
        self.assertEqual(self.c.vorhandene(self.ziel["url"]), set())
        self.assertFalse(SyncEintrag.objects.exists())

    def test_auf_dem_server_geloeschter_termin_wird_neu_angelegt(self):
        t = Termin.objects.create(kalender=self.team, titel="Messe", beginn=timezone.now() + datetime.timedelta(days=5),
                                  ende=timezone.now() + datetime.timedelta(days=5, hours=1))
        self.lauf()
        self.c.loeschen(self.ziel["url"], t.uid)
        self.assertEqual(self.c.vorhandene(self.ziel["url"]), set())
        self.assertEqual(self.lauf()["geaendert"], 1)
        self.assertEqual(self.c.vorhandene(self.ziel["url"]), {f"{t.uid}.ics"})

    def test_fremde_termine_bleiben_unberuehrt(self):
        self.c.speichern(self.ziel["url"], "fremd@x", "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//\r\nBEGIN:VEVENT\r\nUID:fremd@x\r\n"
                         "DTSTAMP:20260101T000000Z\r\nDTSTART;VALUE=DATE:20261005\r\nDTEND;VALUE=DATE:20261006\r\nSUMMARY:Fremd\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
        self.lauf()
        self.assertIn("fremd@x.ics", self.c.vorhandene(self.ziel["url"]))

    def test_systemkalender_urlaub(self):
        m = Mitarbeiter.objects.create(vorname="Erika", nachname="Muster")
        heute = timezone.localdate()
        a = Urlaubsantrag.objects.create(mitarbeiter=m, von=heute, bis=heute + datetime.timedelta(days=2), status="genehmigt", bemerkung="privat")
        Urlaubsantrag.objects.create(mitarbeiter=m, von=heute + datetime.timedelta(days=10), bis=heute + datetime.timedelta(days=11), status="beantragt")
        z = Zuordnung.objects.create(quelle="urlaub", ziel_url=self.ziel["url"], ziel_name="Urlaub")
        ergebnis = self.lauf()
        self.assertEqual(ergebnis["fehler"], 0)
        self.assertIn(f"kybro-urlaub-{a.pk}@kybro.ics", self.c.vorhandene(self.ziel["url"]))
        self.assertEqual(SyncEintrag.objects.filter(zuordnung=z).count(), 1)  # beantragter Urlaub gehört nicht dazu
        a.status = "storniert"
        a.save()
        self.assertEqual(self.lauf()["geloescht"], 1)

    def test_alte_termine_ausserhalb_des_fensters_bleiben(self):
        von, _ = quellen.standardfenster()
        alt = von - datetime.timedelta(days=30)
        SyncEintrag.objects.create(zuordnung=self.z, uid="alt@kybro", pruefsumme="x", ende=alt)
        self.c.speichern(self.ziel["url"], "alt@kybro", "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//\r\nBEGIN:VEVENT\r\nUID:alt@kybro\r\n"
                         "DTSTAMP:20260101T000000Z\r\nDTSTART;VALUE=DATE:20260105\r\nDTEND;VALUE=DATE:20260106\r\nSUMMARY:Alt\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
        self.assertEqual(self.lauf()["geloescht"], 0)
        self.assertIn("alt@kybro.ics", self.c.vorhandene(self.ziel["url"]))

    def test_fehler_wird_gemeldet_und_beim_naechsten_lauf_wiederholt(self):
        Termin.objects.create(kalender=self.team, titel="x", beginn=timezone.now() + datetime.timedelta(days=1),
                              ende=timezone.now() + datetime.timedelta(days=1, hours=1))
        self.verbindung.passwort = "falsch"
        ergebnis = self.lauf()
        self.assertEqual(ergebnis["fehler"], 1)
        self.assertIn("Anmeldung abgelehnt", ergebnis["text"])
        self.assertFalse(SyncEintrag.objects.exists())
        self.verbindung.passwort = "geheim"
        self.assertEqual(self.lauf()["angelegt"], 1)

    def test_zuordnung_entfernen_loescht_termine_auf_dem_server(self):
        Termin.objects.create(kalender=self.team, titel="x", beginn=timezone.now() + datetime.timedelta(days=1),
                              ende=timezone.now() + datetime.timedelta(days=1, hours=1))
        self.lauf()
        self.assertEqual(len(self.c.vorhandene(self.ziel["url"])), 1)
        self.assertEqual(abgleich.zuordnung_entfernen(self.z, self.c), [])
        self.assertEqual(self.c.vorhandene(self.ziel["url"]), set())
        self.assertFalse(Zuordnung.objects.filter(pk=self.z.pk).exists())

    def test_nicht_eingerichtet(self):
        leer = CalDavVerbindung.objects.get(pk=self.verbindung.pk)
        leer.passwort = ""
        leer.save()
        ergebnis = abgleich.abgleichen(leer)
        self.assertEqual(ergebnis["fehler"], 1)
        self.assertIn("nicht vollständig eingerichtet", ergebnis["text"])


class EinstellungenSeitenTests(RadicaleTestCase):
    """Die Einstellungsseite gegen den echten Server."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        self.admin = get_user_model().objects.create_superuser("admin", password="Sehr-geheim-2026")
        self.client.force_login(self.admin)
        self.team = Kalender.objects.create(name="Team")

    def speichern(self, **extra):
        daten = {"aktion": "speichern", "aktiv": "on", "url": self.basis, "benutzer": "sync", "passwort": "geheim", "tls_pruefen": "on"}
        daten.update(extra)
        return self.client.post("/einstellungen/kalender/", daten, follow=True)

    def test_nur_administratoren(self):
        from django.contrib.auth import get_user_model

        self.client.force_login(get_user_model().objects.create_user("anna", password="Sehr-geheim-2026"))
        self.assertEqual(self.client.get("/einstellungen/kalender/").status_code, 403)

    def test_passwort_bleibt_bei_leerem_feld_und_wird_nicht_angezeigt(self):
        self.speichern()
        antwort = self.speichern(passwort="")
        self.assertEqual(CalDavVerbindung.holen().passwort, "geheim")
        self.assertNotContains(antwort, "geheim")

    def test_verbindung_testen_zuordnen_neu_anlegen_und_abgleichen(self):
        antwort = self.speichern(aktion="testen")
        self.assertContains(antwort, "Verbindung in Ordnung")
        self.client.post("/einstellungen/kalender/", {
            "aktion": "zuordnung", f"neu_k{self.team.pk}": "KYBRO Team (Seite)", "ziel_urlaub": "", "neu_anwesenheit": "",
        }, follow=True)
        z = Zuordnung.objects.get()
        self.assertEqual((z.quelle, z.ziel_name), (f"k{self.team.pk}", "KYBRO Team (Seite)"))
        Termin.objects.create(kalender=self.team, titel="Treffen", beginn=timezone.now() + datetime.timedelta(days=1),
                              ende=timezone.now() + datetime.timedelta(days=1, hours=1))
        antwort = self.client.post("/einstellungen/kalender/", {"aktion": "abgleichen"}, follow=True)
        self.assertContains(antwort, "1 angelegt")
        self.assertEqual(len(self.dav().vorhandene(z.ziel_url)), 1)
        # Zuordnung abwählen: Termine verschwinden vom Server
        self.client.post("/einstellungen/kalender/", {"aktion": "zuordnung", f"ziel_k{self.team.pk}": ""}, follow=True)
        self.assertFalse(Zuordnung.objects.exists())
        self.assertEqual(self.dav().vorhandene(z.ziel_url), set())

    def test_falsche_zugangsdaten_beim_test(self):
        antwort = self.speichern(aktion="testen", passwort="falsch")
        self.assertContains(antwort, "Anmeldung abgelehnt")

    def test_unbekannter_zielkalender_wird_abgelehnt(self):
        self.speichern()
        antwort = self.client.post("/einstellungen/kalender/", {"aktion": "zuordnung", f"ziel_k{self.team.pk}": "http://boese.example/x/"}, follow=True)
        self.assertContains(antwort, "Unbekannter Zielkalender")
        self.assertFalse(Zuordnung.objects.exists())

    def test_ein_ziel_nicht_doppelt(self):
        self.speichern(aktion="testen")
        ziel = self.dav().kalender_anlegen("Doppelt")["url"]
        self.client.post("/einstellungen/kalender/", {"aktion": "testen", "url": self.basis, "benutzer": "sync", "passwort": "", "tls_pruefen": "on", "aktiv": "on"}, follow=True)
        antwort = self.client.post("/einstellungen/kalender/", {"aktion": "zuordnung", f"ziel_k{self.team.pk}": ziel, "ziel_urlaub": ziel}, follow=True)
        self.assertContains(antwort, "nur einem KYBRO-Kalender")

    def test_kommando_ohne_aktivierung_tut_nichts(self):
        from io import StringIO

        from django.core.management import call_command

        v = CalDavVerbindung.holen()
        v.aktiv = False
        v.save()
        aus = StringIO()
        call_command("kalender_abgleich", stdout=aus)
        self.assertIn("nicht aktiviert", aus.getvalue())
