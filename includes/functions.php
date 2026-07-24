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

function company_settings(): array {
    static $settings = null;
    if ($settings === null) {
        $settings = db()->query('SELECT * FROM company_settings WHERE id = 1')->fetch();
    }
    return $settings;
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
