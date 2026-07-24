-- Migration: Logo für die Anwendung (wird in der linken Seitenleiste angezeigt)
-- Einmalig auf dem Server ausführen:
--   mysql -u ww_user -p warenwirtschaft < database/migration_005_logo.sql

ALTER TABLE company_settings
    ADD COLUMN logo_path VARCHAR(255) DEFAULT NULL AFTER company_name;
