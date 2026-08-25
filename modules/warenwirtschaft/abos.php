<?php
require_once $_SERVER['DOCUMENT_ROOT'] . '/includes/auth.php';
require_once ROOT_PATH . '/includes/functions.php';
require_once ROOT_PATH . '/includes/license.php';
$self = preg_replace('/^' . preg_quote($_SERVER['DOCUMENT_ROOT'], '/') . '/', '', __DIR__) . '/' .basename($_SERVER['SCRIPT_NAME']);
require_login();
require_module_license('warenwirtschaft');
$pdo = db();
$action = $_GET['action'] ?? 'list';
require_permission('abos', in_array($action, ['cancel', 'generate_drafts'], true) ? 'write' : 'read');

// ---------- KÜNDIGUNG ERFASSEN ----------
if ($action === 'cancel' && $_SERVER['REQUEST_METHOD'] === 'POST') {
    csrf_check();
    $id = (int)$_POST['id'];
    $stmt = $pdo->prepare("SELECT * FROM subscriptions WHERE id=? AND status='aktiv'");
    $stmt->execute([$id]);
    $sub = $stmt->fetch();
    if (!$sub) { flash('danger', 'Abo nicht gefunden oder bereits gekündigt.'); redirect($self); }

    $requestDate = $_POST['cancellation_requested_date'] ?: date('Y-m-d');
    $calc = calculate_subscription_cancellation($sub, $requestDate);
    $stmt = $pdo->prepare("UPDATE subscriptions SET status='gekuendigt', cancellation_requested_date=?, cancellation_effective_date=? WHERE id=?");
    $stmt->execute([$calc['cancellation_requested_date'], $calc['cancellation_effective_date'], $id]);
    flash('success', 'Kündigung erfasst. Das Abo endet zum ' . date('d.m.Y', strtotime($calc['cancellation_effective_date'])) . '.');
    redirect($self . '?action=view&id=' . $id);
}

// ---------- ENTWÜRFE JETZT ERZEUGEN ----------
if ($action === 'generate_drafts' && isset($_GET['token']) && hash_equals(csrf_token(), $_GET['token'])) {
    $created = generate_subscription_invoice_drafts($pdo);
    if ($created) {
        flash('success', count($created) . ' Entwurfs-Rechnung(en) erzeugt: ' . implode(', ', array_map(fn($c) => $c['invoice_number'], $created)) . '. Bitte prüfen und freigeben.');
    } else {
        flash('success', 'Keine fälligen Abo-Rechnungen zu erzeugen.');
    }
    redirect($self);
}

// ---------- AB HIER BEGINNT DIE HTML-AUSGABE ----------
$pageTitle = 'Abonnements';
require_once ROOT_PATH . '/includes/header.php';

$subStatusBadge = function (string $status): string {
    $map = ['aktiv' => 'success', 'gekuendigt' => 'warning', 'beendet' => 'secondary'];
    $labels = ['aktiv' => 'Aktiv', 'gekuendigt' => 'Gekündigt', 'beendet' => 'Beendet'];
    return '<span class="badge text-bg-' . ($map[$status] ?? 'secondary') . '">' . ($labels[$status] ?? ucfirst($status)) . '</span>';
};

