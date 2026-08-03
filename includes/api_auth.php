<?php
require_once __DIR__ . '/db.php';
require_once __DIR__ . '/auth.php';
require_once __DIR__ . '/jwt.php';

/**
 * Prüft Benutzername/Passwort für die API, ohne eine dauerhafte
 * Web-Session zu hinterlassen. Nutzt bewusst dieselbe Prüf-Logik
 * (attempt_login) wie das Web-Login, inkl. LDAP-Unterstützung, damit
 * es nur eine Quelle der Wahrheit für "ist dieses Passwort korrekt" gibt.
 *
 * Gibt bei Erfolg das Benutzer-Array zurück (ohne password_hash), sonst null.
 */
function api_attempt_login(string $username, string $password): ?array {
    $loggedIn = attempt_login($username, $password);
    if (!$loggedIn) {
        // Session-Hinweise (z. B. ldap_unavailable_hint) wieder aufräumen,
        // damit sie nicht in einer späteren Web-Anfrage auftauchen.
        unset($_SESSION['ldap_unavailable_hint']);
        return null;
    }

    $user = current_user();

    // Die App ist stateless (Bearer-Token statt Cookie). Die durch
    // attempt_login() angelegte Session wird daher sofort wieder verworfen,
    // damit keine verwaisten Session-Dateien auf dem Server liegen bleiben.
    $_SESSION = [];
    if (session_status() === PHP_SESSION_ACTIVE) {
        session_destroy();
    }

    return $user;
}

/**
 * Liest den Bearer-Token aus dem Authorization-Header, prüft ihn und
 * gibt das Token-Payload zurück (enthält u. a. 'sub' = user id, 'role').
 * Beendet den Request mit 401, wenn kein gültiger Token vorhanden ist.
 */
function api_require_auth(): array {
    $header = $_SERVER['HTTP_AUTHORIZATION'] ?? '';
    if (!preg_match('/^Bearer\s+(.+)$/i', $header, $matches)) {
        api_json_error('Kein Authentifizierungs-Token übermittelt.', 401);
    }

    $payload = jwt_verify($matches[1]);
    if (!$payload) {
        api_json_error('Token ungültig oder abgelaufen.', 401);
    }

    return $payload;
}

/** Wie api_require_auth(), bricht aber zusätzlich ab, wenn role != admin. */
function api_require_admin(): array {
    $payload = api_require_auth();
    if (($payload['role'] ?? '') !== 'admin') {
        api_json_error('Zugriff verweigert: Nur für Administratoren.', 403);
    }
    return $payload;
}

/** Einheitliche Erfolgsantwort im vereinbarten JSON-Format. */
function api_json_success($data, int $statusCode = 200): void {
    http_response_code($statusCode);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(['success' => true, 'data' => $data], JSON_UNESCAPED_UNICODE);
    exit;
}

/** Einheitliche Fehlerantwort im vereinbarten JSON-Format; beendet den Request. */
function api_json_error(string $message, int $statusCode = 400): void {
    http_response_code($statusCode);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(['success' => false, 'error' => $message], JSON_UNESCAPED_UNICODE);
    exit;
}

/** Liest und dekodiert den JSON-Request-Body; bricht bei Syntaxfehlern ab. */
function api_read_json_body(): array {
    $raw = file_get_contents('php://input');
    if ($raw === '' || $raw === false) {
        return [];
    }
    $decoded = json_decode($raw, true);
    if (json_last_error() !== JSON_ERROR_NONE) {
        api_json_error('Ungültiges JSON im Request-Body.', 400);
    }
    return $decoded ?? [];
}
