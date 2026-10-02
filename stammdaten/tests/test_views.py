from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from lager.models import Lagerbewegung
from stammdaten.models import (
    Ansprechpartner, Artikel, ArtikelLieferant, Kategorie, Kunde, Lieferant, Preisoption, Sonderpreis,
)

User = get_user_model()


def verwaltung(praefix, gesamt=0, initial=0):
    return {
        f"{praefix}-TOTAL_FORMS": str(gesamt),
        f"{praefix}-INITIAL_FORMS": str(initial),
        f"{praefix}-MIN_NUM_FORMS": "0",
        f"{praefix}-MAX_NUM_FORMS": "1000",
    }


def artikel_daten(**ueberschreibungen):
    daten = {
        "name": "Netzwerkkabel", "einheit": "Stk.", "einkaufspreis": "1,50", "verkaufspreis": "4,90",
        "steuersatz": "19,00", "lagerfuehrung": "on", "mindestbestand": "2", "aktiv": "on",
        "anfangsbestand": "10",
        **verwaltung("lief"), **verwaltung("sonder"), **verwaltung("preis"),
    }
    daten.update(ueberschreibungen)
    return {k: v for k, v in daten.items() if v is not None}


class AdminTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", password="Sehr-geheim-2026")
        self.client.force_login(self.admin)


