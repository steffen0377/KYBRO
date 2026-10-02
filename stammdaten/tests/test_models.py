from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from stammdaten.models import Artikel, Kategorie, Kunde, Lieferant, Preisoption, Sonderpreis


class ArtikelModellTests(TestCase):
    def test_artikelnummer_ist_die_fuenfstellige_id(self):
        artikel = Artikel.objects.create(name="Kabel")
        self.assertEqual(artikel.artikelnummer, f"{artikel.pk:05d}")
        self.assertEqual(len(artikel.artikelnummer), 5)

    def test_artikelnummer_bleibt_beim_speichern_gleich(self):
        artikel = Artikel.objects.create(name="Kabel")
        nummer = artikel.artikelnummer
        artikel.name = "Netzwerkkabel"
        artikel.save()
        artikel.refresh_from_db()
        self.assertEqual(artikel.artikelnummer, nummer)

    def test_seriennummern_setzen_lagerfuehrung_voraus(self):
        artikel = Artikel(name="Laptop", lagerfuehrung=False, seriennummern=True)
        with self.assertRaises(ValidationError):
            artikel.full_clean()

    def test_preis_ohne_sonderpreis_ist_der_standardpreis(self):
        artikel = Artikel.objects.create(name="Maus", verkaufspreis=Decimal("20.00"))
        kunde = Kunde.objects.create(firma="Muster GmbH")
        self.assertEqual(artikel.preis_fuer(kunde), Decimal("20.00"))
        self.assertEqual(artikel.preis_fuer(None), Decimal("20.00"))

    def test_fixer_sonderpreis(self):
        artikel = Artikel.objects.create(name="Maus", verkaufspreis=Decimal("20.00"))
        kunde = Kunde.objects.create(firma="Muster GmbH")
        Sonderpreis.objects.create(artikel=artikel, kunde=kunde, art="fixed", wert=Decimal("15.50"))
        self.assertEqual(artikel.preis_fuer(kunde), Decimal("15.50"))

    def test_prozentualer_sonderpreis_ist_rabatt_auf_den_standardpreis(self):
        artikel = Artikel.objects.create(name="Maus", verkaufspreis=Decimal("19.99"))
        kunde = Kunde.objects.create(firma="Muster GmbH")
        Sonderpreis.objects.create(artikel=artikel, kunde=kunde, art="percent", wert=Decimal("10"))
        # 19,99 - 10 % (1,999 -> 2,00) = 17,99
        self.assertEqual(artikel.preis_fuer(kunde), Decimal("17.99"))

    def test_inaktiver_sonderpreis_wird_ignoriert(self):
        artikel = Artikel.objects.create(name="Maus", verkaufspreis=Decimal("20.00"))
        kunde = Kunde.objects.create(firma="Muster GmbH")
        Sonderpreis.objects.create(artikel=artikel, kunde=kunde, wert=Decimal("5"), aktiv=False)
        self.assertEqual(artikel.preis_fuer(kunde), Decimal("20.00"))

    def test_nur_ein_sonderpreis_je_kunde(self):
        artikel = Artikel.objects.create(name="Maus")
        kunde = Kunde.objects.create(firma="Muster GmbH")
        Sonderpreis.objects.create(artikel=artikel, kunde=kunde, wert=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Sonderpreis.objects.create(artikel=artikel, kunde=kunde, wert=2)

    def test_nur_eine_preisoption_je_modell(self):
        artikel = Artikel.objects.create(name="Hosting")
        Preisoption.objects.create(artikel=artikel, abrechnung="monatlich", preis=9)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Preisoption.objects.create(artikel=artikel, abrechnung="monatlich", preis=12)

    def test_unter_mindestbestand(self):
        artikel = Artikel.objects.create(name="Schraube", mindestbestand=5)
        artikel.bestand = Decimal("5")
        self.assertTrue(artikel.unter_mindestbestand)
        artikel.bestand = Decimal("6")
        self.assertFalse(artikel.unter_mindestbestand)
        artikel.lagerfuehrung = False
        artikel.bestand = Decimal("0")
        self.assertFalse(artikel.unter_mindestbestand)


class KategorieModellTests(TestCase):
    def test_eigene_uebergeordnete_ist_ungueltig(self):
        kat = Kategorie.objects.create(name="A")
        kat.uebergeordnet = kat
        with self.assertRaises(ValidationError):
            kat.full_clean()

    def test_zyklus_ueber_mehrere_ebenen_ist_ungueltig(self):
        a = Kategorie.objects.create(name="A")
        b = Kategorie.objects.create(name="B", uebergeordnet=a)
        c = Kategorie.objects.create(name="C", uebergeordnet=b)
        a.uebergeordnet = c
        with self.assertRaises(ValidationError):
            a.full_clean()

    def test_nachfahren(self):
        a = Kategorie.objects.create(name="A")
        b = Kategorie.objects.create(name="B", uebergeordnet=a)
        c = Kategorie.objects.create(name="C", uebergeordnet=b)
        Kategorie.objects.create(name="D")
        self.assertEqual(a.nachfahren_ids(), {b.pk, c.pk})

    def test_loeschen_macht_unterkategorien_zu_hauptkategorien(self):
        a = Kategorie.objects.create(name="A")
        b = Kategorie.objects.create(name="B", uebergeordnet=a)
        a.delete()
        b.refresh_from_db()
        self.assertIsNone(b.uebergeordnet)


class AdressModellTests(TestCase):
    def test_kundennummer(self):
        kunde = Kunde.objects.create(firma="Muster GmbH")
        self.assertEqual(kunde.kundennummer, f"K-{kunde.pk:05d}")

    def test_lieferantennummer(self):
        lieferant = Lieferant.objects.create(firma="Zulieferer AG")
        self.assertEqual(lieferant.lieferantennummer, f"L-{lieferant.pk:05d}")

    def test_firma_oder_nachname_ist_pflicht(self):
        with self.assertRaises(ValidationError):
            Kunde().full_clean()
        Kunde(nachname="Meier").full_clean()  # kein Fehler

    def test_steuerbefreiung_braucht_grund(self):
        kunde = Kunde(firma="Muster", steuerbefreit=True)
        with self.assertRaises(ValidationError) as ctx:
            kunde.full_clean()
        self.assertIn("befreiungsgrund", ctx.exception.message_dict)

    def test_anzeigename(self):
        self.assertEqual(Kunde(firma="Muster GmbH", nachname="X").anzeigename, "Muster GmbH")
        self.assertEqual(Kunde(vorname="Max", nachname="Meier").anzeigename, "Max Meier")
