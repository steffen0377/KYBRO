-- Migration: Ansprechpartner und Bankverbindung je Kunde
-- Einmalig auf dem Server ausführen:
--   mysql -u ww_user -p warenwirtschaft < database/migration_010_kunden_ansprechpartner_bank.sql

ALTER TABLE customers
    ADD COLUMN iban VARCHAR(50) DEFAULT '' AFTER tax_id,
    ADD COLUMN bic VARCHAR(30) DEFAULT '' AFTER iban,
    ADD COLUMN bank_name VARCHAR(100) DEFAULT '' AFTER bic;

CREATE TABLE customer_contacts (
    id INT PRIMARY KEY AUTO_INCREMENT,
    customer_id INT NOT NULL,
    last_name VARCHAR(100) DEFAULT '',
    first_name VARCHAR(100) DEFAULT '',
    company VARCHAR(150) DEFAULT '',
    phone VARCHAR(50) DEFAULT '',
    email VARCHAR(150) DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
) ENGINE=InnoDB;
