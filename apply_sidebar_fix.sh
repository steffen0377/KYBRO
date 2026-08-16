#!/bin/bash
# Ersetzt includes/functions.php und includes/header.php vollstaendig durch
# die neue Version mit zentraler module_url()-Navigation.
# Sicher mehrfach ausfuehrbar (ueberschreibt einfach erneut).
# Aufruf im Projekt-Root: bash apply_sidebar_fix.sh
set -e
if [ ! -f "includes/functions.php" ]; then
    echo "FEHLER: Bitte aus dem KYBRO-Projekt-Root ausfuehren (dort wo includes/ liegt)."
    exit 1
fi

cp includes/functions.php includes/functions.php.bak
cp includes/header.php includes/header.php.bak
echo "Backups angelegt: includes/functions.php.bak, includes/header.php.bak"

cat > includes/functions.php << 'KYBRO_FUNCTIONS_EOF'
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

/**
 * Zentrale Zuordnung: Dateiname (basename) -> Modulverzeichnis relativ zur
 * Projektwurzel. EINZIGE Stelle, die bei einer erneuten Verzeichnis-
 * Restrukturierung angepasst werden muss - Sidebar (includes/header.php)
 * und alle anderen absoluten Links nutzen ausschließlich module_url(),
 * statt Pfade hart zu kodieren.
 */
function module_directory_map(): array {
    return [
        'index.php' => '',
        'login.php' => '',
        'logout.php' => '',
        'artikel.php' => 'modules/stammdaten',
        'lager.php' => 'modules/stammdaten',
        'kunden.php' => 'modules/stammdaten',
        'lieferanten.php' => 'modules/stammdaten',
        'kategorien.php' => 'modules/stammdaten',
        'angebote.php' => 'modules/warenwirtschaft',
        'angebot_pdf.php' => 'modules/warenwirtschaft',
        'auftraege.php' => 'modules/warenwirtschaft',
        'auftrag_pdf.php' => 'modules/warenwirtschaft',
        'rechnungen.php' => 'modules/warenwirtschaft',
        'rechnung_pdf.php' => 'modules/warenwirtschaft',
        'einstellungen.php' => 'admin',
        'lizenzen.php' => 'admin',
        'benutzer.php' => 'admin',
    ];
}

/**
 * Liefert die absolute URL (inkl. APP_URL) zu einer Modul-Datei anhand
 * ihres Dateinamens, z.B. module_url('artikel.php', 'category=5').
 * Wirft eine Exception bei unbekannten Dateien, damit ein vergessener
 * Map-Eintrag sofort aus fällt statt eine tote Navigation zu erzeugen.
 */
function module_url(string $filename, string $queryString = ''): string {
    $map = module_directory_map();
    if (!array_key_exists($filename, $map)) {
        throw new InvalidArgumentException("module_url(): unbekannte Datei '$filename' - bitte in module_directory_map() ergänzen.");
    }
    $dir = $map[$filename];
    $path = $dir === '' ? $filename : $dir . '/' . $filename;
    $url = APP_URL . '/' . $path;
    return $queryString !== '' ? $url . '?' . $queryString : $url;
}

