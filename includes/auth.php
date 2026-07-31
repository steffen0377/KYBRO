<?php
require_once __DIR__ . '/db.php';

if (session_status() === PHP_SESSION_NONE) {
    session_start([
        'cookie_httponly' => true,
        'cookie_samesite' => 'Lax',
    ]);
}

function current_user(): ?array {
    return $_SESSION['user'] ?? null;
}

function require_login(): void {
    if (!current_user()) {
        header('Location: ' . APP_URL . '/login.php');
        exit;
    }
}

function require_admin(): void {
    require_login();
    if (current_user()['role'] !== 'admin') {
        http_response_code(403);
        die('Zugriff verweigert: Diese Funktion ist nur für Administratoren.');
    }
}

// Prüft Benutzername/Passwort ausschließlich gegen die lokale Datenbank.
function attempt_login_local(string $username, string $password): bool {
    $stmt = db()->prepare('SELECT * FROM users WHERE username = ? AND active = 1');
    $stmt->execute([$username]);
    $user = $stmt->fetch();
    if ($user && $user['password_hash'] && password_verify($password, $user['password_hash'])) {
        unset($user['password_hash']);
        $_SESSION['user'] = $user;
        return true;
    }
    return false;
}

// Prüft Benutzername/Passwort gegen den konfigurierten LDAP-Server. Bei
// erfolgreicher Anmeldung wird der lokale Benutzerdatensatz automatisch
// angelegt bzw. aktualisiert (auth_source='ldap'), damit Gruppen-/Rechte-
// Zuordnung weiterhin über die lokale users-Tabelle funktioniert.
// $unavailable wird auf true gesetzt, wenn die LDAP-Anmeldung nicht wegen
// falscher Zugangsdaten fehlschlägt, sondern weil der LDAP-Server bzw. der
// Service-Account nicht erreichbar/nutzbar ist. Damit kann attempt_login()
// zwischen "falsches Passwort" und "LDAP-Ausfall" unterscheiden.
function attempt_login_ldap(string $username, string $password, ?bool &$unavailable = null): bool {
    $unavailable = false;
    if (!extension_loaded('ldap')) {
        $unavailable = true;
        return false;
    }
    if ($password === '') {
        return false;
    }
    $cfg = ldap_settings();
    if (empty($cfg['host'])) {
        $unavailable = true;
        return false;
    }

    $protocol = $cfg['encryption'] === 'ldaps' ? 'ldaps://' : 'ldap://';
    $conn = @ldap_connect($protocol . $cfg['host'], (int)$cfg['port']);
    if (!$conn) {
        $unavailable = true;
        return false;
    }
    ldap_set_option($conn, LDAP_OPT_PROTOCOL_VERSION, 3);
    ldap_set_option($conn, LDAP_OPT_REFERRALS, 0);

    if ($cfg['encryption'] === 'starttls' && !@ldap_start_tls($conn)) {
        $unavailable = true;
        return false;
    }

    // Optionaler Bind mit Service-Account, um den DN des Benutzers zu suchen
    $bindDn = $cfg['bind_dn'] ?: null;
    $bindPw = $cfg['bind_password'] ?: null;
    if (!@ldap_bind($conn, $bindDn, $bindPw)) {
        $unavailable = true;
        return false;
    }

    $filter = str_replace('%s', ldap_escape($username, '', LDAP_ESCAPE_FILTER), $cfg['user_filter']);
    $search = @ldap_search($conn, $cfg['base_dn'], $filter, [$cfg['name_attribute'], $cfg['email_attribute']]);
    if (!$search) {
        $unavailable = true;
        return false;
    }
    $entries = ldap_get_entries($conn, $search);
    if ($entries['count'] !== 1) {
        return false;
    }
    $entry = $entries[0];
    $userDn = $entry['dn'];

    // Anmeldung des Benutzers selbst mit seinem Passwort prüfen
    if (!@ldap_bind($conn, $userDn, $password)) {
        return false;
    }

    $fullName = $entry[strtolower($cfg['name_attribute'])][0] ?? $username;

    // Lokalen Benutzerdatensatz anlegen/aktualisieren, damit Gruppen und
    // Berechtigungen weiter über die lokale users-Tabelle greifen.
    $pdo = db();
    $stmt = $pdo->prepare('SELECT * FROM users WHERE username = ?');
    $stmt->execute([$username]);
    $user = $stmt->fetch();
    if ($user) {
        if (!$user['active']) {
            return false;
        }
        $pdo->prepare("UPDATE users SET full_name = ?, auth_source = 'ldap' WHERE id = ?")->execute([$fullName, $user['id']]);
        $user['full_name'] = $fullName;
    } else {
        $pdo->prepare("INSERT INTO users (username, password_hash, full_name, role, auth_source) VALUES (?, '', ?, 'user', 'ldap')")
            ->execute([$username, $fullName]);
        $stmt = $pdo->prepare('SELECT * FROM users WHERE id = ?');
        $stmt->execute([$pdo->lastInsertId()]);
        $user = $stmt->fetch();
    }

    unset($user['password_hash']);
    $_SESSION['user'] = $user;
    return true;
}

