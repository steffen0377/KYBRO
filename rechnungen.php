<?php
require_once __DIR__ . '/includes/auth.php';
require_once __DIR__ . '/includes/functions.php';
require_login();
$pdo = db();
$action = $_GET['action'] ?? 'list';

function calc_totals_inv(array $descriptions, array $quantities, array $prices, array $taxRates): array {
    $net = 0.0; $tax = 0.0;
    foreach ($descriptions as $i => $desc) {
        if (trim($desc) === '') continue;
        $qty = (float)str_replace(',', '.', $quantities[$i]);
        $price = (float)str_replace(',', '.', $prices[$i]);
        $rate = (float)str_replace(',', '.', $taxRates[$i]);
        $lineNet = $qty * $price;
        $net += $lineNet;
        $tax += $lineNet * $rate / 100;
    }
    return [round($net,2), round($tax,2), round($net+$tax,2)];
}

// Für eine Rechnung: welche Positionen (mit seriennummernpflichtigem Artikel)
// benötigen noch die Zuordnung von Seriennummern?
function pending_serial_items(PDO $pdo, int $invoiceId): array {
    $items = $pdo->prepare("SELECT ii.*, a.name AS article_name, a.track_serials
                             FROM invoice_items ii
                             JOIN articles a ON a.id = ii.article_id
                             WHERE ii.invoice_id = ? AND a.track_serials = 1");
    $items->execute([$invoiceId]);
    $result = [];
    foreach ($items->fetchAll() as $it) {
        $countStmt = $pdo->prepare('SELECT COUNT(*) c FROM article_serials WHERE invoice_id=? AND article_id=?');
        $countStmt->execute([$invoiceId, $it['article_id']]);
        $assigned = (int)$countStmt->fetch()['c'];
        $remaining = (int)$it['quantity'] - $assigned;
        if ($remaining > 0) {
            $it['remaining'] = $remaining;
            $result[] = $it;
        }
    }
    return $result;
}

// ---------- SPEICHERN ----------
if ($_SERVER['REQUEST_METHOD'] === 'POST' && $action === 'save') {
    csrf_check();
    $id = (int)($_POST['id'] ?? 0);
    $customerId = (int)$_POST['customer_id'];
    $descriptions = $_POST['description'] ?? [];
    $quantities = $_POST['quantity'] ?? [];
    $prices = $_POST['unit_price'] ?? [];
    $taxRates = $_POST['tax_rate'] ?? [];
    $articleIds = $_POST['article_id'] ?? [];

    if (!$customerId || !array_filter($descriptions, fn($d)=>trim($d)!=='')) {
        flash('danger', 'Bitte Kunde und mindestens eine Position angeben.');
        redirect('rechnungen.php?action=' . ($id ? "edit&id=$id" : 'new'));
    }

    [$net, $tax, $gross] = calc_totals_inv($descriptions, $quantities, $prices, $taxRates);
    $isNew = !$id;

    // Seriennummernpflicht der beteiligten Artikel vorab nachschlagen
    $usedArticleIds = array_values(array_unique(array_filter($articleIds)));
    $trackSerialsMap = [];
    if ($usedArticleIds) {
        $placeholders = implode(',', array_fill(0, count($usedArticleIds), '?'));
        $stmt = $pdo->prepare("SELECT id, track_serials FROM articles WHERE id IN ($placeholders)");
        $stmt->execute($usedArticleIds);
        foreach ($stmt->fetchAll() as $row) {
            $trackSerialsMap[$row['id']] = (bool)$row['track_serials'];
        }
    }

    $pdo->beginTransaction();
    try {
        if ($id) {
            $stmt = $pdo->prepare('UPDATE invoices SET customer_id=?,invoice_date=?,due_date=?,status=?,notes=?,total_net=?,total_tax=?,total_gross=? WHERE id=?');
            $stmt->execute([$customerId, $_POST['invoice_date'], $_POST['due_date'] ?: null, $_POST['status'], trim($_POST['notes']), $net, $tax, $gross, $id]);
            $pdo->prepare('DELETE FROM invoice_items WHERE invoice_id=?')->execute([$id]);
            $invoiceId = $id;
        } else {
            $number = next_document_number('invoice');
            $stmt = $pdo->prepare('INSERT INTO invoices (invoice_number,customer_id,invoice_date,due_date,status,notes,total_net,total_tax,total_gross,created_by) VALUES (?,?,?,?,?,?,?,?,?,?)');
            $stmt->execute([$number, $customerId, $_POST['invoice_date'], $_POST['due_date'] ?: null, $_POST['status'], trim($_POST['notes']), $net, $tax, $gross, current_user()['id']]);
            $invoiceId = $pdo->lastInsertId();
        }
        $pos = 0;
        $needsSerialAssignment = false;
        $itemStmt = $pdo->prepare('INSERT INTO invoice_items (invoice_id,article_id,position,description,quantity,unit_price,tax_rate) VALUES (?,?,?,?,?,?,?)');
        foreach ($descriptions as $i => $desc) {
            if (trim($desc) === '') continue;
            $articleId = $articleIds[$i] ?: null;
            $qty = (float)str_replace(',', '.', $quantities[$i]);
            $itemStmt->execute([$invoiceId, $articleId, $pos++, trim($desc), $qty, (float)str_replace(',', '.', $prices[$i]), (float)str_replace(',', '.', $taxRates[$i])]);
            // Lagerbestand nur bei NEUEN, direkt angelegten Rechnungen automatisch reduzieren
            if ($isNew && $articleId) {
                if (!empty($trackSerialsMap[$articleId])) {
                    // Seriennummern müssen gezielt zugeordnet werden -> Bestand wird
                    // erst bei der Zuordnung (assign_serials) reduziert.
                    $needsSerialAssignment = true;
                } else {
                    adjust_stock((int)$articleId, -1 * $qty, 'verkauf', 'invoice', $invoiceId, 'Verkauf über Rechnung');
                }
            }
        }
        $pdo->commit();
        if ($needsSerialAssignment) {
            flash('success', 'Rechnung gespeichert. Bitte jetzt die Seriennummern der verkauften Geräte zuordnen.');
            redirect('rechnungen.php?action=assign_serials&id=' . $invoiceId);
        }
        flash('success', 'Rechnung gespeichert.' . ($isNew ? ' Lagerbestand wurde reduziert.' : ' Hinweis: Lagerbestand wird bei Bearbeitung bestehender Rechnungen nicht automatisch angepasst.'));
    } catch (Exception $e) {
        $pdo->rollBack();
        flash('danger', 'Fehler beim Speichern: ' . $e->getMessage());
        redirect('rechnungen.php');
    }
    redirect('rechnungen.php?action=view&id=' . $invoiceId);
}

// ---------- SERIENNUMMERN ZUORDNEN ----------
if ($action === 'assign_serials' && $_SERVER['REQUEST_METHOD'] === 'POST') {
    csrf_check();
    $invoiceId = (int)$_POST['invoice_id'];
    $selections = $_POST['serials'] ?? []; // [article_id => [serial_id, serial_id, ...]]

    $pdo->beginTransaction();
    try {
        foreach ($selections as $articleId => $serialIds) {
            $articleId = (int)$articleId;
            foreach ($serialIds as $serialId) {
                $stmt = $pdo->prepare("SELECT * FROM article_serials WHERE id=? AND article_id=? AND status='lager'");
                $stmt->execute([(int)$serialId, $articleId]);
                $serial = $stmt->fetch();
                if (!$serial) continue; // bereits vergeben oder ungültig - überspringen
                $pdo->prepare("UPDATE article_serials SET status='verkauft', invoice_id=?, sold_at=NOW() WHERE id=?")
                    ->execute([$invoiceId, $serial['id']]);
                adjust_stock($articleId, -1, 'verkauf', 'invoice', $invoiceId, 'Verkauf über Rechnung (S/N: ' . $serial['serial_number'] . ')');
            }
        }
        $pdo->commit();
        $remaining = pending_serial_items($pdo, $invoiceId);
        if ($remaining) {
            flash('danger', 'Es fehlen noch Seriennummern für: ' . implode(', ', array_map(fn($i)=>$i['article_name'].' ('.$i['remaining'].'x)', $remaining)));
            redirect('rechnungen.php?action=assign_serials&id=' . $invoiceId);
        }
        flash('success', 'Seriennummern zugeordnet, Lagerbestand aktualisiert.');
    } catch (Exception $e) {
        $pdo->rollBack();
        flash('danger', 'Fehler: ' . $e->getMessage());
    }
    redirect('rechnungen.php?action=view&id=' . $invoiceId);
}

// ---------- STATUS ÄNDERN ----------
if ($action === 'status' && $_SERVER['REQUEST_METHOD'] === 'POST') {
    csrf_check();
    $stmt = $pdo->prepare('UPDATE invoices SET status=? WHERE id=?');
    $stmt->execute([$_POST['status'], (int)$_POST['id']]);
    flash('success', 'Status aktualisiert.');
    redirect('rechnungen.php?action=view&id=' . (int)$_POST['id']);
}

// ---------- LÖSCHEN (nur Entwürfe) ----------
if ($action === 'delete' && isset($_GET['id']) && hash_equals(csrf_token(), $_GET['token'] ?? '')) {
    $stmt = $pdo->prepare("DELETE FROM invoices WHERE id=? AND status='entwurf'");
    $stmt->execute([(int)$_GET['id']]);
    flash('success', 'Rechnung gelöscht (nur Entwürfe können gelöscht werden).');
    redirect('rechnungen.php');
}

// ---------- AB HIER BEGINNT DIE HTML-AUSGABE ----------
$pageTitle = 'Rechnungen';
require_once __DIR__ . '/includes/header.php';

if ($action === 'assign_serials') {
    $stmt = $pdo->prepare('SELECT invoice_number FROM invoices WHERE id=?');
    $stmt->execute([(int)$_GET['id']]);
    $inv = $stmt->fetch();
    if (!$inv) { flash('danger','Rechnung nicht gefunden.'); redirect('rechnungen.php'); }
    $pending = pending_serial_items($pdo, (int)$_GET['id']);
    ?>
    <h4>Seriennummern zuordnen – Rechnung <?= e($inv['invoice_number']) ?></h4>
    <?php if (!$pending): ?>
      <div class="alert alert-success">Alle Seriennummern sind bereits zugeordnet.</div>
      <a href="rechnungen.php?action=view&id=<?= (int)$_GET['id'] ?>" class="btn btn-secondary">Zur Rechnung</a>
    <?php else: ?>
    <form method="post" action="rechnungen.php?action=assign_serials" class="card p-4">
      <?= csrf_field() ?>
      <input type="hidden" name="invoice_id" value="<?= (int)$_GET['id'] ?>">
      <?php foreach ($pending as $item): ?>
        <?php
          $availStmt = $pdo->prepare("SELECT * FROM article_serials WHERE article_id=? AND status='lager' ORDER BY created_at");
          $availStmt->execute([$item['article_id']]);
          $available = $availStmt->fetchAll();
        ?>
        <div class="mb-4">
          <label class="form-label fw-bold"><?= e($item['article_name']) ?> — bitte <?= $item['remaining'] ?> Seriennummer(n) auswählen</label>
          <?php if (count($available) < $item['remaining']): ?>
            <div class="alert alert-danger">Nur <?= count($available) ?> Seriennummer(n) im Lager verfügbar, benötigt werden <?= $item['remaining'] ?>. Bitte zuerst im Lager-Modul Wareneingang buchen.</div>
          <?php endif; ?>
          <select name="serials[<?= $item['article_id'] ?>][]" class="form-select" multiple size="<?= min(8, max(3, count($available))) ?>" required>
            <?php foreach ($available as $s): ?>
              <option value="<?= $s['id'] ?>"><?= e($s['serial_number']) ?></option>
            <?php endforeach; ?>
          </select>
          <div class="form-text">Mehrfachauswahl: Strg/Cmd gedrückt halten.</div>
        </div>
      <?php endforeach; ?>
      <button class="btn btn-primary" type="submit">Zuordnen und Bestand buchen</button>
    </form>
    <?php endif; ?>
    <?php require_once __DIR__ . '/includes/footer.php'; exit;
}

// ---------- ANSICHT ----------
if ($action === 'view') {
    $stmt = $pdo->prepare('SELECT i.*, c.company, c.first_name, c.last_name, c.street, c.zip, c.city FROM invoices i JOIN customers c ON c.id=i.customer_id WHERE i.id=?');
    $stmt->execute([(int)$_GET['id']]);
    $invoice = $stmt->fetch();
    if (!$invoice) { flash('danger','Rechnung nicht gefunden.'); redirect('rechnungen.php'); }
    $items = $pdo->prepare('SELECT * FROM invoice_items WHERE invoice_id=? ORDER BY position');
    $items->execute([$invoice['id']]);
    $items = $items->fetchAll();
    $pending = pending_serial_items($pdo, $invoice['id']);

    // Zugeordnete Seriennummern je Artikel für die Anzeige laden
    $assignedSerials = [];
    $snStmt = $pdo->prepare('SELECT article_id, serial_number FROM article_serials WHERE invoice_id=? ORDER BY serial_number');
    $snStmt->execute([$invoice['id']]);
    foreach ($snStmt->fetchAll() as $row) {
        $assignedSerials[$row['article_id']][] = $row['serial_number'];
    }
    ?>
    <div class="d-flex justify-content-between mb-3">
      <h4>Rechnung <?= e($invoice['invoice_number']) ?> <?= status_badge($invoice['status']) ?></h4>
      <div>
        <a href="rechnung_pdf.php?id=<?= $invoice['id'] ?>" class="btn btn-outline-primary" target="_blank">PDF ansehen</a>
        <?php if ($invoice['status'] === 'entwurf'): ?>
        <a href="rechnungen.php?action=edit&id=<?= $invoice['id'] ?>" class="btn btn-outline-secondary">Bearbeiten</a>
        <?php endif; ?>
      </div>
    </div>
    <?php if ($pending): ?>
      <div class="alert alert-warning d-flex justify-content-between align-items-center">
        <span>Für diese Rechnung fehlen noch Seriennummern.</span>
        <a href="rechnungen.php?action=assign_serials&id=<?= $invoice['id'] ?>" class="btn btn-sm btn-warning">Jetzt zuordnen</a>
      </div>
    <?php endif; ?>
    <div class="card p-3 mb-3">
      <strong>Kunde:</strong> <?= e($invoice['company'] ?: trim($invoice['first_name'].' '.$invoice['last_name'])) ?><br>
      <?= e($invoice['street']) ?>, <?= e($invoice['zip'].' '.$invoice['city']) ?><br>
      <strong>Rechnungsdatum:</strong> <?= date('d.m.Y', strtotime($invoice['invoice_date'])) ?>
      <?php if ($invoice['due_date']): ?> — <strong>Fällig bis:</strong> <?= date('d.m.Y', strtotime($invoice['due_date'])) ?><?php endif; ?>
    </div>
    <div class="card p-3 mb-3">
      <table class="table">
        <thead><tr><th>Beschreibung</th><th class="text-end">Menge</th><th class="text-end">Einzelpreis</th><th class="text-end">MwSt.</th><th class="text-end">Gesamt</th></tr></thead>
        <tbody>
        <?php foreach ($items as $it): ?>
          <tr>
            <td>
              <?= e($it['description']) ?>
              <?php if ($it['article_id'] && !empty($assignedSerials[$it['article_id']])): ?>
                <div class="small text-muted">S/N: <?= e(implode(', ', $assignedSerials[$it['article_id']])) ?></div>
              <?php endif; ?>
            </td>
            <td class="text-end"><?= num($it['quantity']) ?></td>
            <td class="text-end"><?= money($it['unit_price']) ?></td>
            <td class="text-end"><?= num($it['tax_rate']) ?>%</td>
            <td class="text-end"><?= money($it['quantity']*$it['unit_price']) ?></td>
          </tr>
        <?php endforeach; ?>
        </tbody>
        <tfoot>
          <tr><td colspan="4" class="text-end">Netto</td><td class="text-end"><?= money($invoice['total_net']) ?></td></tr>
          <tr><td colspan="4" class="text-end">MwSt.</td><td class="text-end"><?= money($invoice['total_tax']) ?></td></tr>
          <tr><td colspan="4" class="text-end fw-bold">Gesamt</td><td class="text-end fw-bold"><?= money($invoice['total_gross']) ?></td></tr>
        </tfoot>
      </table>
      <?php if ($invoice['notes']): ?><p class="text-muted"><?= nl2br(e($invoice['notes'])) ?></p><?php endif; ?>
    </div>
    <form method="post" action="rechnungen.php?action=status" class="d-inline">
      <?= csrf_field() ?>
      <input type="hidden" name="id" value="<?= $invoice['id'] ?>">
      <div class="input-group" style="max-width:300px;">
        <select name="status" class="form-select">
          <?php foreach (['entwurf','versendet','bezahlt','ueberfaellig','storniert'] as $s): ?>
            <option value="<?= $s ?>" <?= $invoice['status']===$s?'selected':'' ?>><?= ucfirst($s) ?></option>
          <?php endforeach; ?>
        </select>
        <button class="btn btn-outline-primary" type="submit">Status ändern</button>
      </div>
    </form>
    <?php require_once __DIR__ . '/includes/footer.php'; exit;
}

// ---------- FORMULAR (neu/bearbeiten) ----------
if ($action === 'new' || $action === 'edit') {
    $invoice = ['id'=>0,'customer_id'=>'','invoice_date'=>date('Y-m-d'),'due_date'=>date('Y-m-d', strtotime('+14 days')),'status'=>'entwurf','notes'=>''];
    $items = [];
    if ($action === 'edit') {
        $stmt = $pdo->prepare('SELECT * FROM invoices WHERE id=?');
        $stmt->execute([(int)$_GET['id']]);
        $invoice = $stmt->fetch();
        if (!$invoice) { flash('danger','Rechnung nicht gefunden.'); redirect('rechnungen.php'); }
        if ($invoice['status'] !== 'entwurf') { flash('danger','Nur Entwürfe können bearbeitet werden.'); redirect('rechnungen.php?action=view&id='.$invoice['id']); }
        $itemStmt = $pdo->prepare('SELECT * FROM invoice_items WHERE invoice_id=? ORDER BY position');
        $itemStmt->execute([$invoice['id']]);
        $items = $itemStmt->fetchAll();
    }
    $customers = $pdo->query('SELECT id, company, first_name, last_name FROM customers ORDER BY company, last_name')->fetchAll();
    $articles = $pdo->query('SELECT id, name, sale_price, tax_rate FROM articles WHERE active=1 ORDER BY name')->fetchAll();

    $doc = $invoice;
    $docType = 'invoice';
    $dateField = 'invoice_date'; $dateLabel = 'Rechnungsdatum';
    $secondDateField = 'due_date'; $secondDateLabel = 'Fällig bis';
    $statuses = ['entwurf','versendet','bezahlt','ueberfaellig','storniert'];
    $saveUrl = 'rechnungen.php?action=save';
    $formTitle = $action === 'new' ? 'Neue Rechnung' : 'Rechnung bearbeiten';
    include __DIR__ . '/includes/document_form.php';
    require_once __DIR__ . '/includes/footer.php';
    exit;
}

// ---------- LISTE ----------
$stmt = $pdo->query('SELECT i.*, c.company, c.first_name, c.last_name FROM invoices i JOIN customers c ON c.id=i.customer_id ORDER BY i.created_at DESC');
$invoices = $stmt->fetchAll();
?>
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4>Rechnungen</h4>
  <a href="rechnungen.php?action=new" class="btn btn-primary"><i class="bi bi-plus"></i> Neue Rechnung</a>
</div>
<div class="card p-3">
<table class="table table-hover align-middle">
  <thead><tr><th>Nr.</th><th>Kunde</th><th>Datum</th><th class="text-end">Betrag</th><th>Status</th><th></th></tr></thead>
  <tbody>
  <?php foreach ($invoices as $i): ?>
    <tr>
      <td><a href="rechnungen.php?action=view&id=<?= $i['id'] ?>"><?= e($i['invoice_number']) ?></a></td>
      <td><?= e($i['company'] ?: trim($i['first_name'].' '.$i['last_name'])) ?></td>
      <td><?= date('d.m.Y', strtotime($i['invoice_date'])) ?></td>
      <td class="text-end"><?= money($i['total_gross']) ?></td>
      <td><?= status_badge($i['status']) ?></td>
      <td class="text-end">
        <?php if ($i['status']==='entwurf'): ?>
        <a href="rechnungen.php?action=delete&id=<?= $i['id'] ?>&token=<?= e(csrf_token()) ?>" class="btn btn-sm btn-outline-danger" onclick="return confirm('Rechnung wirklich löschen?')">Löschen</a>
        <?php endif; ?>
      </td>
    </tr>
  <?php endforeach; ?>
  </tbody>
</table>
</div>
<?php require_once __DIR__ . '/includes/footer.php'; ?>
