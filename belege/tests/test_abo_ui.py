from datetime import date
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import TestCase
from django.urls import reverse

from belege.models import Abo, Rechnung
from belege.tests import test_services as ts
from stammdaten.models import Artikel, Preisoption
from decimal import Decimal
from belege import services

User = get_user_model()


class AboOberflaecheTests(TestCase):
    ausgestellte_rechnung = ts.AboTests.ausgestellte_rechnung

    def setUp(self):
        self.artikel = Artikel.objects.create(name="Hosting", lagerfuehrung=False)
        Preisoption.objects.create(artikel=self.artikel, abrechnung="monatlich", preis=Decimal("20"))
        self.option = self.artikel.preisoptionen.get()
        self.ausgestellte_rechnung()
        self.abo = Abo.objects.get()
        self.client.force_login(User.objects.create_superuser("admin", password="Sehr-geheim-2026"))

    def test_liste_detail_und_link_aus_rechnung(self):
        self.assertContains(self.client.get(reverse("belege:abos_liste")), "Hosting")
        self.assertContains(self.client.get(reverse("belege:abos_liste") + "?q=nichts"), "Keine Abonnements")
        antwort = self.client.get(reverse("belege:abos_ansehen", args=[self.abo.pk]))
        self.assertContains(antwort, "Kündigen")
        rechnung = self.abo.ursprungsrechnung
        self.assertEqual(self.client.get(reverse("belege:rechnungen_ansehen", args=[rechnung.pk])).status_code, 200)

    def test_kuendigen_und_zuruecknehmen(self):
        self.client.post(reverse("belege:abos_kuendigen", args=[self.abo.pk]), {"eingang": "2026-03-10"})
        self.abo.refresh_from_db()
        self.assertEqual(self.abo.status, "gekuendigt")
        self.client.post(reverse("belege:abos_reaktivieren", args=[self.abo.pk]))
        self.abo.refresh_from_db()
        self.assertEqual(self.abo.status, "aktiv")

    def test_ungueltiges_datum(self):
        self.client.post(reverse("belege:abos_kuendigen", args=[self.abo.pk]), {"eingang": "quatsch"})
        self.abo.refresh_from_db()
        self.assertEqual(self.abo.status, "aktiv")

    def test_kuendigen_nur_mit_schreibrecht(self):
        leser = User.objects.create_user("leser", password="Sehr-geheim-2026")
        self.client.force_login(leser)
        self.assertEqual(self.client.get(reverse("belege:abos_liste")).status_code, 403)

    def test_befehl_erzeugt_idempotent(self):
        stichtag = self.abo.naechste_abrechnung.isoformat()
        aus = StringIO()
        call_command("abo_rechnungen_erzeugen", stichtag=stichtag, stdout=aus)
        self.assertIn("1 Entwurfsrechnung", aus.getvalue())
        aus = StringIO()
        call_command("abo_rechnungen_erzeugen", stichtag=stichtag, stdout=aus)
        self.assertIn("Keine fälligen", aus.getvalue())
        self.assertEqual(Rechnung.objects.filter(abo=self.abo).count(), 1)
        with self.assertRaises(CommandError):
            call_command("abo_rechnungen_erzeugen", stichtag="x")
