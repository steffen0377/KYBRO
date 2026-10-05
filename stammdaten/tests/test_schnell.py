from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from stammdaten.models import Artikel, Kategorie, Kunde

User = get_user_model()


class SchnellFormularTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("admin", "a@example.com", "Sehr-geheim-2026")
        self.client.force_login(self.user)

    def test_formular_laden(self):
        r = self.client.get(reverse("stammdaten:schnell_neu", args=["kunde"]))
        self.assertContains(r, "data-schnell-form")

    def test_unbekannte_art(self):
        self.assertEqual(self.client.get(reverse("stammdaten:schnell_neu", args=["gibtsnicht"])).status_code, 404)

    def test_kunde_anlegen_json(self):
        r = self.client.post(reverse("stammdaten:schnell_neu", args=["kunde"]), {"firma": "Muster GmbH"})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d["ok"])
        self.assertEqual(Kunde.objects.get(pk=d["id"]).firma, "Muster GmbH")
        self.assertIn("steuerbefreit", d["daten"])

    def test_ungueltig_gibt_422(self):
        r = self.client.post(reverse("stammdaten:schnell_neu", args=["artikel"]), {})
        self.assertEqual(r.status_code, 422)
        self.assertContains(r, "data-schnell-form", status_code=422)

    def test_artikel_bearbeiten(self):
        a = Artikel.objects.create(name="Alt", verkaufspreis=1, einkaufspreis=0)
        r = self.client.post(
            reverse("stammdaten:schnell_bearbeiten", args=["artikel", a.pk]),
            {"name": "Neu", "einheit": "Stk.", "verkaufspreis": "5", "einkaufspreis": "1", "steuersatz": "19"},
        )
        self.assertEqual(r.status_code, 200, r.content)
        a.refresh_from_db()
        self.assertEqual(a.name, "Neu")
        self.assertEqual(r.json()["daten"]["preis"], 5.0)

    def test_kategorie(self):
        r = self.client.post(reverse("stammdaten:schnell_neu", args=["kategorie"]), {"name": "Hardware"})
        self.assertEqual(r.json()["label"], str(Kategorie.objects.get()))

    def test_ohne_recht_verboten(self):
        u = User.objects.create_user("x", "x@example.com", "Sehr-geheim-2026")
        self.client.force_login(u)
        self.assertEqual(self.client.get(reverse("stammdaten:schnell_neu", args=["kunde"])).status_code, 403)

    def test_widget_attribute(self):
        r = self.client.get(reverse("belege:rechnungen_neu"))
        self.assertContains(r, "data-suche")
        self.assertContains(r, "data-schnell-art")
