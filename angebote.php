<?php
require_once __DIR__ . '/includes/auth.php';
require_once __DIR__ . '/includes/functions.php';
require_login();
$pdo = db();
$action = $_GET['action'] ?? 'list';

function calc_totals(array $descriptions, array $quantities, array $prices, array $taxRates): array {
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
        redirect('angebote.php?action=' . ($id ? "edit&id=$id" : 'new'));
    }

    [$net, $tax, $gross] = calc_totals($descriptions, $quantities, $prices, $taxRates);

    $pdo->beginTransaction();
    try {
        if ($id) {
            $stmt = $pdo->prepare('UPDATE offers SET customer_id=?,offer_date=?,valid_until=?,status=?,notes=?,total_net=?,total_tax=?,total_gross=? WHERE id=?');
            $stmt->execute([$customerId, $_POST['offer_date'], $_POST['valid_until'] ?: null, $_POST['status'], trim($_POST['notes']), $net, $tax, $gross, $id]);
            $pdo->prepare('DELETE FROM offer_items WHERE offer_id=?')->execute([$id]);
            $offerId = $id;
        } else {
            $number = next_document_number('offer');
            $stmt = $pdo->prepare('INSERT INTO offers (offer_number,customer_id,offer_date,valid_until,status,notes,total_net,total_tax,total_gross,created_by) VALUES (?,?,?,?,?,?,?,?,?,?)');
            $stmt->execute([$number, $customerId, $_POST['offer_date'], $_POST['valid_until'] ?: null, $_POST['status'], trim($_POST['notes']), $net, $tax, $gross, current_user()['id']]);
            $offerId = $pdo->lastInsertId();
        }
        $pos = 0;
        $itemStmt = $pdo->prepare('INSERT INTO offer_items (offer_id,article_id,position,description,quantity,unit_price,tax_rate) VALUES (?,?,?,?,?,?,?)');
        foreach ($descriptions as $i => $desc) {
            if (trim($desc) === '') continue;
            $itemStmt->execute([
                $offerId,
                $articleIds[$i] ?: null,
                $pos++,
                trim($desc),
                (float)str_replace(',', '.', $quantities[$i]),
                (float)str_replace(',', '.', $prices[$i]),
                (float)str_replace(',', '.', $taxRates[$i]),
            ]);
        }
        $pdo->commit();
        flash('success', 'Angebot gespeichert.');
    } catch (Exception $e) {
        $pdo->rollBack();
        flash('danger', 'Fehler beim Speichern: ' . $e->getMessage());
    }
    redirect('angebote.php?action=view&id=' . $offerId);
}

// ---------- STATUS ÄNDERN ----------
if ($action === 'status' && $_SERVER['REQUEST_METHOD'] === 'POST') {
    csrf_check();
    $stmt = $pdo->prepare('UPDATE offers SET status=? WHERE id=?');
    $stmt->execute([$_POST['status'], (int)$_POST['id']]);
    flash('success', 'Status aktualisiert.');
    redirect('angebote.php?action=view&id=' . (int)$_POST['id']);
}

// ---------- IN RECHNUNG UMWANDELN ----------
if ($action === 'to_invoice' && isset($_GET['id']) && hash_equals(csrf_token(), $_GET['token'] ?? '')) {
    $stmt = $pdo->prepare('SELECT * FROM offers WHERE id=?');
    $stmt->execute([(int)$_GET['id']]);
    $offer = $stmt->fetch();
    if (!$offer) { flash('danger','Angebot nicht gefunden.'); redirect('angebote.php'); }

    $items = $pdo->prepare('SELECT * FROM offer_items WHERE offer_id=? ORDER BY position');
    $items->execute([$offer['id']]);
    $items = $items->fetchAll();

    $pdo->beginTransaction();
    try {
        $number = next_document_number('invoice');
        $stmt = $pdo->prepare('INSERT INTO invoices (invoice_number,offer_id,customer_id,invoice_date,due_date,status,notes,total_net,total_tax,total_gross,created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?)');
        $stmt->execute([$number, $offer['id'], $offer['customer_id'], date('Y-m-d'), date('Y-m-d', strtotime('+14 days')), 'entwurf', $offer['notes'], $offer['total_net'], $offer['total_tax'], $offer['total_gross'], current_user()['id']]);
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
        $pdo->prepare("UPDATE offers SET status='angenommen' WHERE id=?")->execute([$offer['id']]);
        $pdo->commit();
        if ($needsSerialAssignment) {
            flash('success', "Rechnung $number wurde erstellt. Bitte jetzt die Seriennummern der verkauften Geräte zuordnen.");
            redirect('rechnungen.php?action=assign_serials&id=' . $invoiceId);
        }
        flash('success', "Rechnung $number wurde erstellt (Lagerbestand wurde reduziert).");
        redirect('rechnungen.php?action=view&id=' . $invoiceId);
    } catch (Exception $e) {
        $pdo->rollBack();
        flash('danger', 'Fehler: ' . $e->getMessage());
        redirect('angebote.php?action=view&id=' . $offer['id']);
    }
}

