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
function attempt_login_ldap(string $username, string $password): bool {
    if (!extension_loaded('ldap') || $password === '') {
        return false;
    }
    $cfg = ldap_settings();
    if (empty($cfg['host'])) {
        return false;
    }

    $protocol = $cfg['encryption'] === 'ldaps' ? 'ldaps://' : 'ldap://';
    $conn = @ldap_connect($protocol . $cfg['host'], (int)$cfg['port']);
    if (!$conn) {
        return false;
    }
    ldap_set_option($conn, LDAP_OPT_PROTOCOL_VERSION, 3);
    ldap_set_option($conn, LDAP_OPT_REFERRALS, 0);

    if ($cfg['encryption'] === 'starttls' && !@ldap_start_tls($conn)) {
        return false;
    }

    // Optionaler Bind mit Service-Account, um den DN des Benutzers zu suchen
    $bindDn = $cfg['bind_dn'] ?: null;
    $bindPw = $cfg['bind_password'] ?: null;
    if (!@ldap_bind($conn, $bindDn, $bindPw)) {
        return false;
    }

    $filter = str_replace('%s', ldap_escape($username, '', LDAP_ESCAPE_FILTER), $cfg['user_filter']);
    $search = @ldap_search($conn, $cfg['base_dn'], $filter, [$cfg['name_attribute'], $cfg['email_attribute']]);
    if (!$search) {
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

// Prüft Benutzername/Passwort gemäß der konfigurierten Authentifizierungs-
// Reihenfolge (nur lokal, nur LDAP, oder eine Kombination mit Priorität).
function attempt_login(string $username, string $password): bool {
    $mode = auth_config()['auth_mode'] ?? 'local';
    switch ($mode) {
        case 'ldap':
            return attempt_login_ldap($username, $password);
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
