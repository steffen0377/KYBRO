<?php
$pageTitle = 'Dashboard';
require_once __DIR__ . '/includes/header.php';

$pdo = db();
$articleCount = $pdo->query('SELECT COUNT(*) c FROM articles WHERE active=1')->fetch()['c'];
$customerCount = $pdo->query('SELECT COUNT(*) c FROM customers')->fetch()['c'];
$lowStock = $pdo->query('SELECT * FROM articles WHERE active=1 AND track_stock=1 AND stock_qty <= min_stock ORDER BY stock_qty ASC LIMIT 10')->fetchAll();
$openOffers = $pdo->query("SELECT COUNT(*) c FROM offers WHERE status IN ('entwurf','versendet')")->fetch()['c'];
$openInvoices = $pdo->query("SELECT COUNT(*) c, COALESCE(SUM(total_gross),0) s FROM invoices WHERE status IN ('entwurf','versendet','ueberfaellig')")->fetch();
$recentInvoices = $pdo->query('SELECT i.*, c.company, c.first_name, c.last_name FROM invoices i JOIN customers c ON c.id=i.customer_id ORDER BY i.created_at DESC LIMIT 5')->fetchAll();
?>

<div class="row g-3 mb-4">
  <div class="col-md-3"><div class="card p-3"><div class="text-muted small">Artikel aktiv</div><div class="fs-3 fw-bold"><?= $articleCount ?></div></div></div>
  <div class="col-md-3"><div class="card p-3"><div class="text-muted small">Kunden</div><div class="fs-3 fw-bold"><?= $customerCount ?></div></div></div>
  <div class="col-md-3"><div class="card p-3"><div class="text-muted small">Offene Angebote</div><div class="fs-3 fw-bold"><?= $openOffers ?></div></div></div>
  <div class="col-md-3"><div class="card p-3"><div class="text-muted small">Offene Rechnungen</div><div class="fs-3 fw-bold"><?= $openInvoices['c'] ?></div><div class="text-muted small"><?= money((float)$openInvoices['s']) ?></div></div></div>
</div>

<div class="row g-3">
  <div class="col-md-6">
    <div class="card p-3">
      <h6>⚠️ Niedriger Lagerbestand</h6>
      <?php if (!$lowStock): ?>
        <p class="text-muted mb-0">Alles im grünen Bereich.</p>
      <?php else: ?>
        <table class="table table-hover mb-0">
          <thead><tr><th>Artikel</th><th class="text-end">Bestand</th><th class="text-end">Mindestbestand</th></tr></thead>
          <tbody>
          <?php foreach ($lowStock as $a): ?>
            <tr class="<?= !$a['active'] ? 'text-muted' : '' ?>" style="cursor:pointer;" onclick="window.location='<?= APP_URL ?>/modules/stammdaten/artikel.php?action=edit&id=<?= $a['id'] ?>';">
              <td><?= e($a['name']) ?></a></td>
              <td class="text-end low-stock"><?= num($a['stock_qty']) ?></td>
              <td class="text-end"><?= num($a['min_stock']) ?></td>
            </tr>
          <?php endforeach; ?>
          </tbody>
        </table>
      <?php endif; ?>
    </div>
  </div>
  <div class="col-md-6">
    <div class="card p-3">
      <h6>🧾 Letzte Rechnungen</h6>
      <?php if (!$recentInvoices): ?>
        <p class="text-muted mb-0">Noch keine Rechnungen vorhanden.</p>
      <?php else: ?>
        <table class="table table-hover mb-0">
          <thead><tr><th>Nr.</th><th>Kunde</th><th class="text-end">Betrag</th><th>Status</th></tr></thead>
          <tbody>
          <?php foreach ($recentInvoices as $i): ?>
            <tr class="<?= !$i['active'] ? 'text-muted' : '' ?>" style="cursor:pointer;" onclick="window.location='<?= APP_URL ?>/modules/warenwirtschaft/rechnungen.php?action=view&id=<?= $i['id'] ?>';">
              <td><?= e($i['invoice_number']) ?></a></td>
              <td><?= e($i['company'] ?: trim($i['first_name'].' '.$i['last_name'])) ?></td>
              <td class="text-end"><?= money($i['total_gross']) ?></td>
              <td><?= status_badge($i['status']) ?></td>
            </tr>
          <?php endforeach; ?>
          </tbody>
        </table>
      <?php endif; ?>
    </div>
  </div>
</div>

<?php require_once __DIR__ . '/includes/footer.php'; ?>
