<?php
/**
 * Minimale JWT-Implementierung (HS256) für die mobile API.
 *
 * Bewusst ohne externe Library gehalten, um keine zusätzliche Composer-
 * Abhängigkeit einzuführen. Deckt nur das ab, was die App braucht:
 * Erstellen und Prüfen eines signierten, zeitlich befristeten Tokens.
 */

// Geheimer Signierschlüssel. WICHTIG: In der Produktion über eine
// Umgebungsvariable oder eine nicht versionierte config lokal überschreiben,
// z. B. in config.local.php: define('JWT_SECRET', '...');
if (!defined('JWT_SECRET')) {
    define('JWT_SECRET', 'BITTE-IN-config.local.php-UEBERSCHREIBEN');
}

// Gültigkeitsdauer eines Tokens in Sekunden (Standard: 30 Tage, da die App
// offline arbeiten muss und nicht bei jedem Feldeinsatz neu einloggen soll).
if (!defined('JWT_TTL_SECONDS')) {
    define('JWT_TTL_SECONDS', 30 * 24 * 60 * 60);
}

function jwt_base64url_encode(string $data): string {
    return rtrim(strtr(base64_encode($data), '+/', '-_'), '=');
}

function jwt_base64url_decode(string $data): string {
    $padded = str_pad($data, strlen($data) % 4 === 0 ? strlen($data) : strlen($data) + (4 - strlen($data) % 4), '=');
    return base64_decode(strtr($padded, '-_', '+/'));
}

/**
 * Erstellt ein signiertes JWT für den übergebenen Benutzer.
 * $user muss mindestens 'id', 'username', 'role' enthalten.
 */
function jwt_create(array $user): string {
    $header = ['typ' => 'JWT', 'alg' => 'HS256'];
    $now = time();
    $payload = [
        'sub' => (int)$user['id'],
        'username' => $user['username'],
        'role' => $user['role'],
        'iat' => $now,
        'exp' => $now + JWT_TTL_SECONDS,
    ];

    $headerEncoded = jwt_base64url_encode(json_encode($header));
    $payloadEncoded = jwt_base64url_encode(json_encode($payload));
    $signature = hash_hmac('sha256', "$headerEncoded.$payloadEncoded", JWT_SECRET, true);
    $signatureEncoded = jwt_base64url_encode($signature);

    return "$headerEncoded.$payloadEncoded.$signatureEncoded";
}

/**
 * Prüft ein JWT und gibt bei Gültigkeit das Payload-Array zurück,
 * sonst null (abgelaufen, falsch signiert oder falsch aufgebaut).
 */
function jwt_verify(string $token): ?array {
    $parts = explode('.', $token);
    if (count($parts) !== 3) {
        return null;
    }
    [$headerEncoded, $payloadEncoded, $signatureEncoded] = $parts;

    $expectedSignature = jwt_base64url_encode(
        hash_hmac('sha256', "$headerEncoded.$payloadEncoded", JWT_SECRET, true)
    );
    if (!hash_equals($expectedSignature, $signatureEncoded)) {
        return null;
    }

    $payload = json_decode(jwt_base64url_decode($payloadEncoded), true);
    if (!is_array($payload) || !isset($payload['exp'])) {
        return null;
    }
    if ($payload['exp'] < time()) {
        return null;
    }

    return $payload;
}
