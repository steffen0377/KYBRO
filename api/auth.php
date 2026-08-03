<?php
/**
 * POST /api/auth.php
 * Body: { "username": "...", "password": "..." }
 * Antwort bei Erfolg: { "success": true, "data": { "token": "...", "user": {...} } }
 *
 * Nutzt dieselbe Login-Logik wie das Web-Login (inkl. LDAP), siehe
 * includes/api_auth.php::api_attempt_login().
 */
require_once __DIR__ . '/../includes/api_auth.php';
require_once __DIR__ . '/../includes/rate_limit.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    api_json_error('Nur POST erlaubt.', 405);
}

$body = api_read_json_body();
$username = trim($body['username'] ?? '');
$password = $body['password'] ?? '';

if ($username === '' || $password === '') {
    api_json_error('Benutzername und Passwort erforderlich.', 400);
}

$ip = client_ip();
rate_limit_check($username, $ip);

$user = api_attempt_login($username, $password);
rate_limit_record($username, $ip, (bool)$user);

if (!$user) {
    api_json_error('Benutzername oder Passwort ist falsch.', 401);
}

$token = jwt_create($user);

api_json_success([
    'token' => $token,
    'expires_in' => JWT_TTL_SECONDS,
    'user' => [
        'id' => $user['id'],
        'username' => $user['username'],
        'full_name' => $user['full_name'],
        'role' => $user['role'],
    ],
]);
