from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from belege import services
from belege.abos import abo_rechnungen_erzeugen, abo_kuendigen
from belege.models import Abo, Angebot, AngebotPosition, Auftrag, Rechnung, RechnungPosition, berechne_summen
from einstellungen.models import Nummernkreis
from einstellungen.services import naechste_belegnummer
from lager.models import Lagerbewegung, Seriennummer
from stammdaten.models import Artikel, Kunde, Preisoption

User = get_user_model()


def kunde(**kw):
    return Kunde.objects.create(firma="Muster GmbH", **kw)


def angebot_mit_position(k=None, artikel=None, menge="2", preis="10.00", rabatt="0", steuer="19", **pos):
    k = k or kunde()
    angebot = Angebot.objects.create(nummer=naechste_belegnummer("angebot"), kunde=k, datum=date(2026, 3, 1))
    AngebotPosition.objects.create(
        angebot=angebot, position=1, artikel=artikel, beschreibung="Test", einheit="Stk",
        menge=Decimal(menge), einzelpreis=Decimal(preis), rabatt=Decimal(rabatt), steuersatz=Decimal(steuer), **pos,
    )
    angebot.summen_neu_berechnen()
    return angebot


class NummernTests(TestCase):
    def test_fortlaufend_und_jahresweise(self):
        self.assertEqual(naechste_belegnummer("rechnung", date(2026, 1, 5)), "RE-2026-0001")
        self.assertEqual(naechste_belegnummer("rechnung", date(2026, 6, 5)), "RE-2026-0002")
        self.assertEqual(naechste_belegnummer("rechnung", date(2027, 1, 2)), "RE-2027-0001")
        self.assertEqual(naechste_belegnummer("angebot", date(2026, 1, 2)), "ANG-2026-0001")

    def test_nummer_verfaellt_bei_abbruch_nicht(self):
        try:
            with self.assertRaises(RuntimeError):
                from django.db import transaction
                with transaction.atomic():
                    naechste_belegnummer("rechnung", date(2026, 1, 1))
                    raise RuntimeError
        finally:
            pass
        self.assertEqual(naechste_belegnummer("rechnung", date(2026, 1, 1)), "RE-2026-0001")


class SummenTests(TestCase):
    def test_steuer_je_satz_auf_summe(self):
        angebot = angebot_mit_position(menge="3", preis="0.33", steuer="19")
        AngebotPosition.objects.create(
            angebot=angebot, position=2, beschreibung="B", menge=Decimal("1"),
            einzelpreis=Decimal("10"), steuersatz=Decimal("7"),
        )
        angebot.summen_neu_berechnen()
        angebot.refresh_from_db()
        self.assertEqual(angebot.netto, Decimal("10.99"))
        self.assertEqual(angebot.steuer, Decimal("0.19") + Decimal("0.70"))
        self.assertEqual(angebot.brutto, angebot.netto + angebot.steuer)

    def test_rabatt(self):
        angebot = angebot_mit_position(menge="2", preis="10.00", rabatt="10")
        angebot.refresh_from_db()
        self.assertEqual(angebot.netto, Decimal("18.00"))
        self.assertEqual(angebot.brutto, Decimal("21.42"))


class UmwandlungTests(TestCase):
    def test_angebot_zu_auftrag_zu_rechnung_idempotent(self):
        angebot = angebot_mit_position()
        auftrag, neu = services.auftrag_aus_angebot(angebot)
        self.assertTrue(neu)
        self.assertEqual(services.auftrag_aus_angebot(angebot), (auftrag, False))
        self.assertEqual(Auftrag.objects.count(), 1)
        angebot.refresh_from_db()
        self.assertEqual(angebot.status, Angebot.Status.ANGENOMMEN)
        self.assertEqual(auftrag.brutto, angebot.brutto)
        rechnung = services.rechnung_aus_auftrag(auftrag)
        self.assertEqual(rechnung.positionen.count(), 1)
        self.assertEqual(rechnung.brutto, auftrag.brutto)
        with self.assertRaises(services.BelegFehler):
            services.rechnung_aus_auftrag(auftrag)
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, Auftrag.Status.ABGESCHLOSSEN)

    def test_stornierter_auftrag_nicht_abrechenbar(self):
        auftrag, _ = services.auftrag_aus_angebot(angebot_mit_position())
        auftrag.status = Auftrag.Status.STORNIERT
        auftrag.save()
        with self.assertRaises(services.BelegFehler):
            services.rechnung_aus_auftrag(auftrag)

    def test_schnellweg(self):
        auftrag, rechnung = services.rechnung_aus_angebot(angebot_mit_position())
        self.assertEqual(rechnung.auftrag, auftrag)
        self.assertEqual(rechnung.status, Rechnung.Status.ENTWURF)

    def test_angebot_status_angenommen_legt_auftrag_an(self):
        angebot = angebot_mit_position()
        self.assertIsNotNone(services.angebot_status_aendern(angebot, "angenommen"))
        self.assertIsNone(services.angebot_status_aendern(angebot, "abgelehnt"))
        with self.assertRaises(services.BelegFehler):
            services.angebot_status_aendern(angebot, "quatsch")


