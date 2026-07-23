-- Migration: Seriennummern-Erfassung für Lagerartikel
-- Einmalig auf dem Server ausführen:
--   mysql -u ww_user -p warenwirtschaft < database/migration_002_serial_numbers.sql

ALTER TABLE articles
    ADD COLUMN track_serials TINYINT(1) NOT NULL DEFAULT 0 AFTER track_stock;

CREATE TABLE article_serials (
    id INT PRIMARY KEY AUTO_INCREMENT,
    article_id INT NOT NULL,
    serial_number VARCHAR(100) NOT NULL,
    status ENUM('lager','verkauft','defekt') NOT NULL DEFAULT 'lager',
    invoice_id INT DEFAULT NULL,
    note VARCHAR(255) DEFAULT '',
    sold_at DATETIME DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_article_serial (article_id, serial_number),
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE SET NULL
) ENGINE=InnoDB;
