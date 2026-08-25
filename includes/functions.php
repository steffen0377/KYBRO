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
        'abos.php' => 'modules/warenwirtschaft',
        'einstellungen.php' => 'admin',
        'formulareinstellungen.php' => 'admin',
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

    $itemInsert = $pdo->prepare('INSERT INTO order_items (order_id,article_id,position,description,quantity,unit_price,tax_rate,pricing_option_id,billing_type) VALUES (?,?,?,?,?,?,?,?,?)');
    foreach ($offerItems as $it) {
        $itemInsert->execute([$orderId, $it['article_id'], $it['position'], $it['description'], $it['quantity'], $it['unit_price'], $it['tax_rate'], $it['pricing_option_id'] ?? null, $it['billing_type'] ?? 'einmalig']);
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

    $itemStmt = $pdo->prepare('INSERT INTO invoice_items (invoice_id,article_id,position,description,quantity,unit_price,tax_rate,pricing_option_id,billing_type) VALUES (?,?,?,?,?,?,?,?,?)');
    $needsSerialAssignment = false;
    foreach ($items as $it) {
        $itemStmt->execute([$invoiceId, $it['article_id'], $it['position'], $it['description'], $it['quantity'], $it['unit_price'], $it['tax_rate'], $it['pricing_option_id'] ?? null, $it['billing_type'] ?? 'einmalig']);
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

    create_subscriptions_from_invoice_items($pdo, $invoiceId, (int)$order['customer_id'], (int)$order['id'], date('Y-m-d'));

    return ['invoice_id' => $invoiceId, 'invoice_number' => $number, 'needs_serial_assignment' => $needsSerialAssignment];
}

// ---------- ABONNEMENTS ----------

// Legt für alle Abo-Positionen (billing_type != 'einmalig') einer soeben
// erstellten Rechnung je einen subscriptions-Datensatz an. Wird sowohl beim
// direkten Anlegen einer Rechnung als auch beim Umwandeln Auftrag->Rechnung
// aufgerufen. WICHTIG: Muss innerhalb einer bereits laufenden Transaktion
// der aufrufenden Seite aufgerufen werden.
function create_subscriptions_from_invoice_items(PDO $pdo, int $invoiceId, int $customerId, ?int $orderId, string $invoiceDate): void {
    $stmt = $pdo->prepare("SELECT * FROM invoice_items WHERE invoice_id=? AND billing_type IN ('monatlich','jaehrlich')");
    $stmt->execute([$invoiceId]);
    $insert = $pdo->prepare('INSERT INTO subscriptions
        (customer_id,article_id,pricing_option_id,order_id,origin_invoice_id,billing_cycle,price,start_date,next_billing_date,min_runtime_months,notice_period_days,earliest_cancellation_date,status)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,\'aktiv\')');

    foreach ($stmt->fetchAll() as $item) {
        if (!$item['article_id']) {
            continue; // Abos nur für echte Artikel, keine manuellen Freitext-Positionen
        }
        $cycleMonths = $item['billing_type'] === 'jaehrlich' ? 12 : 1;
        $minRuntime = null;
        $noticeDays = 30;
        if ($item['pricing_option_id']) {
            $poStmt = $pdo->prepare('SELECT min_runtime_months, notice_period_days FROM article_pricing_options WHERE id=?');
            $poStmt->execute([$item['pricing_option_id']]);
            if ($po = $poStmt->fetch()) {
                $minRuntime = $po['min_runtime_months'] !== null ? (int)$po['min_runtime_months'] : null;
                $noticeDays = $po['notice_period_days'] !== null ? (int)$po['notice_period_days'] : 30;
            }
        }
        $earliestCancellation = $minRuntime ? date('Y-m-d', strtotime($invoiceDate . " +{$minRuntime} months")) : null;
        $nextBilling = date('Y-m-d', strtotime($invoiceDate . " +{$cycleMonths} months"));

        $insert->execute([
            $customerId, $item['article_id'], $item['pricing_option_id'] ?: null, $orderId, $invoiceId,
            $item['billing_type'], $item['unit_price'], $invoiceDate, $nextBilling, $minRuntime, $noticeDays, $earliestCancellation,
        ]);
    }
}

// Rechnet für ein gegebenes Abo den Kündigungstermin aus: das Abo endet
// frühestens nach Ablauf der Mindestlaufzeit UND frühestens nach Ablauf der
// Kündigungsfrist ab Kündigungseingang - jeweils aufgerundet auf den
// nächsten regulären Abrechnungstermin, damit die Kündigung immer zu einem
// Zyklusende wirksam wird.
function calculate_subscription_cancellation(array $subscription, ?string $requestDate = null): array {
    $requestDate = $requestDate ?: date('Y-m-d');
    $earliestByNotice = date('Y-m-d', strtotime($requestDate . ' +' . (int)($subscription['notice_period_days'] ?? 0) . ' days'));
    $earliest = $earliestByNotice;
    if (!empty($subscription['earliest_cancellation_date']) && strtotime($subscription['earliest_cancellation_date']) > strtotime($earliest)) {
        $earliest = $subscription['earliest_cancellation_date'];
    }

    $cycleMonths = $subscription['billing_cycle'] === 'jaehrlich' ? 12 : 1;
    $effective = $subscription['start_date'];
    while (strtotime($effective) < strtotime($earliest)) {
        $effective = date('Y-m-d', strtotime($effective . " +{$cycleMonths} months"));
    }
    return ['cancellation_requested_date' => $requestDate, 'cancellation_effective_date' => $effective];
}

// Trägt next_billing_date eines Abos um einen Abrechnungszyklus weiter.
// Wird aufgerufen, sobald eine automatisch erzeugte Entwurfs-Rechnung den
// Entwurfsstatus verlässt (manuelle Freigabe durch den Anwender).
function advance_subscription_billing_date(PDO $pdo, int $subscriptionId): void {
    $stmt = $pdo->prepare('SELECT * FROM subscriptions WHERE id=?');
    $stmt->execute([$subscriptionId]);
    $sub = $stmt->fetch();
    if (!$sub) {
        return;
    }
    $cycleMonths = $sub['billing_cycle'] === 'jaehrlich' ? 12 : 1;
    $newNext = date('Y-m-d', strtotime($sub['next_billing_date'] . " +{$cycleMonths} months"));
    $pdo->prepare('UPDATE subscriptions SET next_billing_date=? WHERE id=?')->execute([$newNext, $subscriptionId]);
}

// Prüft alle aktiven bzw. gekündigten (aber noch nicht abgelaufenen) Abos auf
// Fälligkeit und legt dafür jeweils eine Rechnung im Entwurfsstatus an.
// next_billing_date wird HIER bewusst nicht verändert (siehe
// advance_subscription_billing_date) - das macht die Funktion idempotent:
// mehrfaches Ausführen am selben Tag erzeugt keine doppelten Entwürfe.
// Beendet außerdem Abos, deren Kündigung wirksam geworden ist.
// Gibt eine Liste der neu erzeugten Rechnungen zurück.
function generate_subscription_invoice_drafts(PDO $pdo): array {
    $today = date('Y-m-d');

    $pdo->prepare("UPDATE subscriptions SET status='beendet', end_date=cancellation_effective_date
                    WHERE status='gekuendigt' AND cancellation_effective_date <= ?")->execute([$today]);

    $stmt = $pdo->prepare("SELECT * FROM subscriptions
                            WHERE status IN ('aktiv','gekuendigt') AND next_billing_date <= ?
                              AND (cancellation_effective_date IS NULL OR next_billing_date < cancellation_effective_date)");
    $stmt->execute([$today]);

    $created = [];
    foreach ($stmt->fetchAll() as $sub) {
        // Bereits ein Entwurf für diesen Abrechnungstermin vorhanden? (Idempotenz)
        $existsStmt = $pdo->prepare('SELECT id FROM invoices WHERE subscription_id=? AND period_start=?');
        $existsStmt->execute([$sub['id'], $sub['next_billing_date']]);
        if ($existsStmt->fetch()) {
            continue;
        }

        $periodStart = $sub['next_billing_date'];
        $cycleMonths = $sub['billing_cycle'] === 'jaehrlich' ? 12 : 1;
        $periodEnd = date('Y-m-d', strtotime($periodStart . " +{$cycleMonths} months -1 day"));

        $custStmt = $pdo->prepare('SELECT tax_exempt FROM customers WHERE id=?');
        $custStmt->execute([$sub['customer_id']]);
        $customer = $custStmt->fetch();

        $artStmt = $pdo->prepare('SELECT name, tax_rate FROM articles WHERE id=?');
        $artStmt->execute([$sub['article_id']]);
        $article = $artStmt->fetch();

        $taxRate = !empty($customer['tax_exempt']) ? 0.0 : (float)($article['tax_rate'] ?? 19);
        $net = round((float)$sub['price'], 2);
        $tax = round($net * $taxRate / 100, 2);

        $number = next_document_number('invoice');
        $stmt2 = $pdo->prepare('INSERT INTO invoices
            (invoice_number,customer_id,invoice_date,due_date,status,notes,total_net,total_tax,total_gross,subscription_id,period_start,period_end)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)');
        $stmt2->execute([
            $number, $sub['customer_id'], $today, date('Y-m-d', strtotime('+14 days')), 'entwurf',
            'Automatisch erzeugte Abo-Rechnung für den Zeitraum ' . date('d.m.Y', strtotime($periodStart)) . ' - ' . date('d.m.Y', strtotime($periodEnd)) . '. Bitte prüfen und freigeben.',
            $net, $tax, round($net + $tax, 2), $sub['id'], $periodStart, $periodEnd,
        ]);
        $invoiceId = $pdo->lastInsertId();

        $itemStmt = $pdo->prepare('INSERT INTO invoice_items (invoice_id,article_id,position,description,quantity,unit_price,tax_rate,pricing_option_id,billing_type) VALUES (?,?,?,?,?,?,?,?,?)');
        $description = ($article['name'] ?? 'Abonnement') . ' (Abo ' . date('d.m.Y', strtotime($periodStart)) . ' - ' . date('d.m.Y', strtotime($periodEnd)) . ')';
        $itemStmt->execute([$invoiceId, $sub['article_id'], 1, $description, 1, $net, $taxRate, $sub['pricing_option_id'], $sub['billing_cycle']]);

        $created[] = ['invoice_id' => $invoiceId, 'invoice_number' => $number, 'subscription_id' => $sub['id']];
    }
    return $created;
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

// Zeichnet "Seite X von Y" per dompdf-Canvas-API direkt in das PDF.
// WICHTIG: {PAGE_NUM}/{PAGE_COUNT} als reiner HTML-Text (z.B. in
// pdf_template.php) wird von dompdf NICHT automatisch ersetzt - dieser
// Platzhalter-Mechanismus funktioniert nur über die Canvas-Methode
// page_text(), die aktiv nach dem Rendern aufgerufen werden muss (siehe
// die *_pdf.php-Dateien: Aufruf direkt nach $dompdf->render()).
// $marginBottom/$marginRight kommen aus den Formulareinstellungen (mm) und
// sorgen dafür, dass die Seitenzahl - wie der übrige Fußzeilenbereich -
// mit der Randeinstellung mitwandert statt an der physischen Seitenkante
// zu kleben.
function render_pdf_page_number(\Dompdf\Dompdf $dompdf, float $marginBottom, float $marginRight): void {
    $mmToPt = 72 / 25.4;
    $size = 9;
    $canvas = $dompdf->getCanvas();
    $fontMetrics = $dompdf->getFontMetrics();
    $font = $fontMetrics->getFont('helvetica', 'normal');
    // Breite wird anhand einer zweistelligen Beispielzahl geschätzt, da die
    // Platzhalter zum Zeitpunkt der Messung noch nicht durch die tatsächliche
    // Seitenzahl ersetzt sind (das übernimmt dompdf erst beim Ausgeben der
    // fertigen PDF-Datei). Für mehr als 99 Seiten ist der rechte Rand daher
    // nur noch näherungsweise korrekt.
    $textWidth = $fontMetrics->getTextWidth('Seite 88 von 88', $font, $size);
    $x = $canvas->get_width() - ($marginRight * $mmToPt) - $textWidth;
    $y = $canvas->get_height() - (($marginBottom + 4) * $mmToPt);
    $canvas->page_text($x, $y, 'Seite {PAGE_NUM} von {PAGE_COUNT}', $font, $size, [0.4, 0.4, 0.4]);
}

// Werkseinstellungen (Fallback-Werte) für die Formulareinstellungen, gruppiert
// nach Scope. 'global' gilt für alle Formulare, sofern im jeweiligen Scope
// kein eigener Wert hinterlegt ist. Neue Einstellungen können hier ergänzt
// werden, ohne dass eine weitere Migration nötig ist (form_settings ist eine
// Key-Value-Tabelle, siehe database/migrations/migration_019_form_settings.sql).
function form_setting_defaults(): array {
    return [
        'global' => [
            'font_family' => 'Helvetica',
            'font_size' => '10',
            'margin_top' => '20',
            'margin_bottom' => '20',
            'margin_left' => '20',
            'margin_right' => '20',
            'use_letterhead' => '1',
            'logo_position' => 'links',
            'logo_height' => '20',
            'accent_color' => '#0d6efd',
            'footer_text' => '',
            'show_page_number' => '1',
            'show_footer_company_block' => '1',
            'table_columns' => 'pos,artikelnr,bezeichnung,menge,einzelpreis,rabatt,gesamt',
            'currency_format' => 'de_DE',
            'date_format' => 'd.m.Y',
            'decimal_separator' => ',',
            'language' => 'de',
        ],
        'angebot' => [
            'document_title' => 'Angebot',
            'intro_text' => 'Vielen Dank für Ihre Anfrage. Wir unterbreiten Ihnen folgendes Angebot:',
            'closing_text' => 'Wir freuen uns auf Ihren Auftrag.',
            'term_label' => 'Gültig bis',
            'term_days' => '30',
            'columns_override' => '',
            'show_discount_column' => '1',
            'show_tax_breakdown' => '1',
            'show_subtotal' => '1',
            // Leer = vererbt (folgt dem globalen Wert bzw. dessen Default).
            // Siehe get_raw_form_setting() für die Tri-State-Auflösung.
            'show_footer_company_block' => '',
        ],
        'auftrag' => [
            'document_title' => 'Auftragsbestätigung',
            'intro_text' => 'Wir bestätigen Ihnen folgenden Auftrag:',
            'closing_text' => 'Vielen Dank für Ihren Auftrag.',
            'term_label' => 'Liefertermin',
            'term_days' => '14',
            'columns_override' => '',
            'show_discount_column' => '1',
            'show_tax_breakdown' => '1',
            'show_subtotal' => '1',
            'show_footer_company_block' => '',
        ],
        'rechnung' => [
            'document_title' => 'Rechnung',
            'intro_text' => 'Wir stellen Ihnen folgende Leistungen in Rechnung:',
            'closing_text' => 'Vielen Dank für Ihr Vertrauen.',
            'term_label' => 'Zahlungsziel',
            'term_days' => '14',
            'columns_override' => '',
            'show_discount_column' => '1',
            'show_tax_breakdown' => '1',
            'show_subtotal' => '1',
            'show_footer_company_block' => '',
            'zugferd_profile' => 'BASIC',
            'skonto_text' => '',
        ],
    ];
}

// Lädt (einmalig pro Request, static cache) alle gespeicherten Formular-
// einstellungen aus der Datenbank. Gemeinsam genutzt von get_form_setting()
// (aufgelöster Wert inkl. Fallback-Kette) und get_raw_form_setting() (roher,
// unaufgelöster Wert für Tri-State-Steuerelemente).
function form_settings_cache(): array {
    static $cache = null;
    if ($cache === null) {
        $cache = [];
        $stmt = db()->query('SELECT scope, setting_key, setting_value FROM form_settings');
        foreach ($stmt as $row) {
            $cache[$row['scope']][$row['setting_key']] = $row['setting_value'];
        }
    }
    return $cache;
}

// Liest eine einzelne Formulareinstellung mit Fallback-Kette:
// scope-spezifischer Wert -> globaler Wert -> hinterlegter Default.
function get_form_setting(string $scope, string $key, $default = null) {
    $cache = form_settings_cache();
    if (isset($cache[$scope][$key]) && $cache[$scope][$key] !== '') {
        return $cache[$scope][$key];
    }
    if ($scope !== 'global' && isset($cache['global'][$key]) && $cache['global'][$key] !== '') {
        return $cache['global'][$key];
    }
    $defaults = form_setting_defaults();
    if (isset($defaults[$scope][$key])) {
        return $defaults[$scope][$key];
    }
    if (isset($defaults['global'][$key])) {
        return $defaults['global'][$key];
    }
    return $default;
}

// Liefert den rohen, für genau diesen Scope explizit gespeicherten Wert -
// ohne Fallback-Kette. Ein leerer String (bzw. gar kein Eintrag) bedeutet
// "nicht überschrieben" und liefert null. Wird von Tri-State-Steuerelementen
// (aktiviert/deaktiviert/vererbt) in den Formulareinstellungen benötigt, um
// zwischen "explizit auf diesem Formulartyp gesetzt" und "geerbt" zu
// unterscheiden - get_form_setting() liefert dafür bereits den aufgelösten
// Wert und ist an dieser Stelle nicht geeignet.
function get_raw_form_setting(string $scope, string $key): ?string {
    $cache = form_settings_cache();
    if (isset($cache[$scope][$key]) && $cache[$scope][$key] !== '') {
        return $cache[$scope][$key];
    }
    return null;
}

// Liefert alle Einstellungen eines Scopes (inkl. Fallback global -> Default)
// als assoziatives Array - genutzt zur Vorbelegung der Einstellungsseite.
function get_form_settings_for_scope(string $scope): array {
    $defaults = form_setting_defaults();
    $result = [];
    foreach (array_keys($defaults[$scope] ?? []) as $key) {
        $result[$key] = get_form_setting($scope, $key);
    }
    return $result;
}

// Speichert eine einzelne Formulareinstellung (Insert-or-Update via
// ON DUPLICATE KEY, passend zum UNIQUE-Index auf (scope, setting_key)).
function save_form_setting(string $scope, string $key, string $value): void {
    $stmt = db()->prepare('INSERT INTO form_settings (scope, setting_key, setting_value) VALUES (?,?,?)
        ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)');
    $stmt->execute([$scope, $key, $value]);
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
        'abos' => 'Abonnements',
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