class ArtikelViewTests(AdminTestCase):
    def test_anlegen_vergibt_nummer_und_bucht_anfangsbestand(self):
        antwort = self.client.post(reverse("stammdaten:artikel_neu"), artikel_daten())
        self.assertRedirects(antwort, reverse("stammdaten:artikel_liste"))
        artikel = Artikel.objects.get()
        self.assertEqual(artikel.artikelnummer, f"{artikel.pk:05d}")
        self.assertEqual(artikel.verkaufspreis, Decimal("4.90"))  # Komma als Dezimaltrenner
        self.assertEqual(artikel.bestand, Decimal("10"))
        bewegung = Lagerbewegung.objects.get()
        self.assertEqual((bewegung.typ, bewegung.notiz, bewegung.benutzer), ("einlagerung", "Anfangsbestand", self.admin))

    def test_seriennummernartikel_bucht_keinen_anfangsbestand(self):
        self.client.post(reverse("stammdaten:artikel_neu"), artikel_daten(seriennummern="on"))
        self.assertEqual(Artikel.objects.get().bestand, 0)
        self.assertEqual(Lagerbewegung.objects.count(), 0)

    def test_ohne_lagerfuehrung_kein_bestand_und_keine_seriennummern(self):
        self.client.post(
            reverse("stammdaten:artikel_neu"),
            artikel_daten(lagerfuehrung=None, seriennummern="on"),
        )
        artikel = Artikel.objects.get()
        self.assertFalse(artikel.seriennummern)
        self.assertEqual(artikel.bestand, 0)

    def test_name_ist_pflicht(self):
        antwort = self.client.post(reverse("stammdaten:artikel_neu"), artikel_daten(name=""))
        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(Artikel.objects.count(), 0)

    def test_leere_ean_wird_zu_null_und_blockiert_nicht(self):
        self.client.post(reverse("stammdaten:artikel_neu"), artikel_daten(ean=""))
        self.client.post(reverse("stammdaten:artikel_neu"), artikel_daten(name="Zweiter", ean=""))
        self.assertEqual(Artikel.objects.filter(ean__isnull=True).count(), 2)

    def test_anlegen_mit_lieferant_sonderpreis_und_abomodell(self):
        lieferant = Lieferant.objects.create(firma="Zulieferer")
        kunde = Kunde.objects.create(firma="Muster GmbH")
        daten = artikel_daten(
            **verwaltung("lief", 1), **{"lief-0-lieferant": lieferant.pk, "lief-0-lieferanten_artikelnummer": "Z-1", "lief-0-hek": "1,20"},
            **verwaltung("sonder", 1), **{"sonder-0-kunde": kunde.pk, "sonder-0-art": "percent", "sonder-0-wert": "10", "sonder-0-aktiv": "on"},
            **verwaltung("preis", 2),
            **{"preis-0-abrechnung": "einmalig", "preis-0-preis": "4,90", "preis-0-aktiv": "on"},
            **{"preis-1-abrechnung": "monatlich", "preis-1-preis": "2,00", "preis-1-mindestlaufzeit_monate": "12",
               "preis-1-kuendigungsfrist_tage": "30", "preis-1-aktiv": "on"},
        )
        self.client.post(reverse("stammdaten:artikel_neu"), daten)
        artikel = Artikel.objects.get()
        al = ArtikelLieferant.objects.get(artikel=artikel)
        self.assertEqual((al.lieferant, al.lieferanten_artikelnummer, al.hek), (lieferant, "Z-1", Decimal("1.20")))
        sp = Sonderpreis.objects.get(artikel=artikel)
        self.assertEqual((sp.kunde, sp.art, sp.wert), (kunde, "percent", Decimal("10")))
        optionen = {o.abrechnung: o for o in artikel.preisoptionen.all()}
        self.assertEqual(set(optionen), {"einmalig", "monatlich"})
        self.assertEqual(optionen["monatlich"].mindestlaufzeit_monate, 12)
        self.assertIsNone(optionen["einmalig"].mindestlaufzeit_monate)

    def test_doppelte_preisoption_wird_abgelehnt(self):
        daten = artikel_daten(
            **verwaltung("preis", 2),
            **{"preis-0-abrechnung": "monatlich", "preis-0-preis": "2", "preis-0-aktiv": "on"},
            **{"preis-1-abrechnung": "monatlich", "preis-1-preis": "3", "preis-1-aktiv": "on"},
        )
        antwort = self.client.post(reverse("stammdaten:artikel_neu"), daten)
        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(Artikel.objects.count(), 0)

    def test_doppelter_sonderpreis_je_kunde_wird_abgelehnt(self):
        kunde = Kunde.objects.create(firma="Muster GmbH")
        daten = artikel_daten(
            **verwaltung("sonder", 2),
            **{"sonder-0-kunde": kunde.pk, "sonder-0-art": "fixed", "sonder-0-wert": "1", "sonder-0-aktiv": "on"},
            **{"sonder-1-kunde": kunde.pk, "sonder-1-art": "fixed", "sonder-1-wert": "2", "sonder-1-aktiv": "on"},
        )
        antwort = self.client.post(reverse("stammdaten:artikel_neu"), daten)
        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(Sonderpreis.objects.count(), 0)

    def test_bearbeiten_aendert_nummer_nicht_und_loescht_markierte_zeilen(self):
        kunde = Kunde.objects.create(firma="Muster GmbH")
        artikel = Artikel.objects.create(name="Alt")
        sp = Sonderpreis.objects.create(artikel=artikel, kunde=kunde, wert=3)
        nummer = artikel.artikelnummer
        daten = artikel_daten(
            name="Neu", anfangsbestand=None,
            **verwaltung("sonder", 1, 1),
            **{"sonder-0-id": sp.pk, "sonder-0-artikel": artikel.pk, "sonder-0-kunde": kunde.pk,
               "sonder-0-art": "fixed", "sonder-0-wert": "3", "sonder-0-DELETE": "on"},
        )
        antwort = self.client.post(reverse("stammdaten:artikel_bearbeiten", args=[artikel.pk]), daten)
        self.assertRedirects(antwort, reverse("stammdaten:artikel_liste"))
        artikel.refresh_from_db()
        self.assertEqual((artikel.name, artikel.artikelnummer), ("Neu", nummer))
        self.assertEqual(Sonderpreis.objects.count(), 0)
        self.assertEqual(Lagerbewegung.objects.count(), 0)  # kein erneuter Anfangsbestand

    def test_formular_zeigt_vorhandene_werte(self):
        artikel = Artikel.objects.create(name="Alt", verkaufspreis=Decimal("12.5"))
        antwort = self.client.get(reverse("stammdaten:artikel_bearbeiten", args=[artikel.pk]))
        self.assertContains(antwort, "12,50")
        self.assertContains(antwort, artikel.artikelnummer)

    def test_neues_formular_zeigt_vorgaben(self):
        antwort = self.client.get(reverse("stammdaten:artikel_neu"))
        self.assertContains(antwort, "wird automatisch vergeben")
        self.assertContains(antwort, 'value="19,00"')

    def test_deaktivieren(self):
        artikel = Artikel.objects.create(name="Alt")
        self.client.post(reverse("stammdaten:artikel_deaktivieren", args=[artikel.pk]))
        artikel.refresh_from_db()
        self.assertFalse(artikel.aktiv)
        self.assertEqual(self.client.get(reverse("stammdaten:artikel_deaktivieren", args=[artikel.pk])).status_code, 405)


class ArtikelListeTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.kat = Kategorie.objects.create(name="Kabel")
        self.a = Artikel.objects.create(name="Netzwerkkabel", ean="4006381333931", han="HAN-77")
        self.a.kategorien.add(self.kat)
        self.b = Artikel.objects.create(name="Maus")
        self.c = Artikel.objects.create(name="Alte Tastatur", aktiv=False)

    def namen(self, antwort):
        return [a.name for a in antwort.context["artikel"]]

    def test_standardreihenfolge_aktive_zuerst_dann_name(self):
        self.assertEqual(self.namen(self.client.get(reverse("stammdaten:artikel_liste"))),
                         ["Maus", "Netzwerkkabel", "Alte Tastatur"])

    def test_suche_in_name_nummer_ean_han(self):
        liste = reverse("stammdaten:artikel_liste")
        for suche, erwartet in [("kabel", ["Netzwerkkabel"]), (self.b.artikelnummer, ["Maus"]),
                                ("4006381", ["Netzwerkkabel"]), ("HAN-77", ["Netzwerkkabel"])]:
            self.assertEqual(self.namen(self.client.get(liste, {"q": suche})), erwartet, suche)

    def test_kategoriefilter(self):
        antwort = self.client.get(reverse("stammdaten:artikel_liste"), {"kategorie": self.kat.pk})
        self.assertEqual(self.namen(antwort), ["Netzwerkkabel"])
        self.assertContains(antwort, "Kategorie: Kabel")

    def test_sortierung_nur_nach_zugelassenen_spalten(self):
        liste = reverse("stammdaten:artikel_liste")
        self.assertEqual(self.namen(self.client.get(liste, {"sort": "name", "dir": "desc"}))[0], "Netzwerkkabel")
        # Unbekannte Spalte: keine SQL-Sortierung nach beliebigen Feldern, Standardreihenfolge.
        self.assertEqual(self.namen(self.client.get(liste, {"sort": "verkaufspreis;drop"}))[0], "Maus")

    def test_ajax_liefert_nur_das_tabellenfragment(self):
        antwort = self.client.get(reverse("stammdaten:artikel_liste"), {"ajax": "1", "q": "maus"})
        self.assertTemplateUsed(antwort, "stammdaten/_artikel_tabelle.html")
        self.assertTemplateNotUsed(antwort, "base.html")
        self.assertContains(antwort, "Maus")
        self.assertNotContains(antwort, "Netzwerkkabel")


