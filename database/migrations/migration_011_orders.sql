-- Migration 011: Aufträge-Modul (Angebot -> Auftrag -> Rechnung)
-- Fügt orders/order_items hinzu und verknüpft invoices optional mit einem Auftrag.
-- client_uuid dient der Offline-App: sie vergibt die UUID selbst beim Anlegen,
-- damit wiederholte Sync-Versuche (z. B. nach Verbindungsabbruch) keine
-- doppelten Datensätze erzeugen.

CREATE TABLE IF NOT EXISTS orders (
    id INT PRIMARY KEY AUTO_INCREMENT,
    order_number VARCHAR(30) NOT NULL UNIQUE,
    offer_id INT DEFAULT NULL,
    customer_id INT NOT NULL,
    order_date DATE NOT NULL,
    status ENUM('offen','in_bearbeitung','unterschrieben','abgeschlossen','storniert') NOT NULL DEFAULT 'offen',
    notes TEXT,
    signature_path VARCHAR(255) DEFAULT NULL,
    signed_at DATETIME DEFAULT NULL,
    signed_by_name VARCHAR(150) DEFAULT NULL,
    client_uuid VARCHAR(36) DEFAULT NULL UNIQUE,
    total_net DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    total_tax DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    total_gross DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    created_by INT DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE SET NULL,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS order_items (
    id INT PRIMARY KEY AUTO_INCREMENT,
    order_id INT NOT NULL,
    article_id INT DEFAULT NULL,
    position INT NOT NULL DEFAULT 0,
    description VARCHAR(255) NOT NULL,
    quantity DECIMAL(10,2) NOT NULL DEFAULT 1.00,
    unit_price DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    tax_rate DECIMAL(5,2) NOT NULL DEFAULT 19.00,
    client_uuid VARCHAR(36) DEFAULT NULL UNIQUE,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- Rechnungen sollen künftig auch direkt aus einem Auftrag entstehen können,
-- ohne den bisherigen Weg über offer_id zu brechen.
ALTER TABLE invoices
    ADD COLUMN order_id INT DEFAULT NULL AFTER offer_id,
    ADD CONSTRAINT fk_invoices_order FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL;

-- Nummernkreis für Aufträge, analog zu Angeboten/Rechnungen.
ALTER TABLE company_settings
    ADD COLUMN order_prefix VARCHAR(20) NOT NULL DEFAULT 'AUF-' AFTER offer_prefix,
    ADD COLUMN next_order_number INT NOT NULL DEFAULT 1 AFTER next_offer_number;
