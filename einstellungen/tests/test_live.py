import os
import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from belege import services
from belege.models import Abo, Angebot, Auftrag, Rechnung
from belege.tests.test_services import angebot_mit_position
from einstellungen import live
from einstellungen.models import Authentifizierung, Firma, Formulareinstellung, Nummernkreis
from einstellungen.services import naechste_belegnummer
from lager.models import Lagerbewegung, Seriennummer
from stammdaten.models import Artikel, Kunde, Lieferant

User = get_user_model()
PW = "Sehr-geheim-2026"
MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class LiveAktivierenTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", password=PW)
        firma = Firma.holen()
        firma.firmenname = "IT-Dienst GmbH"
        firma.praefix_rechnung = "R-"
        firma.save()
        Authentifizierung.objects.update_or_create(pk=1, defaults={"ldap_host": "dc.example.de"})
        Formulareinstellung.objects.create(bereich="global", schluessel="titel", wert="Meine Rechnung")
        Group.objects.create(name="Vertrieb")
        artikel = Artikel.objects.create(name="Router", bestand=5)
        angebot = angebot_mit_position(artikel=artikel)
        auftrag, _ = services.auftrag_aus_angebot(angebot)
        auftrag.unterschrift.save("u.png", ContentFile(b"png"), save=True)
        self.datei = auftrag.unterschrift.path
        services.rechnung_aus_auftrag(auftrag)
        Lieferant.objects.create(firma="Lieferant AG")
        Lagerbewegung.objects.create(artikel=artikel, menge=1, typ="einlagerung")

    def test_standard_ist_testbetrieb_mit_hinweis(self):
        self.assertEqual(Firma.holen().betriebsmodus, "test")
        self.client.force_login(self.admin)
        antwort = self.client.get(reverse("belege:rechnungen_liste"))
        self.assertContains(antwort, "Testbetrieb")
        self.assertContains(antwort, reverse("einstellungen:live"))
        self.assertNotContains(self.client.get(reverse("core:dashboard")), "Alle Daten sind Testdaten")
        self.assertContains(self.client.get(reverse("einstellungen:firma")), "Live-Betrieb aktivieren")

    def test_nur_administratoren(self):
        self.client.force_login(User.objects.create_user("anna", password=PW))
        self.assertEqual(self.client.get(reverse("einstellungen:live")).status_code, 403)
        self.assertEqual(self.client.post(reverse("einstellungen:live"), {"sicherung": "on", "bestaetigung": "LIVE"}).status_code, 403)
        self.assertTrue(Rechnung.objects.exists())

    def test_ohne_bestaetigung_passiert_nichts(self):
        self.client.force_login(self.admin)
        for daten in ({}, {"sicherung": "on"}, {"sicherung": "on", "bestaetigung": "live!"}, {"bestaetigung": "LIVE"}):
            antwort = self.client.post(reverse("einstellungen:live"), daten)
            self.assertEqual(antwort.status_code, 200)
        self.assertTrue(Rechnung.objects.exists())
        self.assertEqual(Firma.holen().betriebsmodus, "test")

    def test_aktivieren_loescht_testdaten_und_behaelt_einstellungen(self):
        naechste_belegnummer("rechnung", date(2026, 1, 1))
        self.client.force_login(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            antwort = self.client.post(
                reverse("einstellungen:live"), {"sicherung": "on", "bestaetigung": "LIVE"}, follow=True
            )
        self.assertContains(antwort, "Live-Betrieb aktiviert")
        for modell in (Angebot, Auftrag, Rechnung, Abo, Artikel, Kunde, Lieferant, Lagerbewegung, Seriennummer, Nummernkreis):
            self.assertEqual(modell.objects.count(), 0, modell.__name__)
        firma = Firma.holen()
        self.assertEqual(firma.betriebsmodus, "live")
        self.assertEqual((firma.firmenname, firma.praefix_rechnung), ("IT-Dienst GmbH", "R-"))
        self.assertEqual(Authentifizierung.holen().ldap_host, "dc.example.de")
        self.assertEqual(Formulareinstellung.objects.count(), 1)
        self.assertTrue(User.objects.filter(username="admin").exists())
        self.assertTrue(Group.objects.filter(name="Vertrieb").exists())
        self.assertFalse(os.path.exists(self.datei))
        self.assertEqual(naechste_belegnummer("rechnung", date(2026, 1, 1)), "R-2026-0001")

    def test_danach_kein_hinweis_und_nicht_wiederholbar(self):
        live.live_aktivieren(self.admin)
        self.client.force_login(self.admin)
        self.assertNotContains(self.client.get(reverse("core:dashboard")), "Testbetrieb")
        self.assertNotContains(self.client.get(reverse("einstellungen:firma")), "Live-Betrieb aktivieren")
        Kunde.objects.create(firma="Echter Kunde")
        antwort = self.client.post(reverse("einstellungen:live"), {"sicherung": "on", "bestaetigung": "LIVE"})
        self.assertRedirects(antwort, reverse("einstellungen:firma"))
        self.assertTrue(Kunde.objects.exists())
        with self.assertRaises(live.LiveSchonAktiv):
            live.live_aktivieren(self.admin)
        self.assertTrue(Kunde.objects.exists())
