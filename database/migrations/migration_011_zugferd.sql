-- =====================================================
-- Migration 011: Felder für ZUGFeRD-Rechnungen
-- =====================================================

-- USt-IdNr. der eigenen Firma (separat von der Steuernummer `tax_id`)
ALTER TABLE company_settings
    ADD COLUMN vat_id VARCHAR(20) DEFAULT '' AFTER tax_id;

-- USt-IdNr. des Kunden (B2B, separat von `tax_id`)
ALTER TABLE customers
    ADD COLUMN vat_id VARCHAR(20) DEFAULT '' AFTER tax_id;

-- Leistungsdatum je Rechnung (falls abweichend vom Rechnungsdatum,
-- z.B. bei Rechnungsstellung nach Lieferung). Wenn NULL, wird beim
-- ZUGFeRD-Export das Rechnungsdatum als Leistungsdatum verwendet.
ALTER TABLE invoices
    ADD COLUMN service_date DATE DEFAULT NULL AFTER invoice_date;
