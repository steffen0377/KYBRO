<?php
/**
 * Einfaches Rate-Limiting für den API-Login, um Brute-Force-Angriffe auf
 * api/auth.php zu erschweren. Bewusst DB-basiert (keine zusätzliche
 * Infrastruktur wie Redis nötig) - für das erwartete Nutzungsvolumen einer
 * internen Wawi-API ausreichend.
 *
 * Sperrt nach zu vielen Fehlversuchen die Kombination aus Benutzername UND
 * IP-Adresse für eine Weile. Bewusst nicht global pro Benutzername, damit
 * ein Angreifer nicht einfach durch massenhafte Fehlversuche einen echten
 * Benutzer aussperren kann (Denial of Service gegen den Account).
 */
require_once __DIR__ . '/db.php';

const RATE_LIMIT_MAX_ATTEMPTS = 5;
const RATE_LIMIT_WINDOW_MINUTES = 15;

function rate_limit_check(string $username, string $ip): void {
    $pdo = db();
    $stmt = $pdo->prepare('
        SELECT COUNT(*) FROM api_login_attempts
        WHERE username = ? AND ip_address = ? AND success = 0
          AND created_at > DATE_SUB(NOW(), INTERVAL ? MINUTE)
    ');
    $stmt->execute([$username, $ip, RATE_LIMIT_WINDOW_MINUTES]);
    $failedAttempts = (int)$stmt->fetchColumn();

    if ($failedAttempts >= RATE_LIMIT_MAX_ATTEMPTS) {
        api_json_error(
            'Zu viele Fehlversuche. Bitte in ' . RATE_LIMIT_WINDOW_MINUTES . ' Minuten erneut versuchen.',
            429
        );
    }
}

function rate_limit_record(string $username, string $ip, bool $success): void {
    $pdo = db();
    $pdo->prepare('INSERT INTO api_login_attempts (username, ip_address, success) VALUES (?, ?, ?)')
        ->execute([$username, $ip, $success ? 1 : 0]);

    // Alte Einträge aufräumen, damit die Tabelle nicht unbegrenzt wächst.
    // Läuft beiläufig bei jedem Login-Versuch mit statt per Cronjob, da das
    // Datenvolumen für eine interne API gering bleibt.
    $pdo->prepare('DELETE FROM api_login_attempts WHERE created_at < DATE_SUB(NOW(), INTERVAL 1 DAY)')->execute();
}

function client_ip(): string {
    return $_SERVER['REMOTE_ADDR'] ?? 'unknown';
}
