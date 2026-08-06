<?php
/**
 * Lizenzverwaltung
 * ------------------
 * Module der Anwendung (Warenwirtschaft, CRM, Ticketsystem, DMS, HR,
 * Statistik, ...) koennen ueber Lizenzen freigeschaltet werden. Eine
 * Lizenz gehoert zu einem Kunden/einer Installation, hat einen
 * Gueltigkeitszeitraum und ist einem oder mehreren Modulen zugeordnet
 * (Tabellen: modules, licenses, license_modules - siehe
 * database/migrations/migration_011_licensing.sql).
 */

define('LICENSE_CORE_MODULE', 'core');

function licensed_modules(): array {
    static $cache = null;
    if ($cache !== null) {
        return $cache;
    }
    $cache = [];
    $today = date('Y-m-d');
    $stmt = db()->prepare("
        SELECT DISTINCT m.code
        FROM modules m
        JOIN license_modules lm ON lm.module_id = m.id
        JOIN licenses l ON l.id = lm.license_id
        WHERE l.status = 'active'
          AND l.valid_from <= ?
          AND (l.valid_until IS NULL OR l.valid_until >= ?)
    ");
    $stmt->execute([$today, $today]);
    foreach ($stmt->fetchAll() as $row) {
        $cache[$row['code']] = true;
    }
    return $cache;
}

function has_module_license(string $moduleCode): bool {
    if ($moduleCode === LICENSE_CORE_MODULE) {
        return true;
    }
    return !empty(licensed_modules()[$moduleCode]);
}

function require_module_license(string $moduleCode): void {
    if (!has_module_license($moduleCode)) {
        http_response_code(402);
        $label = e(license_module_label($moduleCode));
        die("Zugriff verweigert: Fuer das Modul \"$label\" liegt keine gueltige Lizenz vor. Bitte wenden Sie sich an Ihren Administrator oder unter \"Einstellungen &gt; Lizenzen\".");
    }
}

function license_module_label(string $moduleCode): string {
    static $labels = null;
    if ($labels === null) {
        $labels = [];
        foreach (db()->query('SELECT code, name FROM modules') as $row) {
            $labels[$row['code']] = $row['name'];
        }
    }
    return $labels[$moduleCode] ?? $moduleCode;
}

function license_verify_signature(string $licenseKey, string $signature): bool {
    // TODO: Vorbereitet fuer eine spaetere kryptografisch signierte
    // Lizenzschluessel-Pruefung (aktuell ungenutzt).
    return false;
}
