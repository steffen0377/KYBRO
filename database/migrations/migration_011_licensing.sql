-- =====================================================
-- Migration 011: Lizenzverwaltung
-- =====================================================

CREATE TABLE modules (
    id INT PRIMARY KEY AUTO_INCREMENT,
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(255) NOT NULL DEFAULT '',
    active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

INSERT INTO modules (code, name, description) VALUES
    ('warenwirtschaft', 'Warenwirtschaft', 'Angebote, Aufträge und Rechnungen'),
    ('crm', 'CRM', 'Erweiterte Ansprechpartner-Verwaltung bei Kunden und Lieferanten'),
    ('ticketsystem', 'Ticketsystem', 'Support- und Aufgabenverwaltung'),
    ('dms', 'DMS', 'Dokumentenmanagement'),
    ('hr', 'HR', 'Personalverwaltung'),
    ('statistik', 'Statistik', 'Auswertungen und Reports');

CREATE TABLE licenses (
    id INT PRIMARY KEY AUTO_INCREMENT,
    license_key VARCHAR(255) DEFAULT NULL,
    customer_reference VARCHAR(150) NOT NULL,
    issued_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_from DATE NOT NULL,
    valid_until DATE DEFAULT NULL,
    status ENUM('active','expired','revoked') NOT NULL DEFAULT 'active',
    signature VARCHAR(512) DEFAULT NULL,
    created_by INT DEFAULT NULL,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE license_modules (
    license_id INT NOT NULL,
    module_id INT NOT NULL,
    PRIMARY KEY (license_id, module_id),
    FOREIGN KEY (license_id) REFERENCES licenses(id) ON DELETE CASCADE,
    FOREIGN KEY (module_id) REFERENCES modules(id) ON DELETE CASCADE
) ENGINE=InnoDB;
