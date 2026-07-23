-- Migration: Artikelnummer (SKU) wird verpflichtend, 5-stellig, automatisch vergeben
-- Einmalig auf dem Server ausführen:
--   mysql -u ww_user -p warenwirtschaft < database/migration_003_artikelnummer_pflicht.sql

-- Schritt 1: Bestehende Artikel ohne (oder mit leerer) Artikelnummer bekommen
-- automatisch eine 5-stellige Nummer basierend auf ihrer internen ID (z.B. 00001).
UPDATE articles SET sku = LPAD(id, 5, '0') WHERE sku IS NULL OR sku = '';

-- Schritt 2: Artikelnummer ist ab jetzt ein Pflichtfeld.
ALTER TABLE articles MODIFY COLUMN sku VARCHAR(20) NOT NULL;