// Nächste Angebots-/Rechnungsnummer holen und Zähler erhöhen.
// WICHTIG: Diese Funktion wird immer innerhalb einer bereits laufenden
// Transaktion der aufrufenden Seite (angebote.php/rechnungen.php) aufgerufen
// und startet daher selbst KEINE eigene Transaktion (PDO unterstützt keine
// verschachtelten Transaktionen).
function next_document_number(string $type): string {
    $pdo = db();
    $fields = [
        'offer' => ['next_offer_number', 'offer_prefix'],
        'order' => ['next_order_number', 'order_prefix'],
        'invoice' => ['next_invoice_number', 'invoice_prefix'],
    ];
    [$field, $prefixField] = $fields[$type] ?? $fields['invoice'];
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

// Liefert den bereits existierenden Auftrag zu einem Angebot zurück, oder
// legt (inkl. Positionen) einen neuen an, falls noch keiner existiert.
// WICHTIG: Muss innerhalb einer bereits laufenden Transaktion der aufrufenden
// Seite aufgerufen werden (siehe next_document_number()).
function get_or_create_order_from_offer(PDO $pdo, array $offer): array {
    $stmt = $pdo->prepare('SELECT * FROM orders WHERE offer_id=?');
    $stmt->execute([$offer['id']]);
    $order = $stmt->fetch();
    if ($order) {
        return $order;
    }

    $itemsStmt = $pdo->prepare('SELECT * FROM offer_items WHERE offer_id=? ORDER BY position');
    $itemsStmt->execute([$offer['id']]);
    $offerItems = $itemsStmt->fetchAll();

    $number = next_document_number('order');
    $stmt = $pdo->prepare('INSERT INTO orders (order_number,offer_id,customer_id,order_date,status,notes,total_net,total_tax,total_gross,created_by) VALUES (?,?,?,?,?,?,?,?,?,?)');
    $stmt->execute([$number, $offer['id'], $offer['customer_id'], date('Y-m-d'), 'offen', $offer['notes'], $offer['total_net'], $offer['total_tax'], $offer['total_gross'], current_user()['id'] ?? null]);
    $orderId = $pdo->lastInsertId();

    $itemInsert = $pdo->prepare('INSERT INTO order_items (order_id,article_id,position,description,quantity,unit_price,tax_rate) VALUES (?,?,?,?,?,?,?)');
    foreach ($offerItems as $it) {
        $itemInsert->execute([$orderId, $it['article_id'], $it['position'], $it['description'], $it['quantity'], $it['unit_price'], $it['tax_rate']]);
    }

    $stmt = $pdo->prepare('SELECT * FROM orders WHERE id=?');
    $stmt->execute([$orderId]);
    return $stmt->fetch();
}

// Erstellt eine Rechnung aus den Positionen eines Auftrags (Lagerbestand wird
// dabei wie bisher direkt reduziert, sofern keine Seriennummernpflicht besteht).
// Gibt ['invoice_id'=>int,'invoice_number'=>string,'needs_serial_assignment'=>bool] zurück.
// WICHTIG: Muss innerhalb einer bereits laufenden Transaktion der aufrufenden
// Seite aufgerufen werden (siehe next_document_number()).
function create_invoice_from_order(PDO $pdo, array $order): array {
    $itemsStmt = $pdo->prepare('SELECT * FROM order_items WHERE order_id=? ORDER BY position');
    $itemsStmt->execute([$order['id']]);
    $items = $itemsStmt->fetchAll();

    $number = next_document_number('invoice');
    $stmt = $pdo->prepare('INSERT INTO invoices (invoice_number,offer_id,order_id,customer_id,invoice_date,due_date,status,notes,total_net,total_tax,total_gross,created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)');
    $stmt->execute([$number, $order['offer_id'], $order['id'], $order['customer_id'], date('Y-m-d'), date('Y-m-d', strtotime('+14 days')), 'entwurf', $order['notes'], $order['total_net'], $order['total_tax'], $order['total_gross'], current_user()['id'] ?? null]);
    $invoiceId = $pdo->lastInsertId();

    $itemStmt = $pdo->prepare('INSERT INTO invoice_items (invoice_id,article_id,position,description,quantity,unit_price,tax_rate) VALUES (?,?,?,?,?,?,?)');
    $needsSerialAssignment = false;
    foreach ($items as $it) {
        $itemStmt->execute([$invoiceId, $it['article_id'], $it['position'], $it['description'], $it['quantity'], $it['unit_price'], $it['tax_rate']]);
        if ($it['article_id']) {
            $trackStmt = $pdo->prepare('SELECT track_serials FROM articles WHERE id=?');
            $trackStmt->execute([$it['article_id']]);
            if ($trackStmt->fetch()['track_serials'] ?? false) {
                $needsSerialAssignment = true;
            } else {
                adjust_stock((int)$it['article_id'], -1 * (float)$it['quantity'], 'verkauf', 'invoice', $invoiceId, 'Verkauf über Rechnung ' . $number);
            }
        }
    }

    return ['invoice_id' => $invoiceId, 'invoice_number' => $number, 'needs_serial_assignment' => $needsSerialAssignment];
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
        'auftraege' => 'Aufträge',
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
        'storniert' => 'dark', 'offen' => 'secondary', 'in_bearbeitung' => 'info',
        'abgeschlossen' => 'success',
    ];
    $class = $map[$status] ?? 'secondary';
    return '<span class="badge bg-app-' . $class . '">' . e(ucfirst($status)) . '</span>';
}
KYBRO_FUNCTIONS_EOF

cat > includes/header.php << 'KYBRO_HEADER_EOF'
<?php
require_once __DIR__ . '/auth.php';
require_once __DIR__ . '/functions.php';
require_once __DIR__ . '/license.php';
require_login();
$u = current_user();
$company = company_settings();

// Aktiven Menüpunkt anhand des aktuellen Dateinamens bestimmen
$currentScript = basename($_SERVER['SCRIPT_NAME']);
function nav_active(string $script): string {
    global $currentScript;
    return $currentScript === $script ? 'active' : '';
}
function nav_group_active(array $scripts): bool {
    global $currentScript;
    return in_array($currentScript, $scripts, true);
}

// Kategorien für das Artikel-Untermenü laden und als Baum aufbauen
$navCategories = db()->query('SELECT id, name, parent_id FROM categories ORDER BY name')->fetchAll();
$navCategoriesByParent = [];
foreach ($navCategories as $c) {
    $navCategoriesByParent[$c['parent_id'] ?? 0][] = $c;
}
$navSelectedCategory = ($currentScript === 'artikel.php') ? (int)($_GET['category'] ?? 0) : 0;

