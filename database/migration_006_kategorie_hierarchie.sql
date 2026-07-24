-- Migration: Kategorien können Unterkategorien haben (Baumstruktur)
-- Einmalig auf dem Server ausführen:
--   mysql -u ww_user -p warenwirtschaft < database/migration_006_kategorie_hierarchie.sql

ALTER TABLE categories
    ADD COLUMN parent_id INT DEFAULT NULL AFTER name,
    ADD FOREIGN KEY (parent_id) REFERENCES categories(id) ON DELETE SET NULL;
