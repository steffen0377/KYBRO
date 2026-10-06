import io
from datetime import date
from decimal import Decimal

import pikepdf
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from facturx import get_facturx_xml_from_pdf, xml_check_xsd
from lxml import etree

from belege import pdf, services, zugferd
from belege.models import Angebot, AngebotPosition
from einstellungen.models import Firma, Formulareinstellung
from einstellungen import formulare
from einstellungen.services import naechste_belegnummer
from stammdaten.models import Kunde

User = get_user_model()


def rechnung(steuer="19", kunde=None):
    firma = Firma.holen()
    firma.firmenname, firma.strasse, firma.plz, firma.ort = "IT-Dienst GmbH", "Weg 1", "12345", "Stadt"
    firma.iban, firma.bic, firma.ust_id = "DE02120300000000202051", "BYLADEM1001", "DE123456789"
    firma.save()
    kunde = kunde or Kunde.objects.create(firma="Muster GmbH", strasse="Str. 2", plz="54321", ort="Dorf")
    a = Angebot.objects.create(nummer=naechste_belegnummer("angebot"), kunde=kunde, datum=date(2026, 3, 1))
    AngebotPosition.objects.create(angebot=a, position=1, beschreibung="Beratung ä ö ü €", einheit="h",
                                   menge=Decimal("3"), einzelpreis=Decimal("33.33"), rabatt=Decimal("10"),
                                   steuersatz=Decimal(steuer))
    AngebotPosition.objects.create(angebot=a, position=2, beschreibung="Fahrt", menge=Decimal("1"),
                                   einzelpreis=Decimal("10"), steuersatz=Decimal("7"))
    a.summen_neu_berechnen()
    return services.rechnung_aus_angebot(a)[1]


class FormatTests(TestCase):
    def test_zahlen(self):
        self.assertEqual(pdf.geld(Decimal("1234.5")), "1.234,50 €")
        self.assertEqual(pdf.menge_text(Decimal("3.00")), "3")
        self.assertEqual(pdf.menge_text(Decimal("2.50")), "2,50")

    def test_einstellungen_kette(self):
        self.assertEqual(formulare.holen("rechnung", "titel"), "Rechnung")
        Formulareinstellung.objects.create(bereich="global", schluessel="akzentfarbe", wert="#ff0000")
        self.assertEqual(formulare.holen("rechnung", "akzentfarbe"), "#ff0000")
        Formulareinstellung.objects.create(bereich="rechnung", schluessel="akzentfarbe", wert="#00ff00")
        self.assertEqual(formulare.holen("rechnung", "akzentfarbe"), "#00ff00")
        self.assertEqual(formulare.holen("angebot", "akzentfarbe"), "#ff0000")


