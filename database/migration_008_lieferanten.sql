-- Migration: Lieferantenverwaltung
-- Einmalig auf dem Server ausführen:
--   mysql -u ww_user -p warenwirtschaft < database/migration_008_lieferanten.sql

CREATE TABLE suppliers (
    id INT PRIMARY KEY AUTO_INCREMENT,
    supplier_number VARCHAR(20) UNIQUE,
    company VARCHAR(150) DEFAULT '',
    first_name VARCHAR(100) DEFAULT '',
    last_name VARCHAR(100) DEFAULT '',
    street VARCHAR(150) DEFAULT '',
    zip VARCHAR(20) DEFAULT '',
    city VARCHAR(100) DEFAULT '',
    country VARCHAR(100) DEFAULT 'Deutschland',
    email VARCHAR(150) DEFAULT '',
    phone VARCHAR(50) DEFAULT '',
    tax_id VARCHAR(50) DEFAULT '',
    customer_number_at_supplier VARCHAR(50) DEFAULT '',
    notes TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
