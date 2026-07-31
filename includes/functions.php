<?php

function e(?string $str): string {
    return htmlspecialchars($str ?? '', ENT_QUOTES, 'UTF-8');
}

function money(float $val): string {
    return number_format($val, 2, ',', '.') . ' €';
}

function num(float $val): string {
    return number_format($val, 2, ',', '.');
}

function flash(string $type, string $message): void {
    $_SESSION['flash'][] = ['type' => $type, 'message' => $message];
}

function get_flashes(): array {
    $f = $_SESSION['flash'] ?? [];
    unset($_SESSION['flash']);
    return $f;
}

function redirect(string $path): void {
    header('Location: ' . APP_URL . '/' . ltrim($path, '/'));
    exit;
}

// Nächste Angebots-/Rechnungsnummer holen und Zähler erhöhen.
// WICHTIG: Diese Funktion wird immer innerhalb einer bereits laufenden
// Transaktion der aufrufenden Seite (angebote.php/rechnungen.php) aufgerufen
// und startet daher selbst KEINE eigene Transaktion (PDO unterstützt keine
// verschachtelten Transaktionen).
function next_document_number(string $type): string {
    $pdo = db();
    $field = $type === 'offer' ? 'next_offer_number' : 'next_invoice_number';
    $prefixField = $type === 'offer' ? 'offer_prefix' : 'invoice_prefix';
    $stmt = $pdo->query("SELECT $field, $prefixField FROM company_settings WHERE id = 1 FOR UPDATE");
    $row = $stmt->fetch();
    $number = $row[$field];
    $prefix = $row[$prefixField];
    $pdo->prepare("UPDATE company_settings SET $field = $field + 1 WHERE id = 1")->execute();
    return $prefix . date('Y') . '-' . str_pad((string)$number, 4, '0', STR_PAD_LEFT);
}

// Bestand eines Artikels ändern und Bewegung protokollieren.
// Artikel ohne Lagerbestandsführung (track_stock=0) werden dabei übersprungen,
// z.B. Dienstleistungen.
function adjust_stock(int $articleId, float $delta, string $type, ?string $refType = null, ?int $refId = null, string $note = ''): void {
    $pdo = db();
    $stmt = $pdo->prepare('SELECT track_stock FROM articles WHERE id = ?');
    $stmt->execute([$articleId]);
    $article = $stmt->fetch();
    if (!$article || !$article['track_stock']) {
        return;
    }

    $stmt = $pdo->prepare('UPDATE articles SET stock_qty = stock_qty + ? WHERE id = ?');
    $stmt->execute([$delta, $articleId]);

    $stmt = $pdo->prepare('INSERT INTO stock_movements (article_id, type, quantity, reference_type, reference_id, note, created_by) VALUES (?,?,?,?,?,?,?)');
    $stmt->execute([$articleId, $type, $delta, $refType, $refId, $note, current_user()['id'] ?? null]);
}

// Kategorie-Zuordnungen eines Artikels ersetzen (Mehrfachzuordnung möglich)
function save_article_categories(PDO $pdo, int $articleId, array $categoryIds): void {
    $categoryIds = array_values(array_unique(array_filter(array_map('intval', $categoryIds))));
    $pdo->prepare('DELETE FROM article_categories WHERE article_id=?')->execute([$articleId]);
    if ($categoryIds) {
        $stmt = $pdo->prepare('INSERT INTO article_categories (article_id, category_id) VALUES (?,?)');
        foreach ($categoryIds as $catId) {
            $stmt->execute([$articleId, $catId]);
        }
    }
}

// Lieferanten-Zuordnungen eines Artikels ersetzen (inkl. Lieferanten-Artikelnummer und HEK)
function save_article_suppliers(PDO $pdo, int $articleId, array $supplierIds, array $supplierArticleNumbers, array $hekPrices): void {
    $pdo->prepare('DELETE FROM article_suppliers WHERE article_id=?')->execute([$articleId]);
    $stmt = $pdo->prepare('INSERT INTO article_suppliers (article_id, supplier_id, supplier_article_number, hek_price) VALUES (?,?,?,?)');
    $seen = [];
    foreach ($supplierIds as $i => $supplierId) {
        $supplierId = (int)$supplierId;
        if (!$supplierId || isset($seen[$supplierId])) continue; // leere Zeile oder Lieferant doppelt gewählt - überspringen
        $seen[$supplierId] = true;
        $stmt->execute([
            $articleId,
            $supplierId,
            trim($supplierArticleNumbers[$i] ?? ''),
            (float)str_replace(',', '.', $hekPrices[$i] ?? '0'),
        ]);
    }
}

