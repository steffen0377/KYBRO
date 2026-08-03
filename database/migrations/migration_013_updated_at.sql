-- Migration 013: updated_at für Kunden und Artikel
-- Ohne updated_at kann die App bei einem Delta-Sync (?since=...) echte
-- Änderungen (z. B. neue Adresse, neuer Preis) nicht von unveränderten
-- Datensätzen unterscheiden - nur Neuanlagen wären über created_at sichtbar.

ALTER TABLE customers
    ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER created_at;

ALTER TABLE articles
    ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER created_at;

-- Bestehende Datensätze initial auf created_at setzen, damit ein erster
-- Sync nicht fälschlich "gerade eben geändert" meldet.
UPDATE customers SET updated_at = created_at;
UPDATE articles SET updated_at = created_at;
