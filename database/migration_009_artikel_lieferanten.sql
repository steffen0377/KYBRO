-- Migration: Lieferanten-Zuordnung bei Artikeln (Lieferanten-Artikelnummer, HEK)
-- Einmalig auf dem Server ausführen:
--   mysql -u ww_user -p warenwirtschaft < database/migration_009_artikel_lieferanten.sql

CREATE TABLE article_suppliers (
    id INT PRIMARY KEY AUTO_INCREMENT,
    article_id INT NOT NULL,
    supplier_id INT NOT NULL,
    supplier_article_number VARCHAR(50) DEFAULT '',
    hek_price DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    UNIQUE KEY uniq_article_supplier (article_id, supplier_id),
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE CASCADE
) ENGINE=InnoDB;
