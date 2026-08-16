<?php
require_once $_SERVER['DOCUMENT_ROOT'] . '/includes/auth.php';
require_once ROOT_PATH . '/includes/functions.php';
require_once ROOT_PATH . '/includes/license.php';
require_login();
require_module_license('warenwirtschaft');
$pdo = db();
$action = $_GET['action'] ?? 'list';
require_permission('auftraege', in_array($action, ['status', 'to_invoice', 'delete'], true) ? 'write' : 'read');

// ---------- STATUS ÄNDERN ----------
if ($action === 'status' && $_SERVER['REQUEST_METHOD'] === 'POST') {
    csrf_check();
    $stmt = $pdo->prepare('UPDATE orders SET status=? WHERE id=?');
    $stmt->execute([$_POST['status'], (int)$_POST['id']]);
    flash('success', 'Status aktualisiert.');
    redirect('modules/warenwirtschaft/auftraege.php?action=view&id=' . (int)$_POST['id']);
}

// ---------- IN RECHNUNG UMWANDELN ----------
if ($action === 'to_invoice' && isset($_GET['id']) && hash_equals(csrf_token(), $_GET['token'] ?? '')) {
    $stmt = $pdo->prepare('SELECT * FROM orders WHERE id=?');
    $stmt->execute([(int)$_GET['id']]);
    $order = $stmt->fetch();
    if (!$order) { flash('danger','Auftrag nicht gefunden.'); redirect('modules/warenwirtschaft/auftraege.php'); }

    $pdo->beginTransaction();
    try {
        $result = create_invoice_from_order($pdo, $order);
        $pdo->prepare("UPDATE orders SET status='abgeschlossen' WHERE id=?")->execute([$order['id']]);
        $pdo->commit();
        if ($result['needs_serial_assignment']) {
            flash('success', "Rechnung {$result['invoice_number']} wurde erstellt. Bitte jetzt die Seriennummern der verkauften Geräte zuordnen.");
            redirect('modules/warenwirtschaft/rechnungen.php?action=assign_serials&id=' . $result['invoice_id']);
        }
        flash('success', "Rechnung {$result['invoice_number']} wurde erstellt (Lagerbestand wurde reduziert).");
        redirect('modules/warenwirtschaft/rechnungen.php?action=view&id=' . $result['invoice_id']);
    } catch (Exception $e) {
        $pdo->rollBack();
        flash('danger', 'Fehler: ' . $e->getMessage());
        redirect('modules/warenwirtschaft/auftraege.php?action=view&id=' . $order['id']);
    }
}

// ---------- LÖSCHEN ----------
if ($action === 'delete' && isset($_GET['id']) && hash_equals(csrf_token(), $_GET['token'] ?? '')) {
    $pdo->prepare('DELETE FROM orders WHERE id=?')->execute([(int)$_GET['id']]);
    flash('success', 'Auftrag gelöscht.');
    redirect('modules/warenwirtschaft/auftraege.php');
}

// ---------- AB HIER BEGINNT DIE HTML-AUSGABE ----------
$pageTitle = 'Aufträge';
require_once ROOT_PATH . '/includes/header.php';

