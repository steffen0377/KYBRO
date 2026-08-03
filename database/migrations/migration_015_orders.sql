-- =====================================================
-- Migration 015: Aufträge (Prozesskette Angebot -> Auftrag -> Rechnung)
-- =====================================================

ALTER TABLE company_settings
    ADD COLUMN order_prefix VARCHAR(20) NOT NULL DEFAULT 'AUF-' AFTER offer_prefix,
    ADD COLUMN next_order_number INT NOT NULL DEFAULT 1 AFTER order_prefix;

CREATE TABLE orders (
    id INT PRIMARY KEY AUTO_INCREMENT,
    order_number VARCHAR(30) NOT NULL UNIQUE,
    offer_id INT DEFAULT NULL,
    customer_id INT NOT NULL,
    order_date DATE NOT NULL,
    status ENUM('offen','in_bearbeitung','abgeschlossen','storniert') NOT NULL DEFAULT 'offen',
    notes TEXT,
    total_net DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    total_tax DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    total_gross DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    created_by INT DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE SET NULL,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE order_items (
    id INT PRIMARY KEY AUTO_INCREMENT,
    order_id INT NOT NULL,
    article_id INT DEFAULT NULL,
    position INT NOT NULL DEFAULT 0,
    description VARCHAR(255) NOT NULL,
    quantity DECIMAL(10,2) NOT NULL DEFAULT 1.00,
    unit_price DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    tax_rate DECIMAL(5,2) NOT NULL DEFAULT 19.00,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- Rechnungen wissen künftig auch, aus welchem Auftrag sie entstanden sind
-- (zusätzlich zu offer_id, das weiterhin die ursprüngliche Angebots-Referenz bleibt).
ALTER TABLE invoices
    ADD COLUMN order_id INT DEFAULT NULL AFTER offer_id,
    ADD FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL;