// ---------- LÖSCHEN ----------
if ($action === 'delete' && isset($_GET['id']) && hash_equals(csrf_token(), $_GET['token'] ?? '')) {
    $pdo->prepare('DELETE FROM offers WHERE id=?')->execute([(int)$_GET['id']]);
    flash('success', 'Angebot gelöscht.');
    redirect('angebote.php');
}

// ---------- AB HIER BEGINNT DIE HTML-AUSGABE ----------
$pageTitle = 'Angebote';
require_once __DIR__ . '/includes/header.php';

// ---------- ANSICHT ----------
if ($action === 'view') {
    $stmt = $pdo->prepare('SELECT o.*, c.company, c.first_name, c.last_name, c.street, c.zip, c.city FROM offers o JOIN customers c ON c.id=o.customer_id WHERE o.id=?');
    $stmt->execute([(int)$_GET['id']]);
    $offer = $stmt->fetch();
    if (!$offer) { flash('danger','Angebot nicht gefunden.'); redirect('angebote.php'); }
    $items = $pdo->prepare('SELECT * FROM offer_items WHERE offer_id=? ORDER BY position');
    $items->execute([$offer['id']]);
    $items = $items->fetchAll();
    ?>
    <div class="d-flex justify-content-between mb-3">
      <h4>Angebot <?= e($offer['offer_number']) ?> <?= status_badge($offer['status']) ?></h4>
      <div>
        <a href="angebot_pdf.php?id=<?= $offer['id'] ?>" class="btn btn-outline-primary" target="_blank">PDF ansehen</a>
        <a href="angebote.php?action=edit&id=<?= $offer['id'] ?>" class="btn btn-outline-secondary">Bearbeiten</a>
        <a href="angebote.php?action=to_invoice&id=<?= $offer['id'] ?>&token=<?= e(csrf_token()) ?>" class="btn btn-success" onclick="return confirm('Rechnung aus diesem Angebot erstellen? Der Lagerbestand wird reduziert.')">Rechnung erstellen</a>
      </div>
    </div>
    <div class="card p-3 mb-3">
      <strong>Kunde:</strong> <?= e($offer['company'] ?: trim($offer['first_name'].' '.$offer['last_name'])) ?><br>
      <?= e($offer['street']) ?>, <?= e($offer['zip'].' '.$offer['city']) ?><br>
      <strong>Datum:</strong> <?= date('d.m.Y', strtotime($offer['offer_date'])) ?>
      <?php if ($offer['valid_until']): ?> — <strong>Gültig bis:</strong> <?= date('d.m.Y', strtotime($offer['valid_until'])) ?><?php endif; ?>
    </div>
    <div class="card p-3 mb-3">
      <table class="table">
        <thead><tr><th>Beschreibung</th><th class="text-end">Menge</th><th class="text-end">Einzelpreis</th><th class="text-end">MwSt.</th><th class="text-end">Gesamt</th><th></th></tr></thead>
        <tbody>
        <?php foreach ($items as $it): ?>
          <tr>
            <td><?= e($it['description']) ?></td>
            <td class="text-end"><?= num($it['quantity']) ?></td>
            <td class="text-end"><?= money($it['unit_price']) ?></td>
            <td class="text-end"><?= num($it['tax_rate']) ?>%</td>
            <td class="text-end"><?= money($it['quantity']*$it['unit_price']) ?></td>
            <td class="text-end">
              <?php if (!$it['article_id']): ?>
                <a href="artikel.php?action=new&from_offer_item=<?= $it['id'] ?>" class="btn btn-sm btn-outline-success">Als Artikel anlegen</a>
              <?php endif; ?>
            </td>
          </tr>
        <?php endforeach; ?>
        </tbody>
        <tfoot>
          <tr><td colspan="4" class="text-end">Netto</td><td class="text-end"><?= money($offer['total_net']) ?></td><td></td></tr>
          <tr><td colspan="4" class="text-end">MwSt.</td><td class="text-end"><?= money($offer['total_tax']) ?></td><td></td></tr>
          <tr><td colspan="4" class="text-end fw-bold">Gesamt</td><td class="text-end fw-bold"><?= money($offer['total_gross']) ?></td><td></td></tr>
        </tfoot>
      </table>
      <?php if ($offer['notes']): ?><p class="text-muted"><?= nl2br(e($offer['notes'])) ?></p><?php endif; ?>
    </div>
    <form method="post" action="angebote.php?action=status" class="d-inline">
      <?= csrf_field() ?>
      <input type="hidden" name="id" value="<?= $offer['id'] ?>">
      <div class="input-group" style="max-width:300px;">
        <select name="status" class="form-select">
          <?php foreach (['entwurf','versendet','angenommen','abgelehnt'] as $s): ?>
            <option value="<?= $s ?>" <?= $offer['status']===$s?'selected':'' ?>><?= ucfirst($s) ?></option>
          <?php endforeach; ?>
        </select>
        <button class="btn btn-outline-primary" type="submit">Status ändern</button>
      </div>
    </form>
    <?php require_once __DIR__ . '/includes/footer.php'; exit;
}

