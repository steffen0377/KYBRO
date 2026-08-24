-- Migration 021: Kundenbezogene Sonderpreise für Artikel
-- Ein Artikel kann pro Kunde genau einen Sonderpreis hinterlegen,
-- entweder als Fixpreis (€, netto) oder als Rabatt in % auf den Standard-VK-Preis.

CREATE TABLE IF NOT EXISTS article_special_prices (
    id INT(11) NOT NULL AUTO_INCREMENT,
    article_id INT(11) NOT NULL,
    customer_id INT(11) NOT NULL,
    price_type ENUM('fixed','percent') NOT NULL DEFAULT 'fixed',
    price_value DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_article_customer (article_id, customer_id),
    KEY idx_customer (customer_id),
    CONSTRAINT fk_asp_article FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE CASCADE,
    CONSTRAINT fk_asp_customer FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