class ZugferdTests(TestCase):
    def test_xml_ist_schemagueltig_und_summen_stimmen(self):
        r = rechnung()
        xml = zugferd.rechnung_xml(r)
        zugferd.pruefen(xml)
        wurzel = etree.fromstring(xml)
        ns = zugferd.NS
        brutto = wurzel.findtext(".//ram:GrandTotalAmount", namespaces=ns)
        self.assertEqual(Decimal(brutto), r.brutto)
        self.assertEqual(wurzel.findtext(".//ram:ID", namespaces=ns), zugferd.PROFIL)
        self.assertEqual(len(wurzel.findall(".//ram:ApplicableHeaderTradeSettlement/ram:ApplicableTradeTax", ns)), 2)

    def test_xml_mit_allen_optionalen_firmen_und_kundenfeldern_schemagueltig(self):
        """Regression: E-Mail der Firma vor der Anschrift machte die XML ungültig (Fehler beim PDF-Aufruf)."""
        kunde = Kunde.objects.create(
            firma="Muster GmbH", strasse="Str. 2", plz="54321", ort="Dorf", email="kunde@example.com",
            ust_id="DE987654321", telefon="0123",
        )
        r = rechnung(kunde=kunde)
        firma = Firma.holen()
        firma.email, firma.telefon, firma.steuernummer, firma.ust_id = "info@example.com", "0987", "123/456/78901", "DE123456789"
        firma.kontoinhaber, firma.bank = "IT-Dienst GmbH", "Testbank"
        firma.save()
        xml = zugferd.rechnung_xml(r)
        zugferd.pruefen(xml)
        wurzel = etree.fromstring(xml)
        verkaeufer = wurzel.find(".//ram:SellerTradeParty", namespaces=zugferd.NS)
        reihenfolge = [etree.QName(k).localname for k in verkaeufer]
        self.assertLess(reihenfolge.index("PostalTradeAddress"), reihenfolge.index("URIUniversalCommunication"))
        self.assertLess(reihenfolge.index("URIUniversalCommunication"), reihenfolge.index("SpecifiedTaxRegistration"))

    def test_steuerbefreit_nutzt_kategorie_e_mit_grund(self):
        k = Kunde.objects.create(firma="Frei", steuerbefreit=True, befreiungsgrund="Drittland")
        a = Angebot.objects.create(nummer="X1", kunde=k, datum=date(2026, 3, 1))
        AngebotPosition.objects.create(angebot=a, position=1, beschreibung="X", menge=Decimal("1"),
                                       einzelpreis=Decimal("100"), steuersatz=Decimal("0"))
        a.summen_neu_berechnen()
        r = services.rechnung_aus_angebot(a)[1]
        xml = zugferd.rechnung_xml(r)
        zugferd.pruefen(xml)
        w = etree.fromstring(xml)
        self.assertEqual(w.findtext(".//ram:ApplicableHeaderTradeSettlement/ram:ApplicableTradeTax/ram:CategoryCode", namespaces=zugferd.NS), "E")
        self.assertEqual(w.findtext(".//ram:ExemptionReason", namespaces=zugferd.NS), "Drittland")

    def test_laendercode(self):
        self.assertEqual(zugferd.laendercode("Deutschland"), "DE")
        self.assertEqual(zugferd.laendercode("Österreich"), "AT")
        self.assertEqual(zugferd.laendercode("fr"), "FR")


class PdfTests(TestCase):
    def test_rechnung_pdf_enthaelt_text_und_xml(self):
        r = rechnung()
        daten = pdf.beleg_pdf(r)
        self.assertTrue(daten.startswith(b"%PDF"))
        name, xml = get_facturx_xml_from_pdf(io.BytesIO(daten), check_xsd=True)
        self.assertEqual(name, "factur-x.xml")
        self.assertIn(r.nummer.encode(), xml)
        with pikepdf.open(io.BytesIO(daten)) as p:
            self.assertGreaterEqual(len(p.pages), 1)

    def test_angebot_pdf_ohne_xml(self):
        a = rechnung().angebot
        daten = pdf.beleg_pdf(a)
        self.assertTrue(daten.startswith(b"%PDF"))
        self.assertFalse(get_facturx_xml_from_pdf(io.BytesIO(daten), check_xsd=False)[0])

    def test_ansicht_und_rechte(self):
        r = rechnung()
        url = reverse("belege:rechnungen_pdf", args=[r.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(User.objects.create_superuser("a", password="Sehr-geheim-2026"))
        antwort = self.client.get(url)
        self.assertEqual(antwort["Content-Type"], "application/pdf")
        self.assertIn(f'filename="{r.nummer}.pdf"', antwort["Content-Disposition"])
        self.assertEqual(self.client.get(reverse("belege:angebote_pdf", args=[r.angebot.pk])).status_code, 200)
        self.assertContains(self.client.get(reverse("belege:rechnungen_ansehen", args=[r.pk])), url)

    def test_briefbogen_elemente_erscheinen_auf_jeder_seite_des_pdf(self):
        from pypdf import PdfReader
        from einstellungen.models import BriefbogenElement
        BriefbogenElement.objects.create(
            typ="textbox", x_mm=20, y_mm=280, breite_mm=170, text="Fuss %CompanyName%", schriftgroesse=8,
            vertikale_ausrichtung="unten",
        )
        r = rechnung()
        for i in range(60):  # erzwingt mehrere Seiten
            r.positionen.create(position=10 + i, beschreibung=f"Zusatz {i}", menge=1, einzelpreis=1, steuersatz=19)
        leser = PdfReader(io.BytesIO(pdf.beleg_pdf(r)))
        self.assertGreater(len(leser.pages), 1)
        for seite in leser.pages:
            self.assertIn("Fuss IT-Dienst GmbH", seite.extract_text())
