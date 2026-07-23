-- =====================================================
-- Warenwirtschaft - Datenbankschema für MariaDB
-- =====================================================

CREATE DATABASE IF NOT EXISTS warenwirtschaft
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE warenwirtschaft;

-- ---------------------------------------------------
-- Firmeneinstellungen (für Angebote/Rechnungen-Kopf)
-- ---------------------------------------------------
CREATE TABLE company_settings (
    id INT PRIMARY KEY AUTO_INCREMENT,
    company_name VARCHAR(150) NOT NULL DEFAULT '',
    street VARCHAR(150) DEFAULT '',
    zip VARCHAR(20) DEFAULT '',
    city VARCHAR(100) DEFAULT '',
    country VARCHAR(100) DEFAULT 'Deutschland',
    tax_id VARCHAR(50) DEFAULT '',
    iban VARCHAR(50) DEFAULT '',
    bic VARCHAR(30) DEFAULT '',
    bank_name VARCHAR(100) DEFAULT '',
    email VARCHAR(150) DEFAULT '',
    phone VARCHAR(50) DEFAULT '',
    offer_prefix VARCHAR(20) NOT NULL DEFAULT 'ANG-',
    next_offer_number INT NOT NULL DEFAULT 1,
    invoice_prefix VARCHAR(20) NOT NULL DEFAULT 'RE-',
    next_invoice_number INT NOT NULL DEFAULT 1,
    default_tax_rate DECIMAL(5,2) NOT NULL DEFAULT 19.00
) ENGINE=InnoDB;

INSERT INTO company_settings (company_name) VALUES ('Meine Firma');

-- ---------------------------------------------------
-- Benutzer
-- ---------------------------------------------------
CREATE TABLE users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    role ENUM('admin','user') NOT NULL DEFAULT 'user',
    active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Hinweis: Der erste Admin-Benutzer wird NICHT hier per SQL angelegt,
-- sondern einmalig über setup_admin.php erstellt (siehe README.md).
-- Das stellt sicher, dass das Passwort korrekt und sicher gehasht wird.

-- ---------------------------------------------------
-- Kunden
-- ---------------------------------------------------
CREATE TABLE customers (
    id INT PRIMARY KEY AUTO_INCREMENT,
    customer_number VARCHAR(20) UNIQUE,
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
    notes TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ---------------------------------------------------
-- Artikel
-- ---------------------------------------------------
CREATE TABLE articles (
    id INT PRIMARY KEY AUTO_INCREMENT,
    sku VARCHAR(50) UNIQUE,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    unit VARCHAR(20) NOT NULL DEFAULT 'Stk.',
    purchase_price DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    sale_price DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    tax_rate DECIMAL(5,2) NOT NULL DEFAULT 19.00,
    stock_qty DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    min_stock DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    track_stock TINYINT(1) NOT NULL DEFAULT 1,
    active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ---------------------------------------------------
-- Lagerbewegungen (Historie jeder Bestandsänderung)
-- ---------------------------------------------------
CREATE TABLE stock_movements (
    id INT PRIMARY KEY AUTO_INCREMENT,
    article_id INT NOT NULL,
    type ENUM('einlagerung','auslagerung','korrektur','verkauf') NOT NULL,
    quantity DECIMAL(10,2) NOT NULL,
    reference_type VARCHAR(30) DEFAULT NULL,
    reference_id INT DEFAULT NULL,
    note VARCHAR(255) DEFAULT '',
    created_by INT DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- ---------------------------------------------------
-- Angebote
-- ---------------------------------------------------
CREATE TABLE offers (
    id INT PRIMARY KEY AUTO_INCREMENT,
    offer_number VARCHAR(30) NOT NULL UNIQUE,
    customer_id INT NOT NULL,
    offer_date DATE NOT NULL,
    valid_until DATE DEFAULT NULL,
    status ENUM('entwurf','versendet','angenommen','abgelehnt') NOT NULL DEFAULT 'entwurf',
    notes TEXT,
    total_net DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    total_tax DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    total_gross DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    created_by INT DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE offer_items (
    id INT PRIMARY KEY AUTO_INCREMENT,
    offer_id INT NOT NULL,
    article_id INT DEFAULT NULL,
    position INT NOT NULL DEFAULT 0,
    description VARCHAR(255) NOT NULL,
    quantity DECIMAL(10,2) NOT NULL DEFAULT 1.00,
    unit_price DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    tax_rate DECIMAL(5,2) NOT NULL DEFAULT 19.00,
    FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE CASCADE,
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- ---------------------------------------------------
-- Rechnungen
-- ---------------------------------------------------
CREATE TABLE invoices (
    id INT PRIMARY KEY AUTO_INCREMENT,
    invoice_number VARCHAR(30) NOT NULL UNIQUE,
    offer_id INT DEFAULT NULL,
    customer_id INT NOT NULL,
    invoice_date DATE NOT NULL,
    due_date DATE DEFAULT NULL,
    status ENUM('entwurf','versendet','bezahlt','ueberfaellig','storniert') NOT NULL DEFAULT 'entwurf',
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

CREATE TABLE invoice_items (
    id INT PRIMARY KEY AUTO_INCREMENT,
    invoice_id INT NOT NULL,
    article_id INT DEFAULT NULL,
    position INT NOT NULL DEFAULT 0,
    description VARCHAR(255) NOT NULL,
    quantity DECIMAL(10,2) NOT NULL DEFAULT 1.00,
    unit_price DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    tax_rate DECIMAL(5,2) NOT NULL DEFAULT 19.00,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE SET NULL
) ENGINE=InnoDB;