function render_article_category_nav(array $byParent, int $parentId, int $depth, int $selectedId): void {
    if (empty($byParent[$parentId])) return;
    echo '<ul class="nav flex-column" style="padding-left:' . (12 + $depth * 14) . 'px;">';
    foreach ($byParent[$parentId] as $cat) {
        $isActive = $selectedId === (int)$cat['id'];
        echo '<li class="nav-item">';
        echo '<a class="nav-link text-white-50 ' . ($isActive ? 'active fw-bold' : '') . '" href="' . module_url('artikel.php', 'category=' . $cat['id']) . '">' . htmlspecialchars($cat['name']) . '</a>';
        render_article_category_nav($byParent, (int)$cat['id'], $depth + 1, $selectedId);
        echo '</li>';
    }
    echo '</ul>';
}
?>
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title><?= isset($pageTitle) ? e($pageTitle) . ' – ' : '' ?><?= e($company['company_name'] ?: 'Warenwirtschaft') ?></title>
<link href="<?= APP_URL ?>/assets/vendor/bootstrap/css/bootstrap.min.css" rel="stylesheet">
<link href="<?= APP_URL ?>/assets/vendor/bootstrap-icons/bootstrap-icons.css" rel="stylesheet">
<link href="<?= APP_URL ?>/assets/css/style.css?v=<?= @filemtime(__DIR__ . '/../assets/css/style.css') ?: '1' ?>" rel="stylesheet">
</head>
<body>
<div class="d-flex" id="wrapper">

  <nav class="sidebar sidebar-bg text-white p-3 d-none d-md-block" id="sidebar">
    <div class="sidebar-brand text-center mb-4">
      <a href="<?= module_url('index.php') ?>" class="text-white text-decoration-none">
        <?php if (!empty($company['logo_path'])): ?>
          <img src="<?= APP_URL ?>/<?= e($company['logo_path']) ?>" alt="Logo" class="sidebar-logo mb-2">
        <?php else: ?>
          <div class="fs-2 mb-1">📦</div>
        <?php endif; ?>
        <div class="fw-bold"><?= e($company['company_name'] ?: 'Warenwirtschaft') ?></div>
      </a>
    </div>
    <?php
      $verkaufActive = nav_group_active(['angebote.php', 'auftraege.php', 'rechnungen.php']);
      $einkaufActive = nav_group_active(['lieferanten.php']);
      $einstellungenActive = nav_group_active(['einstellungen.php', 'kategorien.php', 'lizenzen.php']);
      $hasWarenwirtschaftLicense = has_module_license('warenwirtschaft');
    ?>
    <ul class="nav nav-pills flex-column gap-1">
      <li class="nav-item"><a class="nav-link text-white <?= nav_active('index.php') ?>" href="<?= module_url('index.php') ?>"><i class="bi bi-speedometer2 me-2"></i>Dashboard</a></li>
      <li class="nav-item">
        <a class="nav-link text-white d-flex align-items-center <?= nav_active('artikel.php') ?> <?= $currentScript === 'artikel.php' ? '' : 'collapsed' ?>" href="<?= module_url('artikel.php') ?>">
          <i class="bi bi-box-seam me-2"></i>Artikel
          <i class="bi bi-chevron-down ms-auto small nav-chevron"></i>
        </a>
        <?php if ($currentScript === 'artikel.php'): ?>
          <?php render_article_category_nav($navCategoriesByParent, 0, 0, $navSelectedCategory); ?>
        <?php endif; ?>
      </li>
      <li class="nav-item"><a class="nav-link text-white <?= nav_active('lager.php') ?>" href="<?= module_url('lager.php') ?>"><i class="bi bi-archive me-2"></i>Lager</a></li>
      <li class="nav-item"><a class="nav-link text-white <?= nav_active('kunden.php') ?>" href="<?= module_url('kunden.php') ?>"><i class="bi bi-people me-2"></i>Kunden</a></li>

      <?php if ($hasWarenwirtschaftLicense): ?>
      <li class="nav-item">
        <a class="nav-link text-white d-flex align-items-center <?= $verkaufActive ? '' : 'collapsed' ?>" href="#navVerkauf" data-bs-toggle="collapse" role="button" aria-expanded="<?= $verkaufActive ? 'true' : 'false' ?>" aria-controls="navVerkauf">
          <i class="bi bi-cart me-2"></i>Verkauf
          <i class="bi bi-chevron-down ms-auto small nav-chevron"></i>
        </a>
        <div class="collapse <?= $verkaufActive ? 'show' : '' ?>" id="navVerkauf">
          <ul class="nav flex-column ms-3">
            <li class="nav-item"><a class="nav-link text-white-50 <?= nav_active('angebote.php') ?>" href="<?= module_url('angebote.php') ?>"><i class="bi bi-file-earmark-text me-2"></i>Angebote</a></li>
            <li class="nav-item"><a class="nav-link text-white-50 <?= nav_active('auftraege.php') ?>" href="<?= module_url('auftraege.php') ?>"><i class="bi bi-clipboard-check me-2"></i>Aufträge</a></li>
            <li class="nav-item"><a class="nav-link text-white-50 <?= nav_active('rechnungen.php') ?>" href="<?= module_url('rechnungen.php') ?>"><i class="bi bi-receipt me-2"></i>Rechnungen</a></li>
          </ul>
        </div>
      </li>
      <?php elseif ($u['role'] === 'admin'): ?>
      <li class="nav-item">
        <a class="nav-link text-white-50 d-flex align-items-center" href="<?= module_url('lizenzen.php') ?>" title="Fuer dieses Modul liegt keine gueltige Lizenz vor">
          <i class="bi bi-cart me-2"></i>Verkauf <span class="badge bg-app-secondary ms-2">Lizenz erforderlich</span>
        </a>
      </li>
      <?php endif; ?>

      <li class="nav-item">
        <a class="nav-link text-white d-flex align-items-center <?= $einkaufActive ? '' : 'collapsed' ?>" href="#navEinkauf" data-bs-toggle="collapse" role="button" aria-expanded="<?= $einkaufActive ? 'true' : 'false' ?>" aria-controls="navEinkauf">
          <i class="bi bi-bag me-2"></i>Einkauf
          <i class="bi bi-chevron-down ms-auto small nav-chevron"></i>
        </a>
        <div class="collapse <?= $einkaufActive ? 'show' : '' ?>" id="navEinkauf">
          <ul class="nav flex-column ms-3">
            <li class="nav-item"><a class="nav-link text-white-50 <?= nav_active('lieferanten.php') ?>" href="<?= module_url('lieferanten.php') ?>"><i class="bi bi-truck me-2"></i>Lieferanten</a></li>
          </ul>
        </div>
      </li>

      <?php if ($u['role'] === 'admin'): ?>
      <li class="nav-item mt-3"><hr class="text-white-50 my-1"></li>
      <li class="nav-item">
        <a class="nav-link text-white d-flex align-items-center <?= $einstellungenActive ? '' : 'collapsed' ?>" href="#navEinstellungen" data-bs-toggle="collapse" role="button" aria-expanded="<?= $einstellungenActive ? 'true' : 'false' ?>" aria-controls="navEinstellungen">
          <i class="bi bi-gear me-2"></i>Einstellungen
          <i class="bi bi-chevron-down ms-auto small nav-chevron"></i>
        </a>
        <div class="collapse <?= $einstellungenActive ? 'show' : '' ?>" id="navEinstellungen">
          <ul class="nav flex-column ms-3">
            <li class="nav-item"><a class="nav-link text-white-50 <?= nav_active('einstellungen.php') ?>" href="<?= module_url('einstellungen.php') ?>"><i class="bi bi-building me-2"></i>Firmeneinstellungen</a></li>
            <li class="nav-item"><a class="nav-link text-white-50 <?= nav_active('kategorien.php') ?>" href="<?= module_url('kategorien.php') ?>"><i class="bi bi-tags me-2"></i>Kategorien</a></li>
            <li class="nav-item"><a class="nav-link text-white-50 <?= nav_active('lizenzen.php') ?>" href="<?= module_url('lizenzen.php') ?>"><i class="bi bi-key me-2"></i>Lizenzen</a></li>
          </ul>
        </div>
      </li>
      <?php endif; ?>
    </ul>
  </nav>

  <div class="flex-grow-1" style="min-width:0;">
    <div class="topbar d-flex justify-content-between align-items-center px-3 py-2 border-bottom bg-white">
      <button class="btn btn-app-outline-secondary d-md-none" type="button" onclick="document.getElementById('sidebar').classList.toggle('d-none')">
        <i class="bi bi-list"></i>
      </button>
      <span class="d-none d-md-inline"></span>
      <div>
        <span class="me-3">Angemeldet als <strong><?= e($u['full_name']) ?></strong></span>
        <a href="<?= APP_URL ?>/logout.php" class="btn btn-app-outline-secondary btn-sm">Abmelden</a>
      </div>
    </div>
    <div class="container-fluid p-4">
    <?php foreach (get_flashes() as $f): ?>
      <div class="alert alert-app-<?= e($f['type']) ?> alert-dismissible fade show" role="alert">
        <?= e($f['message']) ?>
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      </div>
    <?php endforeach; ?>
KYBRO_HEADER_EOF

echo "Fertig. includes/functions.php und includes/header.php wurden aktualisiert."
