"""E-Rechnung: ZUGFeRD / Factur-X, Profil EN 16931 (CII-XML).

Das XML wird aus den Rechnungsdaten erzeugt und vom Paket ``factur-x`` als
PDF/A-3-Anhang in das PDF eingebettet. Die Summen stammen unverändert aus
``berechne_summen`` und stimmen mit dem PDF überein.
"""

from decimal import Decimal

from facturx import generate_from_binary, xml_check_xsd
from lxml import etree

from einstellungen.models import Firma

from .models import berechne_summen

NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
    "qdt": "urn:un:unece:uncefact:data:standard:QualifiedDataType:100",
}
PROFIL = "urn:cen.eu:en16931:2017"
BEFREIUNGSGRUND_STANDARD = "Steuerfrei"

LAENDER = {
    "": "DE", "deutschland": "DE", "germany": "DE", "österreich": "AT", "austria": "AT",
    "schweiz": "CH", "switzerland": "CH", "frankreich": "FR", "niederlande": "NL",
    "belgien": "BE", "luxemburg": "LU", "italien": "IT", "spanien": "ES", "polen": "PL",
    "dänemark": "DK", "tschechien": "CZ",
}


def laendercode(name: str) -> str:
    name = (name or "").strip()
    if len(name) == 2 and name.isalpha():
        return name.upper()
    return LAENDER.get(name.lower(), "DE")


def _b(wert) -> str:
    return f"{Decimal(wert):.2f}"


def _datum(d) -> str:
    return d.strftime("%Y%m%d")


class _Baum:
    """Kleiner Helfer zum Aufbau des CII-XML mit Namensraum-Kürzeln."""

    def __init__(self):
        self.wurzel = etree.Element(f"{{{NS['rsm']}}}CrossIndustryInvoice", nsmap=NS)

    @staticmethod
    def q(pfad: str) -> str:
        praefix, name = pfad.split(":")
        return f"{{{NS[praefix]}}}{name}"

    def neu(self, eltern, pfad, text=None, **attribute):
        e = etree.SubElement(eltern, self.q(pfad), **attribute)
        if text is not None:
            e.text = str(text)
        return e


