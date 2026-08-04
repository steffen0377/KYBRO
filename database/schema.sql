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
    logo_path VARCHAR(255) DEFAULT NULL,
    street VARCHAR(150) DEFAULT '',
    zip VARCHAR(20) DEFAULT '',
    city VARCHAR(100) DEFAULT '',
    country VARCHAR(100) DEFAULT 'Deutschland',
    tax_id VARCHAR(50) DEFAULT '',
    vat_id VARCHAR(20) DEFAULT '',
    iban VARCHAR(50) DEFAULT '',
    bic VARCHAR(30) DEFAULT '',
    bank_name VARCHAR(100) DEFAULT '',
    email VARCHAR(150) DEFAULT '',
    phone VARCHAR(50) DEFAULT '',
    offer_prefix VARCHAR(20) NOT NULL DEFAULT 'ANG-',
    next_offer_number INT NOT NULL DEFAULT 1,
    order_prefix VARCHAR(20) NOT NULL DEFAULT 'AUF-',
    next_order_number INT NOT NULL DEFAULT 1,
    invoice_prefix VARCHAR(20) NOT NULL DEFAULT 'RE-',
    next_invoice_number INT NOT NULL DEFAULT 1,
    default_tax_rate DECIMAL(5,2) NOT NULL DEFAULT 19.00,
    smtp_host VARCHAR(150) NOT NULL DEFAULT '',
    smtp_port INT NOT NULL DEFAULT 587,
    smtp_encryption ENUM('none','ssl','tls') NOT NULL DEFAULT 'tls',
    smtp_username VARCHAR(150) NOT NULL DEFAULT '',
    smtp_password VARCHAR(255) NOT NULL DEFAULT '',
    smtp_from_email VARCHAR(150) NOT NULL DEFAULT '',
    smtp_from_name VARCHAR(150) NOT NULL DEFAULT ''
) ENGINE=InnoDB;

INSERT INTO company_settings (company_name) VALUES ('Meine Firma');

-- ---------------------------------------------------
-- LDAP-Einstellungen (Einzeldatensatz, wie company_settings)
-- ---------------------------------------------------
CREATE TABLE ldap_settings (
    id INT PRIMARY KEY AUTO_INCREMENT,
    host VARCHAR(150) NOT NULL DEFAULT '',
    port INT NOT NULL DEFAULT 389,
    encryption ENUM('none','starttls','ldaps') NOT NULL DEFAULT 'none',
    base_dn VARCHAR(255) NOT NULL DEFAULT '',
    bind_dn VARCHAR(255) NOT NULL DEFAULT '',
    bind_password VARCHAR(255) NOT NULL DEFAULT '',
    user_filter VARCHAR(255) NOT NULL DEFAULT '(uid=%s)',
    name_attribute VARCHAR(50) NOT NULL DEFAULT 'cn',
    email_attribute VARCHAR(50) NOT NULL DEFAULT 'mail'
) ENGINE=InnoDB;

INSERT INTO ldap_settings (id) VALUES (1);

-- ---------------------------------------------------
-- Authentifizierungs-Reihenfolge (Einzeldatensatz)
-- local             = nur lokale Datenbank
-- ldap              = nur LDAP
-- ldap_then_local   = zuerst LDAP, dann lokale DB
-- local_then_ldap   = zuerst lokale DB, dann LDAP
-- ---------------------------------------------------
CREATE TABLE auth_config (
    id INT PRIMARY KEY AUTO_INCREMENT,
    auth_mode ENUM('local','ldap','ldap_then_local','local_then_ldap') NOT NULL DEFAULT 'local'
) ENGINE=InnoDB;

INSERT INTO auth_config (id, auth_mode) VALUES (1, 'local');

