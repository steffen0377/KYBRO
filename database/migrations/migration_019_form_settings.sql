-- Migration 019: Formulareinstellungen (Layout-Einstellungen für Angebote,
-- Aufträge und Rechnungen). Key-Value-Tabelle je Scope (global / angebot /
-- auftrag / rechnung), damit neue Einstellungen künftig ohne weitere
-- Migration ergänzt werden können. Fallback-Logik: scope -> global -> Default
-- in PHP (siehe includes/functions.php: get_form_setting()).

CREATE TABLE IF NOT EXISTS form_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    scope ENUM('global','angebot','auftrag','rechnung') NOT NULL,
    setting_key VARCHAR(64) NOT NULL,
    setting_value TEXT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_scope_key (scope, setting_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