def rechnung_xml(rechnung) -> bytes:
    """Erzeugt das EN-16931-XML (CII) einer Rechnung."""
    firma = Firma.holen()
    kunde = rechnung.kunde
    positionen = list(rechnung.positionen.all())
    summen = berechne_summen(positionen)
    befreit = kunde.steuerbefreit
    grund = (kunde.befreiungsgrund or "").strip() or BEFREIUNGSGRUND_STANDARD

    t = _Baum()
    w = t.wurzel
    ctx = t.neu(w, "rsm:ExchangedDocumentContext")
    t.neu(t.neu(ctx, "ram:GuidelineSpecifiedDocumentContextParameter"), "ram:ID", PROFIL)

    dok = t.neu(w, "rsm:ExchangedDocument")
    t.neu(dok, "ram:ID", rechnung.nummer)
    t.neu(dok, "ram:TypeCode", "380")
    t.neu(t.neu(dok, "ram:IssueDateTime"), "udt:DateTimeString", _datum(rechnung.datum), format="102")
    if rechnung.notizen.strip():
        t.neu(t.neu(dok, "ram:IncludedNote"), "ram:Content", rechnung.notizen.strip())

    handel = t.neu(w, "rsm:SupplyChainTradeTransaction")

    for nr, p in enumerate(positionen, start=1):
        zeile = t.neu(handel, "ram:IncludedSupplyChainTradeLineItem")
        t.neu(t.neu(zeile, "ram:AssociatedDocumentLineDocument"), "ram:LineID", nr)
        produkt = t.neu(zeile, "ram:SpecifiedTradeProduct")
        t.neu(produkt, "ram:Name", p.beschreibung)
        # Der Stückpreis wird nach Rabatt angegeben, damit Menge x Preis = Zeilensumme gilt.
        netto_preis = p.einzelpreis * (Decimal(100) - p.rabatt) / Decimal(100)
        preis = t.neu(t.neu(zeile, "ram:SpecifiedLineTradeAgreement"), "ram:NetPriceProductTradePrice")
        t.neu(preis, "ram:ChargeAmount", f"{netto_preis:.4f}")
        t.neu(t.neu(zeile, "ram:SpecifiedLineTradeDelivery"), "ram:BilledQuantity", f"{p.menge:.4f}", unitCode="C62")
        abrechnung = t.neu(zeile, "ram:SpecifiedLineTradeSettlement")
        steuer = t.neu(abrechnung, "ram:ApplicableTradeTax")
        t.neu(steuer, "ram:TypeCode", "VAT")
        t.neu(steuer, "ram:CategoryCode", "E" if p.steuersatz == 0 else "S")
        t.neu(steuer, "ram:RateApplicablePercent", _b(p.steuersatz))
        t.neu(t.neu(abrechnung, "ram:SpecifiedTradeSettlementLineMonetarySummation"), "ram:LineTotalAmount", _b(p.netto))

    vereinbarung = t.neu(handel, "ram:ApplicableHeaderTradeAgreement")
    t.neu(vereinbarung, "ram:BuyerReference", rechnung.nummer)

    verkaeufer = t.neu(vereinbarung, "ram:SellerTradeParty")
    t.neu(verkaeufer, "ram:Name", firma.firmenname or "Firma")
    # Reihenfolge laut Schema: Name, Anschrift, Kommunikation (E-Mail), Steuerregistrierungen.
    adresse = t.neu(verkaeufer, "ram:PostalTradeAddress")
    t.neu(adresse, "ram:PostcodeCode", firma.plz)
    t.neu(adresse, "ram:LineOne", firma.strasse)
    t.neu(adresse, "ram:CityName", firma.ort)
    t.neu(adresse, "ram:CountryID", laendercode(firma.land))
    if firma.email:
        t.neu(t.neu(verkaeufer, "ram:URIUniversalCommunication"), "ram:URIID", firma.email, schemeID="EM")
    if firma.ust_id:
        t.neu(t.neu(verkaeufer, "ram:SpecifiedTaxRegistration"), "ram:ID", firma.ust_id, schemeID="VA")
    if firma.steuernummer:
        t.neu(t.neu(verkaeufer, "ram:SpecifiedTaxRegistration"), "ram:ID", firma.steuernummer, schemeID="FC")

    kaeufer = t.neu(vereinbarung, "ram:BuyerTradeParty")
    t.neu(kaeufer, "ram:Name", kunde.anzeigename)
    adresse = t.neu(kaeufer, "ram:PostalTradeAddress")
    t.neu(adresse, "ram:PostcodeCode", kunde.plz)
    t.neu(adresse, "ram:LineOne", kunde.strasse)
    t.neu(adresse, "ram:CityName", kunde.ort)
    t.neu(adresse, "ram:CountryID", laendercode(kunde.land))
    if kunde.ust_id:
        t.neu(t.neu(kaeufer, "ram:SpecifiedTaxRegistration"), "ram:ID", kunde.ust_id, schemeID="VA")

    lieferung = t.neu(handel, "ram:ApplicableHeaderTradeDelivery")
    leistung = rechnung.leistungsdatum or rechnung.datum
    t.neu(
        t.neu(t.neu(lieferung, "ram:ActualDeliverySupplyChainEvent"), "ram:OccurrenceDateTime"),
        "udt:DateTimeString", _datum(leistung), format="102",
    )

    abr = t.neu(handel, "ram:ApplicableHeaderTradeSettlement")
    t.neu(abr, "ram:InvoiceCurrencyCode", "EUR")
    if firma.iban:
        zahlung = t.neu(abr, "ram:SpecifiedTradeSettlementPaymentMeans")
        t.neu(zahlung, "ram:TypeCode", "58")
        konto = t.neu(zahlung, "ram:PayeePartyCreditorFinancialAccount")
        t.neu(konto, "ram:IBANID", firma.iban.replace(" ", ""))
        if firma.kontoinhaber or firma.firmenname:
            t.neu(konto, "ram:AccountName", firma.kontoinhaber or firma.firmenname)
        if firma.bic:
            t.neu(t.neu(zahlung, "ram:PayeeSpecifiedCreditorFinancialInstitution"), "ram:BICID", firma.bic)

    for satz, gruppe in summen.gruppen.items():
        steuer = t.neu(abr, "ram:ApplicableTradeTax")
        t.neu(steuer, "ram:CalculatedAmount", _b(gruppe["steuer"]))
        t.neu(steuer, "ram:TypeCode", "VAT")
        if satz == 0:
            t.neu(steuer, "ram:ExemptionReason", grund if befreit else BEFREIUNGSGRUND_STANDARD)
        t.neu(steuer, "ram:BasisAmount", _b(gruppe["netto"]))
        t.neu(steuer, "ram:CategoryCode", "E" if satz == 0 else "S")
        t.neu(steuer, "ram:RateApplicablePercent", _b(satz))

    if rechnung.zeitraum_von and rechnung.zeitraum_bis:
        zeitraum = t.neu(abr, "ram:BillingSpecifiedPeriod")
        t.neu(t.neu(zeitraum, "ram:StartDateTime"), "udt:DateTimeString", _datum(rechnung.zeitraum_von), format="102")
        t.neu(t.neu(zeitraum, "ram:EndDateTime"), "udt:DateTimeString", _datum(rechnung.zeitraum_bis), format="102")

    if rechnung.faellig_am:
        bedingung = t.neu(abr, "ram:SpecifiedTradePaymentTerms")
        t.neu(bedingung, "ram:Description", f"Zahlbar bis {rechnung.faellig_am.strftime('%d.%m.%Y')}")
        t.neu(t.neu(bedingung, "ram:DueDateDateTime"), "udt:DateTimeString", _datum(rechnung.faellig_am), format="102")

    summe = t.neu(abr, "ram:SpecifiedTradeSettlementHeaderMonetarySummation")
    t.neu(summe, "ram:LineTotalAmount", _b(summen.netto))
    t.neu(summe, "ram:TaxBasisTotalAmount", _b(summen.netto))
    t.neu(summe, "ram:TaxTotalAmount", _b(summen.steuer), currencyID="EUR")
    t.neu(summe, "ram:GrandTotalAmount", _b(summen.brutto))
    t.neu(summe, "ram:DuePayableAmount", _b(summen.brutto))

    return etree.tostring(w, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def pruefen(xml: bytes) -> None:
    """Prüft das XML gegen das mitgelieferte Schema (wirft bei Fehlern eine Ausnahme)."""
    xml_check_xsd(xml, flavor="factur-x", level="en16931")


def in_pdf_einbetten(pdf: bytes, xml: bytes) -> bytes:
    """Bettet das XML als PDF/A-3-Anhang ein (Factur-X, Profil EN 16931)."""
    return generate_from_binary(pdf, xml, flavor="factur-x", level="en16931", check_xsd=True)