// ---------- ANSICHT ----------
if ($action === 'view') {
    $stmt = $pdo->prepare('SELECT o.*, c.company, c.first_name, c.last_name, c.street, c.zip, c.city FROM orders o JOIN customers c ON c.id=o.customer_id WHERE o.id=?');
    $stmt->execute([(int)$_GET['id']]);
    $order = $stmt->fetch();
    if (!$order) { flash('danger','Auftrag nicht gefunden.'); redirect('modules/warenwirtschaft/auftraege.php'); }
    $items = $pdo->prepare('SELECT * FROM order_items WHERE order_id=? ORDER BY position');
    $items->execute([$order['id']]);
    $items = $items->fetchAll();

    $offerNumber = null;
    if ($order['offer_id']) {
        $offStmt = $pdo->prepare('SELECT offer_number FROM offers WHERE id=?');
        $offStmt->execute([$order['offer_id']]);
        $off = $offStmt->fetch();
        $offerNumber = $off['offer_number'] ?? null;
    }
    $invoicesStmt = $pdo->prepare('SELECT id, invoice_number, status FROM invoices WHERE order_id=? ORDER BY created_at');
    $invoicesStmt->execute([$order['id']]);
    $relatedInvoices = $invoicesStmt->fetchAll();
    ?>
    <div class="d-flex justify-content-between mb-3">
      <h4>Auftrag <?= e($order['order_number']) ?> <?= status_badge($order['status']) ?></h4>
      <div>
        <a href="auftrag_pdf.php?id=<?= $order['id'] ?>" class="btn btn-app-outline-primary" target="_blank">PDF ansehen</a>
        <?php if (!$relatedInvoices): ?>
        <a href="auftraege.php?action=to_invoice&id=<?= $order['id'] ?>&token=<?= e(csrf_token()) ?>" class="btn btn-app-success" onclick="return confirm('Rechnung aus diesem Auftrag erstellen? Der Lagerbestand wird reduziert.')">Rechnung erstellen</a>
        <?php endif; ?>
      </div>
    </div>
    <?php if ($offerNumber): ?>
      <div class="mb-3"><span class="text-muted">Entstanden aus Angebot</span> <a href="angebote.php?action=view&id=<?= $order['offer_id'] ?>"><?= e($offerNumber) ?></a></div>
    <?php endif; ?>
    <?php if ($relatedInvoices): ?>
      <div class="alert alert-app-info">
        Zu diesem Auftrag <?= count($relatedInvoices) > 1 ? 'wurden bereits Rechnungen' : 'wurde bereits eine Rechnung' ?> erstellt:
        <?php foreach ($relatedInvoices as $inv): ?>
          <a href="rechnungen.php?action=view&id=<?= $inv['id'] ?>" class="ms-1"><?= e($inv['invoice_number']) ?></a> <?= status_badge($inv['status']) ?>
        <?php endforeach; ?>
      </div>
    <?php endif; ?>
    <div class="card p-3 mb-3">
      <strong>Kunde:</strong> <?= e($order['company'] ?: trim($order['first_name'].' '.$order['last_name'])) ?><br>
      <?= e($order['street']) ?>, <?= e($order['zip'].' '.$order['city']) ?><br>
      <strong>Datum:</strong> <?= date('d.m.Y', strtotime($order['order_date'])) ?>
    </div>
    <div class="card p-3 mb-3">
      <table class="table">
        <thead><tr><th>Beschreibung</th><th class="text-end">Menge</th><th class="text-end">Einzelpreis</th><th class="text-end">MwSt.</th><th class="text-end">Gesamt</th></tr></thead>
        <tbody>
        <?php foreach ($items as $it): ?>
          <tr>
            <td><?= e($it['description']) ?></td>
            <td class="text-end"><?= num($it['quantity']) ?></td>
            <td class="text-end"><?= money($it['unit_price']) ?></td>
            <td class="text-end"><?= num($it['tax_rate']) ?>%</td>
            <td class="text-end"><?= money($it['quantity']*$it['unit_price']) ?></td>
          </tr>
        <?php endforeach; ?>
        </tbody>
        <tfoot>
          <tr><td colspan="4" class="text-end">Netto</td><td class="text-end"><?= money($order['total_net']) ?></td></tr>
          <tr><td colspan="4" class="text-end">MwSt.</td><td class="text-end"><?= money($order['total_tax']) ?></td></tr>
          <tr><td colspan="4" class="text-end fw-bold">Gesamt</td><td class="text-end fw-bold"><?= money($order['total_gross']) ?></td></tr>
        </tfoot>
      </table>
      <?php if ($order['notes']): ?><p class="text-muted"><?= nl2br(e($order['notes'])) ?></p><?php endif; ?>
    </div>
    <form method="post" action="auftraege.php?action=status" class="d-inline">
      <?= csrf_field() ?>
      <input type="hidden" name="id" value="<?= $order['id'] ?>">
      <div class="input-group" style="max-width:300px;">
        <select name="status" class="form-select">
          <?php foreach (['offen','in_bearbeitung','abgeschlossen','storniert'] as $s): ?>
            <option value="<?= $s ?>" <?= $order['status']===$s?'selected':'' ?>><?= ucfirst($s) ?></option>
          <?php endforeach; ?>
        </select>
        <button class="btn btn-app-outline-primary" type="submit">Status ändern</button>
      </div>
    </form>
    <?php require_once ROOT_PATH . '/includes/footer.php'; exit;
}

// ---------- LISTE ----------
$stmt = $pdo->query('SELECT o.*, c.company, c.first_name, c.last_name FROM orders o JOIN customers c ON c.id=o.customer_id ORDER BY o.created_at DESC');
$orders = $stmt->fetchAll();
?>
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4>Aufträge</h4>
</div>
<div class="card p-3">
<table class="table table-hover align-middle">
  <thead><tr><th>Nr.</th><th>Kunde</th><th>Datum</th><th class="text-end">Betrag</th><th>Status</th><th></th></tr></thead>
  <tbody>
  <?php foreach ($orders as $o): ?>
    <tr style="cursor:pointer;" onclick="window.location='auftraege.php?action=view&id=<?= $o['id'] ?>';">
      <td><?= e($o['order_number']) ?></td>
      <td><?= e($o['company'] ?: trim($o['first_name'].' '.$o['last_name'])) ?></td>
      <td><?= date('d.m.Y', strtotime($o['order_date'])) ?></td>
      <td class="text-end"><?= money($o['total_gross']) ?></td>
      <td><?= status_badge($o['status']) ?></td>
      <td class="text-end">
        <a href="auftraege.php?action=delete&id=<?= $o['id'] ?>&token=<?= e(csrf_token()) ?>" class="btn btn-sm btn-app-outline-danger" onclick="event.stopPropagation(); return confirm('Auftrag wirklich löschen?')">Löschen</a>
      </td>
    </tr>
  <?php endforeach; ?>
  </tbody>
</table>
</div>
<?php require_once ROOT_PATH . '/includes/footer.php'; ?>
