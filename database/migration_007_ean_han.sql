-- Migration: Felder EAN (Barcode) und HAN (Herstellerartikelnummer) für Artikel
-- Einmalig auf dem Server ausführen:
--   mysql -u ww_user -p warenwirtschaft < database/migration_007_ean_han.sql

ALTER TABLE articles
    ADD COLUMN ean VARCHAR(20) DEFAULT NULL AFTER sku,
    ADD COLUMN han VARCHAR(50) DEFAULT NULL AFTER ean;
