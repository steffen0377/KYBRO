-- Migration 022: Befreiungsgrund für steuerbefreite Kunden (ZUGFeRD BR-S-05)
--
-- Hintergrund: ZUGFeRD verlangt bei Steuerkategorie "S" (Standard) zwingend
-- einen Steuersatz > 0 (BR-S-05). Kunden mit 0% MwSt. wegen echter
-- Steuerbefreiung (z.B. §4 Nr. 21a UStG) müssen stattdessen mit Kategorie
-- "E" (Exempt from tax) und einem Befreiungsgrund-Text ausgezeichnet werden.
--
-- Dieses Feld ergänzt den bereits vorhandenen Haken "tax_exempt" in
-- customers um den dazugehörigen Freitext für BT-120.

ALTER TABLE `customers`
    ADD COLUMN `tax_exemption_reason` VARCHAR(255) NULL DEFAULT NULL
    AFTER `tax_exempt`;

-- Bereits vorhandene steuerbefreite Kunden ohne Grund mit dem bisher
-- einzig genutzten Standardgrund vorbelegen. Bei Bedarf danach im
-- Kundenstamm individuell anpassen (z.B. Reverse Charge, Export etc.).
UPDATE `customers`
SET `tax_exemption_reason` = 'Steuerfrei gemäß §4 Nr. 21a UStG'
WHERE `tax_exempt` = 1
  AND (`tax_exemption_reason` IS NULL OR `tax_exemption_reason` = '');