class KundenViewTests(AdminTestCase):
    def daten(self, **ueberschreibungen):
        daten = {"firma": "Muster GmbH", "land": "Deutschland", "zahlungsart": "ueberweisung",
                 **verwaltung("ansp")}
        daten.update(ueberschreibungen)
        return daten

    def test_anlegen_mit_ansprechpartner(self):
        daten = self.daten(**verwaltung("ansp", 1), **{"ansp-0-nachname": "Meier", "ansp-0-email": "m@example.com"})
        self.assertRedirects(self.client.post(reverse("stammdaten:kunden_neu"), daten), reverse("stammdaten:kunden_liste"))
        kunde = Kunde.objects.get()
        self.assertTrue(kunde.kundennummer.startswith("K-"))
        self.assertEqual(Ansprechpartner.objects.get().kunde, kunde)

    def test_firma_oder_nachname_pflicht(self):
        antwort = self.client.post(reverse("stammdaten:kunden_neu"), self.daten(firma=""))
        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(Kunde.objects.count(), 0)

    def test_steuerbefreiung_braucht_befreiungsgrund(self):
        antwort = self.client.post(reverse("stammdaten:kunden_neu"), self.daten(steuerbefreit="on"))
        self.assertContains(antwort, "Befreiungsgrund")
        self.assertEqual(Kunde.objects.count(), 0)
        self.client.post(reverse("stammdaten:kunden_neu"),
                         self.daten(steuerbefreit="on", befreiungsgrund="§ 4 Nr. 21a UStG"))
        self.assertTrue(Kunde.objects.get().steuerbefreit)

    def test_bearbeiten_und_ansprechpartner_loeschen(self):
        kunde = Kunde.objects.create(firma="Alt")
        ap = Ansprechpartner.objects.create(kunde=kunde, nachname="Meier")
        daten = self.daten(firma="Neu", **verwaltung("ansp", 1, 1),
                           **{"ansp-0-id": ap.pk, "ansp-0-kunde": kunde.pk, "ansp-0-nachname": "Meier", "ansp-0-DELETE": "on"})
        self.client.post(reverse("stammdaten:kunden_bearbeiten", args=[kunde.pk]), daten)
        kunde.refresh_from_db()
        self.assertEqual(kunde.firma, "Neu")
        self.assertEqual(Ansprechpartner.objects.count(), 0)

    def test_suche(self):
        Kunde.objects.create(firma="Alpha GmbH")
        Kunde.objects.create(nachname="Beta")
        antwort = self.client.get(reverse("stammdaten:kunden_liste"), {"q": "alp"})
        self.assertEqual([k.anzeigename for k in antwort.context["kunden"]], ["Alpha GmbH"])

    def test_loeschen(self):
        kunde = Kunde.objects.create(firma="Weg")
        self.client.post(reverse("stammdaten:kunden_loeschen", args=[kunde.pk]))
        self.assertFalse(Kunde.objects.exists())

    def test_buchhaltung_ist_vor_belegen_leer(self):
        kunde = Kunde.objects.create(firma="Muster")
        antwort = self.client.get(reverse("stammdaten:kunden_bearbeiten", args=[kunde.pk]))
        self.assertContains(antwort, "Summe unbezahlter Rechnungen")
        self.assertEqual(antwort.context["offene_summe"], Decimal("0.00"))