// ---------- ANSICHT ----------
if ($action === 'view') {
    $stmt = $pdo->prepare('SELECT s.*, c.company, c.first_name, c.last_name, a.name AS article_name, a.sku
                            FROM subscriptions s
                            JOIN customers c ON c.id = s.customer_id
                            JOIN articles a ON a.id = s.article_id
                            WHERE s.id = ?');
    $stmt->execute([(int)$_GET['id']]);
    $sub = $stmt->fetch();
    if (!$sub) { flash('danger', 'Abo nicht gefunden.'); redirect($self); }

    $invStmt = $pdo->prepare("SELECT id, invoice_number, status, invoice_date, period_start, period_end, total_gross
                               FROM invoices WHERE subscription_id=? ORDER BY period_start, id");
    $invStmt->execute([$sub['id']]);
    $relatedInvoices = $invStmt->fetchAll();
    ?>
    <div class="d-flex justify-content-between mb-3">
      <h4><?= e($sub['article_name']) ?> <?= $subStatusBadge($sub['status']) ?></h4>
      <a href="abos.php" class="btn btn-app-outline-secondary">Zurück zur Liste</a>
    </div>
    <div class="card p-3 mb-3">
      <strong>Kunde:</strong> <?= e($sub['company'] ?: trim($sub['first_name'].' '.$sub['last_name'])) ?><br>
      <strong>Artikel:</strong> <?= e($sub['article_name']) ?> (<?= e($sub['sku']) ?>)<br>
      <strong>Abrechnung:</strong> <?= $sub['billing_cycle'] === 'jaehrlich' ? 'Jährlich' : 'Monatlich' ?>, <?= money($sub['price']) ?> je Zyklus<br>
      <strong>Start:</strong> <?= date('d.m.Y', strtotime($sub['start_date'])) ?><br>
      <?php if ($sub['status'] === 'aktiv'): ?>
        <strong>Nächste Abrechnung:</strong> <?= date('d.m.Y', strtotime($sub['next_billing_date'])) ?><br>
      <?php endif; ?>
      <?php if ($sub['min_runtime_months']): ?>
        <strong>Mindestlaufzeit:</strong> <?= (int)$sub['min_runtime_months'] ?> Monate (frühestes Vertragsende: <?= date('d.m.Y', strtotime($sub['earliest_cancellation_date'])) ?>)<br>
      <?php endif; ?>
      <?php if ($sub['notice_period_days']): ?>
        <strong>Kündigungsfrist:</strong> <?= (int)$sub['notice_period_days'] ?> Tage<br>
      <?php endif; ?>
      <?php if ($sub['status'] === 'gekuendigt'): ?>
        <strong>Gekündigt am:</strong> <?= date('d.m.Y', strtotime($sub['cancellation_requested_date'])) ?>,
        <strong>Vertragsende:</strong> <?= date('d.m.Y', strtotime($sub['cancellation_effective_date'])) ?><br>
      <?php elseif ($sub['status'] === 'beendet'): ?>
        <strong>Beendet zum:</strong> <?= date('d.m.Y', strtotime($sub['end_date'])) ?><br>
      <?php endif; ?>
    </div>

    <?php if ($sub['status'] === 'aktiv' && has_permission('abos', 'write')): ?>
    <div class="card p-3 mb-3">
      <h5>Kündigung erfassen</h5>
      <form method="post" action="abos.php?action=cancel" class="row g-3 align-items-end">
        <?= csrf_field() ?>
        <input type="hidden" name="id" value="<?= $sub['id'] ?>">
        <div class="col-md-4">
          <label class="form-label">Kündigungseingang</label>
          <input type="date" name="cancellation_requested_date" class="form-control" value="<?= date('Y-m-d') ?>">
        </div>
        <div class="col-md-4">
          <button type="submit" class="btn btn-app-outline-danger" onclick="return confirm('Kündigung für dieses Abo erfassen?')">Kündigung erfassen</button>
        </div>
      </form>
      <div class="form-text mt-2">Das Vertragsende wird automatisch unter Berücksichtigung von Mindestlaufzeit und Kündigungsfrist auf den nächsten regulären Abrechnungstermin berechnet.</div>
    </div>
    <?php endif; ?>

    <div class="card p-3 mb-3">
      <h5>Zugehörige Rechnungen</h5>
      <?php if (!$relatedInvoices): ?>
        <p class="text-muted mb-0">Noch keine Rechnungen zu diesem Abo.</p>
      <?php else: ?>
      <table class="table table-hover align-middle mb-0">
        <thead><tr><th>Nr.</th><th>Zeitraum</th><th class="text-end">Betrag</th><th>Status</th></tr></thead>
        <tbody>
        <?php foreach ($relatedInvoices as $inv): ?>
          <tr style="cursor:pointer;" onclick="window.location='rechnungen.php?action=view&id=<?= $inv['id'] ?>';">
            <td><?= e($inv['invoice_number']) ?></td>
            <td><?= $inv['period_start'] ? date('d.m.Y', strtotime($inv['period_start'])) . ' – ' . date('d.m.Y', strtotime($inv['period_end'])) : '—' ?></td>
            <td class="text-end"><?= money($inv['total_gross']) ?></td>
            <td><?= status_badge($inv['status']) ?></td>
          </tr>
        <?php endforeach; ?>
        </tbody>
      </table>
      <?php endif; ?>
    </div>
    <?php require_once ROOT_PATH . '/includes/footer.php'; exit;
}

// ---------- LISTE ----------
$stmt = $pdo->query('SELECT s.*, c.company, c.first_name, c.last_name, a.name AS article_name
                      FROM subscriptions s
                      JOIN customers c ON c.id = s.customer_id
                      JOIN articles a ON a.id = s.article_id
                      ORDER BY FIELD(s.status,\'aktiv\',\'gekuendigt\',\'beendet\'), s.next_billing_date');
$subscriptions = $stmt->fetchAll();
?>
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4>Abonnements</h4>
  <?php if (has_permission('abos', 'write')): ?>
  <a href="abos.php?action=generate_drafts&token=<?= e(csrf_token()) ?>" class="btn btn-app-primary" onclick="return confirm('Für alle fälligen Abos jetzt Entwurfs-Rechnungen erzeugen?')">Fällige Entwürfe jetzt erzeugen</a>
  <?php endif; ?>
</div>
<div class="card p-3">
<table class="table table-hover align-middle">
  <thead><tr><th>Kunde</th><th>Artikel</th><th>Zyklus</th><th class="text-end">Preis</th><th>Nächste Abrechnung</th><th>Status</th></tr></thead>
  <tbody>
  <?php foreach ($subscriptions as $s): ?>
    <tr style="cursor:pointer;" onclick="window.location='abos.php?action=view&id=<?= $s['id'] ?>';">
      <td><?= e($s['company'] ?: trim($s['first_name'].' '.$s['last_name'])) ?></td>
      <td><?= e($s['article_name']) ?></td>
      <td><?= $s['billing_cycle'] === 'jaehrlich' ? 'Jährlich' : 'Monatlich' ?></td>
      <td class="text-end"><?= money($s['price']) ?></td>
      <td><?= $s['status'] === 'aktiv' ? date('d.m.Y', strtotime($s['next_billing_date'])) : '—' ?></td>
      <td><?= $subStatusBadge($s['status']) ?></td>
    </tr>
  <?php endforeach; ?>
  <?php if (!$subscriptions): ?>
    <tr><td colspan="6" class="text-muted">Noch keine Abonnements vorhanden.</td></tr>
  <?php endif; ?>
  </tbody>
</table>
</div>
<?php require_once ROOT_PATH . '/includes/footer.php'; ?>