// ---------- FORMULAR (neu/bearbeiten) ----------
if ($action === 'new' || $action === 'edit') {
    $offer = ['id'=>0,'customer_id'=>'','offer_date'=>date('Y-m-d'),'valid_until'=>date('Y-m-d', strtotime('+30 days')),'status'=>'entwurf','notes'=>''];
    $items = [];
    if ($action === 'edit') {
        $stmt = $pdo->prepare('SELECT * FROM offers WHERE id=?');
        $stmt->execute([(int)$_GET['id']]);
        $offer = $stmt->fetch();
        if (!$offer) { flash('danger','Angebot nicht gefunden.'); redirect('angebote.php'); }
        $itemStmt = $pdo->prepare('SELECT * FROM offer_items WHERE offer_id=? ORDER BY position');
        $itemStmt->execute([$offer['id']]);
        $items = $itemStmt->fetchAll();
    }
    $customers = $pdo->query('SELECT id, company, first_name, last_name FROM customers ORDER BY company, last_name')->fetchAll();
    $articles = $pdo->query('SELECT id, name, sale_price, tax_rate FROM articles WHERE active=1 ORDER BY name')->fetchAll();

    $doc = $offer;
    $docType = 'offer';
    $dateField = 'offer_date'; $dateLabel = 'Angebotsdatum';
    $secondDateField = 'valid_until'; $secondDateLabel = 'Gültig bis';
    $statuses = ['entwurf','versendet','angenommen','abgelehnt'];
    $saveUrl = 'angebote.php?action=save';
    $formTitle = $action === 'new' ? 'Neues Angebot' : 'Angebot bearbeiten';
    include __DIR__ . '/includes/document_form.php';
    require_once __DIR__ . '/includes/footer.php';
    exit;
}

// ---------- LISTE ----------
$stmt = $pdo->query('SELECT o.*, c.company, c.first_name, c.last_name FROM offers o JOIN customers c ON c.id=o.customer_id ORDER BY o.created_at DESC');
$offers = $stmt->fetchAll();
?>
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4>Angebote</h4>
  <a href="angebote.php?action=new" class="btn btn-primary"><i class="bi bi-plus"></i> Neues Angebot</a>
</div>
<div class="card p-3">
<table class="table table-hover align-middle">
  <thead><tr><th>Nr.</th><th>Kunde</th><th>Datum</th><th class="text-end">Betrag</th><th>Status</th><th></th></tr></thead>
  <tbody>
  <?php foreach ($offers as $o): ?>
    <tr class="<?= !$o['active'] ? 'text-muted' : '' ?>" style="cursor:pointer;" onclick="window.location='angebote.php?action=edit&id=<?= $o['id'] ?>';">
      <td><?= e($o['offer_number']) ?></a></td>
      <td><?= e($o['company'] ?: trim($o['first_name'].' '.$o['last_name'])) ?></td>
      <td><?= date('d.m.Y', strtotime($o['offer_date'])) ?></td>
      <td class="text-end"><?= money($o['total_gross']) ?></td>
      <td><?= status_badge($o['status']) ?></td>
      <td class="text-end">
        <a href="angebote.php?action=to_invoice&id=<?= $o['id'] ?>&token=<?= e(csrf_token()) ?>" class="btn btn-sm btn-success" onclick="return confirm('Rechnung aus diesem Angebot erstellen? Der Lagerbestand wird reduziert.')">Rechnung erstellen</a>
        <a href="angebote.php?action=delete&id=<?= $o['id'] ?>&token=<?= e(csrf_token()) ?>" class="btn btn-sm btn-outline-danger" onclick="return confirm('Angebot wirklich löschen?')">Löschen</a>
      </td>
    </tr>
  <?php endforeach; ?>
  </tbody>
</table>
</div>
<?php require_once __DIR__ . '/includes/footer.php'; ?>
