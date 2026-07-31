-- =====================================================
-- Migration 011: E-Mail/SMTP-Einstellungen, LDAP, Authentifizierungs-
-- Reihenfolge, Gruppen und Modul-Berechtigungen
-- =====================================================

-- ---------------------------------------------------
-- SMTP / E-Mail-Einstellungen (Erweiterung company_settings)
-- ---------------------------------------------------
ALTER TABLE company_settings
    ADD COLUMN smtp_host VARCHAR(150) NOT NULL DEFAULT '' AFTER invoice_prefix,
    ADD COLUMN smtp_port INT NOT NULL DEFAULT 587 AFTER smtp_host,
    ADD COLUMN smtp_encryption ENUM('none','ssl','tls') NOT NULL DEFAULT 'tls' AFTER smtp_port,
    ADD COLUMN smtp_username VARCHAR(150) NOT NULL DEFAULT '' AFTER smtp_encryption,
    ADD COLUMN smtp_password VARCHAR(255) NOT NULL DEFAULT '' AFTER smtp_username,
    ADD COLUMN smtp_from_email VARCHAR(150) NOT NULL DEFAULT '' AFTER smtp_password,
    ADD COLUMN smtp_from_name VARCHAR(150) NOT NULL DEFAULT '' AFTER smtp_from_email;

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
-- Benutzer: Gruppen-Zuordnung und Authentifizierungsquelle
-- ---------------------------------------------------
ALTER TABLE users
    ADD COLUMN group_id INT DEFAULT NULL AFTER role,
    ADD COLUMN auth_source ENUM('local','ldap') NOT NULL DEFAULT 'local' AFTER group_id,
    ADD CONSTRAINT fk_users_group FOREIGN KEY (group_id) REFERENCES `groups`(id) ON DELETE SET NULL;

-- Bestehende Admin-Benutzer der neuen Administratoren-Gruppe zuordnen
UPDATE users SET group_id = 1 WHERE role = 'admin';