-- ---------------------------------------------------
-- Gruppen (steuern Zugriffsberechtigungen auf Module)
-- ---------------------------------------------------
CREATE TABLE `groups` (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL UNIQUE,
    description VARCHAR(255) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

INSERT INTO `groups` (name, description) VALUES ('Administratoren', 'Voller Zugriff auf alle Module');

-- ---------------------------------------------------
-- Benutzer
-- ---------------------------------------------------
CREATE TABLE users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    role ENUM('admin','user') NOT NULL DEFAULT 'user',
    group_id INT DEFAULT NULL,
    auth_source ENUM('local','ldap') NOT NULL DEFAULT 'local',
    active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (group_id) REFERENCES `groups`(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- Hinweis: Der erste Admin-Benutzer wird NICHT hier per SQL angelegt,
-- sondern einmalig über setup_admin.php erstellt (siehe README.md).
-- Das stellt sicher, dass das Passwort korrekt und sicher gehasht wird.

-- ---------------------------------------------------
-- Modul-Berechtigungen je Gruppe (lesen/schreiben getrennt)
-- ---------------------------------------------------
CREATE TABLE group_permissions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    group_id INT NOT NULL,
    module VARCHAR(50) NOT NULL,
    can_read TINYINT(1) NOT NULL DEFAULT 0,
    can_write TINYINT(1) NOT NULL DEFAULT 0,
    UNIQUE KEY uniq_group_module (group_id, module),
    FOREIGN KEY (group_id) REFERENCES `groups`(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Administratoren-Gruppe erhält von Anfang an vollen Zugriff auf alle
-- bekannten Module. Die Modul-Liste entspricht den bestehenden Menüpunkten.
INSERT INTO group_permissions (group_id, module, can_read, can_write)
SELECT 1, m.module, 1, 1 FROM (
    SELECT 'artikel' AS module
    UNION SELECT 'lager'
    UNION SELECT 'kunden'
    UNION SELECT 'lieferanten'
    UNION SELECT 'angebote'
    UNION SELECT 'rechnungen'
    UNION SELECT 'kategorien'
    UNION SELECT 'einstellungen'
) m;

-- ---------------------------------------------------
-- Rate-Limiting für api/auth.php
-- ---------------------------------------------------
CREATE TABLE api_login_attempts (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) NOT NULL,
    ip_address VARCHAR(45) NOT NULL,
    success TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_lookup (username, ip_address, created_at)
) ENGINE=InnoDB;

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
    vat_id VARCHAR(20) DEFAULT '',
    iban VARCHAR(50) DEFAULT '',
    bic VARCHAR(30) DEFAULT '',
    bank_name VARCHAR(100) DEFAULT '',
    notes TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ---------------------------------------------------
-- Ansprechpartner (mehrere pro Kunde möglich)
-- ---------------------------------------------------
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

-- ---------------------------------------------------
-- Lieferanten
-- ---------------------------------------------------
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

-- ---------------------------------------------------
-- Artikel
-- ---------------------------------------------------
CREATE TABLE articles (
    id INT PRIMARY KEY AUTO_INCREMENT,
    sku VARCHAR(20) NOT NULL UNIQUE,
    ean VARCHAR(20) DEFAULT NULL,
    han VARCHAR(50) DEFAULT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    unit VARCHAR(20) NOT NULL DEFAULT 'Stk.',
    purchase_price DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    sale_price DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    tax_rate DECIMAL(5,2) NOT NULL DEFAULT 19.00,
    stock_qty DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    min_stock DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    track_stock TINYINT(1) NOT NULL DEFAULT 1,
    track_serials TINYINT(1) NOT NULL DEFAULT 0,
    active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ---------------------------------------------------
-- Lieferanten-Zuordnung je Artikel (mehrere Lieferanten möglich,
-- jeweils mit Lieferanten-Artikelnummer und unserem HEK)
-- ---------------------------------------------------
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

-- ---------------------------------------------------
-- Kategorien (mehrere pro Artikel möglich)
-- ---------------------------------------------------
CREATE TABLE categories (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL UNIQUE,
    parent_id INT DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_id) REFERENCES categories(id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE article_categories (
    article_id INT NOT NULL,
    category_id INT NOT NULL,
    PRIMARY KEY (article_id, category_id),
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
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
-- Aufträge (Prozesskette Angebot -> Auftrag -> Rechnung)
-- client_uuid dient der Offline-App: sie vergibt die UUID selbst beim
-- Anlegen, damit wiederholte Sync-Versuche (z.B. nach Verbindungsabbruch)
-- keine doppelten Datensätze erzeugen.
-- ---------------------------------------------------
CREATE TABLE orders (
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

CREATE TABLE order_items (
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

-- ---------------------------------------------------
-- Rechnungen
-- ---------------------------------------------------
CREATE TABLE invoices (
    id INT PRIMARY KEY AUTO_INCREMENT,
    invoice_number VARCHAR(30) NOT NULL UNIQUE,
    offer_id INT DEFAULT NULL,
    order_id INT DEFAULT NULL,
    customer_id INT NOT NULL,
    invoice_date DATE NOT NULL,
    service_date DATE DEFAULT NULL,
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
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL,
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

-- ---------------------------------------------------
-- Seriennummern (optional, pro Artikel aktivierbar)
-- ---------------------------------------------------
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
