from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from lager import services
from lager.models import Lagerbewegung, Seriennummer
from lager.services import LagerFehler
from stammdaten.models import Artikel

User = get_user_model()


class BestandTests(TestCase):
    def setUp(self):
        self.artikel = Artikel.objects.create(name="Schraube")
        self.user = User.objects.create_user("lager", password="x")

    def test_bestand_aendern_protokolliert_bewegung(self):
        services.bestand_aendern(self.artikel, 5, "einlagerung", "manual", None, "Test", self.user)
        self.artikel.refresh_from_db()
        self.assertEqual(self.artikel.bestand, Decimal("5"))
        bewegung = Lagerbewegung.objects.get()
        self.assertEqual((bewegung.menge, bewegung.typ, bewegung.benutzer), (Decimal("5"), "einlagerung", self.user))

    def test_artikel_ohne_lagerfuehrung_wird_uebersprungen(self):
        dienst = Artikel.objects.create(name="Beratung", lagerfuehrung=False)
        self.assertIsNone(services.bestand_aendern(dienst, -3, "verkauf"))
        dienst.refresh_from_db()
        self.assertEqual(dienst.bestand, 0)
        self.assertEqual(Lagerbewegung.objects.count(), 0)

    def test_wareneingang(self):
        services.wareneingang(self.artikel, "2,5".replace(",", "."), "", self.user)
        self.artikel.refresh_from_db()
        self.assertEqual(self.artikel.bestand, Decimal("2.5"))
        self.assertEqual(Lagerbewegung.objects.get().notiz, "Wareneingang")

    def test_wareneingang_verlangt_positive_menge(self):
        with self.assertRaises(LagerFehler):
            services.wareneingang(self.artikel, 0)
        with self.assertRaises(LagerFehler):
            services.wareneingang(self.artikel, -1)

    def test_wareneingang_ohne_seriennummer_bei_seriennummernartikel_abgelehnt(self):
        laptop = Artikel.objects.create(name="Laptop", seriennummern=True)
        with self.assertRaises(LagerFehler):
            services.wareneingang(laptop, 1)

    def test_inventurkorrektur_bucht_die_differenz(self):
        services.wareneingang(self.artikel, 10)
        services.inventurkorrektur(self.artikel, 7, "Zählung", self.user)
        self.artikel.refresh_from_db()
        self.assertEqual(self.artikel.bestand, Decimal("7"))
        letzte = Lagerbewegung.objects.first()
        self.assertEqual((letzte.typ, letzte.menge, letzte.notiz), ("korrektur", Decimal("-3"), "Zählung"))

    def test_inventurkorrektur_ohne_aenderung_bucht_nichts(self):
        services.wareneingang(self.artikel, 10)
        self.assertIsNone(services.inventurkorrektur(self.artikel, 10))
        self.assertEqual(Lagerbewegung.objects.count(), 1)

    def test_inventurkorrektur_bei_seriennummernartikel_abgelehnt(self):
        laptop = Artikel.objects.create(name="Laptop", seriennummern=True)
        with self.assertRaises(LagerFehler):
            services.inventurkorrektur(laptop, 3)

    def test_negativer_istbestand_abgelehnt(self):
        with self.assertRaises(LagerFehler):
            services.inventurkorrektur(self.artikel, -1)


class SeriennummernTests(TestCase):
    def setUp(self):
        self.laptop = Artikel.objects.create(name="Laptop", seriennummern=True)

    def test_text_zu_nummern(self):
        self.assertEqual(
            services.seriennummern_aus_text(" A1 \r\n\nB2\nA1\n  \nC3"), ["A1", "B2", "C3"]
        )

    def test_einlagern_erhoeht_bestand_um_anzahl(self):
        anzahl, doppelt = services.seriennummern_einlagern(self.laptop, ["A1", "B2", "C3"])
        self.laptop.refresh_from_db()
        self.assertEqual((anzahl, doppelt), (3, []))
        self.assertEqual(self.laptop.bestand, Decimal("3"))
        self.assertEqual(Seriennummer.objects.filter(artikel=self.laptop, status="lager").count(), 3)

    def test_doppelte_seriennummern_werden_uebersprungen(self):
        services.seriennummern_einlagern(self.laptop, ["A1"])
        anzahl, doppelt = services.seriennummern_einlagern(self.laptop, ["A1", "B2"])
        self.laptop.refresh_from_db()
        self.assertEqual((anzahl, doppelt), (1, ["A1"]))
        self.assertEqual(self.laptop.bestand, Decimal("2"))

    def test_einlagern_nur_fuer_seriennummernartikel(self):
        schraube = Artikel.objects.create(name="Schraube")
        with self.assertRaises(LagerFehler):
            services.seriennummern_einlagern(schraube, ["X"])

    def test_einlagern_ohne_nummern_abgelehnt(self):
        with self.assertRaises(LagerFehler):
            services.seriennummern_einlagern(self.laptop, [])

    def test_defekt_reduziert_bestand(self):
        services.seriennummern_einlagern(self.laptop, ["A1", "B2"])
        serie = Seriennummer.objects.get(nummer="A1")
        services.seriennummer_defekt(serie)
        serie.refresh_from_db()
        self.laptop.refresh_from_db()
        self.assertEqual(serie.status, "defekt")
        self.assertEqual(self.laptop.bestand, Decimal("1"))
        with self.assertRaises(LagerFehler):
            services.seriennummer_defekt(serie)

    def test_entfernen_loescht_und_reduziert_bestand(self):
        services.seriennummern_einlagern(self.laptop, ["A1", "B2"])
        serie = Seriennummer.objects.get(nummer="B2")
        services.seriennummer_entfernen(serie)
        self.laptop.refresh_from_db()
        self.assertFalse(Seriennummer.objects.filter(nummer="B2").exists())
        self.assertEqual(self.laptop.bestand, Decimal("1"))

    def test_verkaufte_seriennummer_laesst_sich_nicht_entfernen(self):
        services.seriennummern_einlagern(self.laptop, ["A1"])
        serie = Seriennummer.objects.get()
        serie.status = "verkauft"
        serie.save()
        with self.assertRaises(LagerFehler):
            services.seriennummer_entfernen(serie)
        self.assertTrue(Seriennummer.objects.filter(pk=serie.pk).exists())