class LieferantenUndKategorienTests(AdminTestCase):
    def test_lieferant_anlegen_bearbeiten_loeschen(self):
        daten = {"firma": "Zulieferer AG", "land": "Deutschland", "zahlungsart": "zentralreguliert"}
        self.client.post(reverse("stammdaten:lieferanten_neu"), daten)
        lieferant = Lieferant.objects.get()
        self.assertTrue(lieferant.lieferantennummer.startswith("L-"))
        self.assertEqual(lieferant.zahlungsart, "zentralreguliert")
        self.client.post(reverse("stammdaten:lieferanten_bearbeiten", args=[lieferant.pk]), {**daten, "firma": "Neu AG"})
        lieferant.refresh_from_db()
        self.assertEqual(lieferant.firma, "Neu AG")
        self.client.post(reverse("stammdaten:lieferanten_loeschen", args=[lieferant.pk]))
        self.assertFalse(Lieferant.objects.exists())

    def test_lieferant_ohne_namen_abgelehnt(self):
        antwort = self.client.post(reverse("stammdaten:lieferanten_neu"), {"land": "Deutschland", "zahlungsart": "ueberweisung"})
        self.assertEqual(antwort.status_code, 200)
        self.assertFalse(Lieferant.objects.exists())

    def test_kategorie_anlegen_und_name_eindeutig(self):
        liste = reverse("stammdaten:kategorien_liste")
        self.assertRedirects(self.client.post(reverse("stammdaten:kategorien_neu"), {"name": "Kabel"}), liste)
        antwort = self.client.post(reverse("stammdaten:kategorien_neu"), {"name": "Kabel"})
        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(Kategorie.objects.count(), 1)

    def test_kategorie_zyklus_ueber_formular_nicht_moeglich(self):
        a = Kategorie.objects.create(name="A")
        b = Kategorie.objects.create(name="B", uebergeordnet=a)
        antwort = self.client.post(reverse("stammdaten:kategorien_bearbeiten", args=[a.pk]), {"name": "A", "uebergeordnet": b.pk})
        self.assertEqual(antwort.status_code, 200)
        a.refresh_from_db()
        self.assertIsNone(a.uebergeordnet)

    def test_kategorie_baum_mit_einrueckung(self):
        a = Kategorie.objects.create(name="A")
        b = Kategorie.objects.create(name="B", uebergeordnet=a)
        Kategorie.objects.create(name="C", uebergeordnet=b)
        Kategorie.objects.create(name="Z")
        zeilen = self.client.get(reverse("stammdaten:kategorien_liste")).context["zeilen"]
        self.assertEqual([(z["kategorie"].name, z["tiefe"]) for z in zeilen], [("A", 0), ("B", 1), ("C", 2), ("Z", 0)])

    def test_kategorie_loeschen(self):
        a = Kategorie.objects.create(name="A")
        b = Kategorie.objects.create(name="B", uebergeordnet=a)
        self.client.post(reverse("stammdaten:kategorien_loeschen", args=[a.pk]))
        b.refresh_from_db()
        self.assertIsNone(b.uebergeordnet)


class RechteTests(TestCase):
    def benutzer(self, *rechte):
        gruppe = Group.objects.create(name="G")
        gruppe.permissions.set(Permission.objects.filter(content_type__app_label="accounts", codename__in=rechte))
        user = User.objects.create_user("anna", password="Sehr-geheim-2026")
        user.groups.add(gruppe)
        self.client.force_login(user)

    def test_ohne_anmeldung_login(self):
        url = reverse("stammdaten:artikel_liste")
        self.assertRedirects(self.client.get(url), f"{reverse('accounts:login')}?next={url}")

    def test_ohne_recht_403(self):
        self.benutzer()
        for name in ("artikel_liste", "kunden_liste", "lieferanten_liste", "kategorien_liste"):
            self.assertEqual(self.client.get(reverse(f"stammdaten:{name}")).status_code, 403, name)

    def test_lesen_erlaubt_schreiben_nicht(self):
        self.benutzer("artikel_lesen")
        self.assertEqual(self.client.get(reverse("stammdaten:artikel_liste")).status_code, 200)
        self.assertEqual(self.client.get(reverse("stammdaten:artikel_neu")).status_code, 200)  # GET = lesen
        self.assertEqual(self.client.post(reverse("stammdaten:artikel_neu"), artikel_daten()).status_code, 403)
        self.assertEqual(Artikel.objects.count(), 0)

    def test_schreibrecht_reicht(self):
        self.benutzer("kunden_schreiben")
        antwort = self.client.post(reverse("stammdaten:kunden_neu"), {"firma": "X", "land": "D", "zahlungsart": "ueberweisung", **verwaltung("ansp")})
        self.assertEqual(antwort.status_code, 302)
        self.assertEqual(Kunde.objects.count(), 1)

    def test_neuer_knopf_nur_mit_schreibrecht(self):
        self.benutzer("artikel_lesen")
        self.assertNotContains(self.client.get(reverse("stammdaten:artikel_liste")), reverse("stammdaten:artikel_neu"))