// Notfall-Login ausschließlich für lokale Administrator-Konten, falls der
// LDAP-Server bei auth_mode='ldap' nicht erreichbar ist. Bewusst auf
// role='admin' beschränkt, damit dies keine generelle Hintertür für alle
// Benutzer öffnet, sondern nur sicherstellt, dass ein Administrator im
// Notfall noch Zugriff hat (z. B. um auf auth_mode='local' umzustellen).
function attempt_login_local_emergency(string $username, string $password): bool {
    $stmt = db()->prepare("SELECT * FROM users WHERE username = ? AND active = 1 AND role = 'admin'");
    $stmt->execute([$username]);
    $user = $stmt->fetch();
    if ($user && $user['password_hash'] && password_verify($password, $user['password_hash'])) {
        unset($user['password_hash']);
        $_SESSION['user'] = $user;
        return true;
    }
    return false;
}

// Protokolliert einen LDAP-Ausfall serverseitig, unabhängig davon, ob der
// Notfall-Login erfolgreich war. So bleibt ein LDAP-Ausfall nachvollziehbar,
// auch wenn der einzelne Benutzer die Flash-Warnung nicht meldet.
function log_ldap_unavailable(string $username, bool $emergencyLoginUsed): void {
    error_log(sprintf(
        '[LDAP] Server nicht erreichbar bei Login-Versuch von "%s". Notfall-Login (nur Admin): %s',
        $username,
        $emergencyLoginUsed ? 'erfolgreich verwendet' : 'nicht möglich/fehlgeschlagen'
    ));
}

// Prüft Benutzername/Passwort gemäß der konfigurierten Authentifizierungs-
// Reihenfolge (nur lokal, nur LDAP, oder eine Kombination mit Priorität).
function attempt_login(string $username, string $password): bool {
    $mode = auth_config()['auth_mode'] ?? 'local';
    switch ($mode) {
        case 'ldap':
            $unavailable = false;
            if (attempt_login_ldap($username, $password, $unavailable)) {
                return true;
            }
            if ($unavailable) {
                $emergencyOk = attempt_login_local_emergency($username, $password);
                log_ldap_unavailable($username, $emergencyOk);
                if ($emergencyOk) {
                    flash('warning', 'Achtung: Der LDAP-Server war nicht erreichbar. Sie wurden über das lokale Administrator-Konto als Notfall-Login angemeldet.');
                    return true;
                }
                // Damit login.php dem Benutzer statt "Zugangsdaten falsch"
                // die zutreffende Meldung "LDAP nicht erreichbar" anzeigen kann.
                $_SESSION['ldap_unavailable_hint'] = true;
            }
            return false;
        case 'ldap_then_local':
            return attempt_login_ldap($username, $password) || attempt_login_local($username, $password);
        case 'local_then_ldap':
            return attempt_login_local($username, $password) || attempt_login_ldap($username, $password);
        case 'local':
        default:
            return attempt_login_local($username, $password);
    }
}

function logout(): void {
    $_SESSION = [];
    session_destroy();
}

// CSRF-Schutz
function csrf_token(): string {
    if (empty($_SESSION['csrf_token'])) {
        $_SESSION['csrf_token'] = bin2hex(random_bytes(32));
    }
    return $_SESSION['csrf_token'];
}

function csrf_field(): string {
    return '<input type="hidden" name="csrf_token" value="' . htmlspecialchars(csrf_token()) . '">';
}

function csrf_check(): void {
    $token = $_POST['csrf_token'] ?? '';
    if (!hash_equals($_SESSION['csrf_token'] ?? '', $token)) {
        http_response_code(403);
        die('Ungültiges Sicherheits-Token. Bitte Seite neu laden und erneut versuchen.');
    }
}
