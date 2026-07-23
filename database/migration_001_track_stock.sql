-- Migration: Fügt die Möglichkeit hinzu, Artikel OHNE Lagerbestandsführung anzulegen
-- (z.B. für Dienstleistungen). Einmalig auf dem Server ausführen:
--   mysql -u ww_user -p warenwirtschaft < database/migration_001_track_stock.sql

ALTER TABLE articles
    ADD COLUMN track_stock TINYINT(1) NOT NULL DEFAULT 1 AFTER min_stock;
