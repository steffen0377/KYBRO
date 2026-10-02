from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from lager.models import Lagerbewegung, Seriennummer
from stammdaten.models import Artikel

User = get_user_model()


class LagerViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", password="Sehr-geheim-2026")
        self.client.force_login(self.admin)
        self.schraube = Artikel.objects.create(name="Schraube")
        self.laptop = Artikel.objects.create(name="Laptop", seriennummern=True)

    def test_uebersicht_listet_nur_passende_artikel_in_den_formularen(self):
        antwort = self.client.get(reverse("lager:uebersicht"))
        self.assertEqual(list(antwort.context["form_wareneingang"].fields["artikel"].queryset), [self.schraube])
        self.assertEqual(list(antwort.context["form_seriell"].fields["artikel"].queryset), [self.laptop])

    def test_wareneingang(self):
        antwort = self.client.post(reverse("lager:wareneingang"), {"artikel": self.schraube.pk, "menge": "12,5", "notiz": "Lieferung"}, follow=True)
        self.assertContains(antwort, "Wareneingang gebucht.")
        self.schraube.refresh_from_db()
        self.assertEqual(self.schraube.bestand, Decimal("12.5"))
        self.assertContains(antwort, "Lieferung")

    def test_wareneingang_fuer_seriennummernartikel_nicht_moeglich(self):
        antwort = self.client.post(reverse("lager:wareneingang"), {"artikel": self.laptop.pk, "menge": "1"}, follow=True)
        self.assertContains(antwort, "nicht gebucht")
        self.assertEqual(Lagerbewegung.objects.count(), 0)

    def test_korrektur(self):
        self.client.post(reverse("lager:wareneingang"), {"artikel": self.schraube.pk, "menge": "10"})
        antwort = self.client.post(reverse("lager:korrektur"), {"artikel": self.schraube.pk, "neuer_bestand": "8"}, follow=True)
        self.assertContains(antwort, "Bestand korrigiert.")
        self.schraube.refresh_from_db()
        self.assertEqual(self.schraube.bestand, Decimal("8"))

    def test_seriennummern_einlagern_mit_dublette(self):
        url = reverse("lager:seriell_einlagern")
        self.client.post(url, {"artikel": self.laptop.pk, "seriennummern": "A1\nB2\nA1"})
        antwort = self.client.post(url, {"artikel": self.laptop.pk, "seriennummern": "B2\nC3"}, follow=True)
        self.assertContains(antwort, "Bereits vorhandene Seriennummern übersprungen: B2")
        self.assertContains(antwort, "1 Seriennummer(n) eingelagert.")
        self.laptop.refresh_from_db()
        self.assertEqual(self.laptop.bestand, Decimal("3"))
        self.assertContains(antwort, "C3")  # Weiterleitung zeigt die Seriennummernliste

    def test_serie_defekt_und_entfernen_nur_per_post(self):
        self.client.post(reverse("lager:seriell_einlagern"), {"artikel": self.laptop.pk, "seriennummern": "A1\nB2"})
        a1, b2 = Seriennummer.objects.get(nummer="A1"), Seriennummer.objects.get(nummer="B2")
        self.assertEqual(self.client.get(reverse("lager:serie_defekt", args=[a1.pk])).status_code, 405)
        self.client.post(reverse("lager:serie_defekt", args=[a1.pk]))
        self.client.post(reverse("lager:serie_entfernen", args=[b2.pk]))
        a1.refresh_from_db()
        self.assertEqual(a1.status, "defekt")
        self.assertFalse(Seriennummer.objects.filter(nummer="B2").exists())
        self.laptop.refresh_from_db()
        self.assertEqual(self.laptop.bestand, Decimal("0"))

    def test_unter_mindestbestand_wird_angezeigt(self):
        self.schraube.mindestbestand = 5
        self.schraube.save()
        antwort = self.client.get(reverse("lager:uebersicht"))
        self.assertContains(antwort, "Unter Mindestbestand")

    def test_rechte(self):
        gruppe = Group.objects.create(name="Nur lesen")
        gruppe.permissions.set(Permission.objects.filter(codename="lager_lesen"))
        user = User.objects.create_user("anna", password="Sehr-geheim-2026")
        user.groups.add(gruppe)
        self.client.force_login(user)
        antwort = self.client.get(reverse("lager:uebersicht"))
        self.assertEqual(antwort.status_code, 200)
        self.assertNotContains(antwort, reverse("lager:wareneingang"))  # keine Eingabeformulare
        self.assertEqual(self.client.post(reverse("lager:wareneingang"), {"artikel": self.schraube.pk, "menge": "1"}).status_code, 403)
        self.assertEqual(Lagerbewegung.objects.count(), 0)