class LagerTests(TestCase):
    def setUp(self):
        self.artikel = Artikel.objects.create(name="Kabel", bestand=Decimal("10"))

    def rechnung(self, menge="3"):
        return services.rechnung_aus_angebot(angebot_mit_position(artikel=self.artikel, menge=menge))[1]

    def test_buchung_bei_erstellung(self):
        self.rechnung()
        self.artikel.refresh_from_db()
        self.assertEqual(self.artikel.bestand, Decimal("7"))

    def test_bearbeiten_bucht_neu(self):
        r = self.rechnung()
        r.positionen.update(menge=Decimal("5"))
        services.rechnung_nach_bearbeiten(r, neu=False)
        self.artikel.refresh_from_db()
        self.assertEqual(self.artikel.bestand, Decimal("5"))

    def test_loeschen_und_stornieren_des_entwurfs_stellt_bestand_her(self):
        r = self.rechnung()
        services.rechnung_loeschen(r)
        self.artikel.refresh_from_db()
        self.assertEqual(self.artikel.bestand, Decimal("10"))
        r2 = self.rechnung()
        services.rechnung_status_aendern(r2, "storniert")
        self.artikel.refresh_from_db()
        self.assertEqual(self.artikel.bestand, Decimal("10"))

    def test_ausgestellte_rechnung_nicht_loeschbar_und_nicht_zurueck(self):
        r = self.rechnung()
        services.rechnung_status_aendern(r, "versendet")
        with self.assertRaises(services.BelegFehler):
            services.rechnung_loeschen(r)
        with self.assertRaises(services.BelegFehler):
            services.rechnung_status_aendern(r, "entwurf")

    def test_seriennummern_werden_separat_zugeordnet(self):
        laptop = Artikel.objects.create(name="Laptop", seriennummern=True)
        s1 = Seriennummer.objects.create(artikel=laptop, nummer="A1")
        Seriennummer.objects.create(artikel=laptop, nummer="A2")
        r = services.rechnung_aus_angebot(angebot_mit_position(artikel=laptop, menge="1"))[1]
        self.assertEqual(Lagerbewegung.objects.filter(artikel=laptop, bezug_typ="rechnung").count(), 0)
        offen = services.offene_seriennummern(r)
        self.assertEqual(len(offen), 1)
        services.seriennummern_zuordnen(r, {laptop.pk: [s1.pk]})
        s1.refresh_from_db()
        self.assertEqual((s1.status, s1.rechnung), (Seriennummer.Status.VERKAUFT, r))
        services.rechnung_loeschen(r)
        s1.refresh_from_db()
        self.assertEqual(s1.status, Seriennummer.Status.LAGER)


class AboTests(TestCase):
    def setUp(self):
        self.artikel = Artikel.objects.create(name="Hosting", lagerfuehrung=False)
        Preisoption.objects.create(artikel=self.artikel, abrechnung="monatlich", preis=Decimal("20"))
        self.option = self.artikel.preisoptionen.get()

    def ausgestellte_rechnung(self):
        a = angebot_mit_position(artikel=self.artikel, menge="1", preis="20", abrechnung="monatlich", preisoption=self.option)
        r = services.rechnung_aus_angebot(a)[1]
        services.rechnung_status_aendern(r, "versendet")
        return r

    def test_abo_beim_ersten_verlassen_des_entwurfs(self):
        r = self.ausgestellte_rechnung()
        abo = Abo.objects.get()
        self.assertEqual((abo.zyklus, abo.preis, abo.ursprungsrechnung), ("monatlich", Decimal("20.00"), r))
        services.rechnung_status_aendern(r, "bezahlt")
        self.assertEqual(Abo.objects.count(), 1)

    def test_entwurf_direkt_storniert_legt_kein_abo_an(self):
        a = angebot_mit_position(artikel=self.artikel, menge="1", abrechnung="monatlich", preisoption=self.option)
        r = services.rechnung_aus_angebot(a)[1]
        services.rechnung_status_aendern(r, "storniert")
        self.assertEqual(Abo.objects.count(), 0)

    def test_folgerechnungen_idempotent(self):
        self.ausgestellte_rechnung()
        abo = Abo.objects.get()
        faellig = abo.naechste_abrechnung
        erste = abo_rechnungen_erzeugen(faellig)
        zweite = abo_rechnungen_erzeugen(faellig)
        self.assertEqual(len(erste), 1)
        self.assertEqual(zweite, [])
        self.assertEqual(Rechnung.objects.filter(abo=abo).count(), 1)
        folge = erste[0]
        self.assertEqual(folge.status, Rechnung.Status.ENTWURF)
        services.rechnung_status_aendern(folge, "versendet")
        abo.refresh_from_db()
        self.assertGreater(abo.naechste_abrechnung, faellig)

    def test_kuendigung(self):
        self.ausgestellte_rechnung()
        abo = Abo.objects.get()
        abo_kuendigen(abo, date(2026, 3, 10))
        abo.refresh_from_db()
        self.assertEqual(abo.status, Abo.Status.GEKUENDIGT)
        self.assertIsNotNone(abo.kuendigung_wirksam)