// Ansprechpartner eines Kunden ersetzen (mehrere Ansprechpartner möglich)
function save_customer_contacts(PDO $pdo, int $customerId, array $lastNames, array $firstNames, array $companies, array $phones, array $emails): void {
    $pdo->prepare('DELETE FROM customer_contacts WHERE customer_id=?')->execute([$customerId]);
    $stmt = $pdo->prepare('INSERT INTO customer_contacts (customer_id, last_name, first_name, company, phone, email) VALUES (?,?,?,?,?,?)');
    foreach ($lastNames as $i => $lastName) {
        $lastName = trim($lastName);
        $firstName = trim($firstNames[$i] ?? '');
        $company = trim($companies[$i] ?? '');
        $phone = trim($phones[$i] ?? '');
        $email = trim($emails[$i] ?? '');
        if ($lastName === '' && $firstName === '' && $company === '' && $phone === '' && $email === '') {
            continue; // leere Zeile - überspringen
        }
        $stmt->execute([$customerId, $lastName, $firstName, $company, $phone, $email]);
    }
}

function company_settings(): array {
    static $settings = null;
    if ($settings === null) {
        $settings = db()->query('SELECT * FROM company_settings WHERE id = 1')->fetch();
    }
    return $settings;
}

function ldap_settings(): array {
    static $settings = null;
    if ($settings === null) {
        $settings = db()->query('SELECT * FROM ldap_settings WHERE id = 1')->fetch();
    }
    return $settings;
}

function auth_config(): array {
    static $config = null;
    if ($config === null) {
        $config = db()->query('SELECT * FROM auth_config WHERE id = 1')->fetch();
    }
    return $config;
}

// Bekannte Module der Anwendung (für Gruppen-Berechtigungen und Auswahllisten)
function known_modules(): array {
    return [
        'artikel' => 'Artikel',
        'lager' => 'Lager',
        'kunden' => 'Kunden',
        'lieferanten' => 'Lieferanten',
        'angebote' => 'Angebote',
        'rechnungen' => 'Rechnungen',
        'kategorien' => 'Kategorien',
        'einstellungen' => 'Einstellungen',
    ];
}

// Prüft, ob der aktuell angemeldete Benutzer Zugriff ('read' oder 'write') auf
// ein Modul hat. Administratoren (role='admin') haben immer vollen Zugriff.
function has_permission(string $module, string $action = 'read'): bool {
    $user = current_user();
    if (!$user) {
        return false;
    }
    if ($user['role'] === 'admin') {
        return true;
    }
    if (empty($user['group_id'])) {
        return false;
    }
    static $cache = [];
    $key = $user['group_id'] . ':' . $module;
    if (!isset($cache[$key])) {
        $stmt = db()->prepare('SELECT can_read, can_write FROM group_permissions WHERE group_id = ? AND module = ?');
        $stmt->execute([$user['group_id'], $module]);
        $cache[$key] = $stmt->fetch() ?: ['can_read' => 0, 'can_write' => 0];
    }
    $field = $action === 'write' ? 'can_write' : 'can_read';
    return (bool)$cache[$key][$field];
}

// Bricht mit HTTP 403 ab, wenn der Benutzer keine Berechtigung für das
// angegebene Modul/die angegebene Aktion hat.
function require_permission(string $module, string $action = 'read'): void {
    require_login();
    if (!has_permission($module, $action)) {
        http_response_code(403);
        die('Zugriff verweigert: Ihnen fehlt die Berechtigung für dieses Modul.');
    }
}

function status_badge(string $status): string {
    $map = [
        'entwurf' => 'secondary', 'versendet' => 'info', 'angenommen' => 'success',
        'abgelehnt' => 'danger', 'bezahlt' => 'success', 'ueberfaellig' => 'danger',
        'storniert' => 'dark',
    ];
    $class = $map[$status] ?? 'secondary';
    return '<span class="badge bg-' . $class . '">' . e(ucfirst($status)) . '</span>';
}
