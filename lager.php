<?php
$pageTitle = 'Lager';
require_once __DIR__ . '/includes/header.php';
$pdo = db();
$action = $_GET['action'] ?? 'list';

if ($_SERVER['REQUEST_METHOD'] === 'POST' && $action === 'korrektur') {
    csrf_check();
    $articleId = (int)$_POST['article_id'];
    $newQty = (float)str_replace(',', '.', $_POST['new_qty']);
    $note = trim($_POST['note']) ?: 'Manuelle Korrektur';
    $stmt = $pdo->prepare('SELECT stock_qty FROM articles WHERE id=?');
    $stmt->execute([$articleId]);
    $current = $stmt->fetch();
    if ($current) {
        $delta = $newQty - (float)$current['stock_qty'];
        if ($delta != 0) {
            adjust_stock($articleId, $delta, 'korrektur', 'manual', null, $note);
        }
        flash('success', 'Bestand korrigiert.');
    }
    redirect('lager.php');
}

if ($action === 'einlagern' && $_SERVER['REQUEST_METHOD'] === 'POST') {
    csrf_check();
    $articleId = (int)$_POST['article_id'];
    $qty = (float)str_replace(',', '.', $_POST['qty']);
    $note = trim($_POST['note']) ?: 'Wareneingang';
    if ($qty > 0) {
        adjust_stock($articleId, $qty, 'einlagerung', 'manual', null, $note);
        flash('success', 'Wareneingang gebucht.');
    }
    redirect('lager.php');
}

$articles = $pdo->query('SELECT id, name, sku, stock_qty, min_stock, unit FROM articles WHERE active=1 AND track_stock=1 ORDER BY name')->fetchAll();
$movements = $pdo->query('SELECT sm.*, a.name AS article_name, u.full_name FROM stock_movements sm
                           JOIN articles a ON a.id=sm.article_id
                           LEFT JOIN users u ON u.id=sm.created_by
                           ORDER BY sm.created_at DESC LIMIT 100')->fetchAll();
?>
<h4>Lagerverwaltung</h4>

<div class="row g-3 mb-4">
  <div class="col-md-6">
    <div class="card p-3">
      <h6>Wareneingang buchen</h6>
      <form method="post" action="lager.php?action=einlagern">
        <?= csrf_field() ?>
        <div class="mb-2">
          <select name="article_id" class="form-select" required>
            <option value="">Artikel wählen…</option>
            <?php foreach ($articles as $a): ?>
              <option value="<?= $a['id'] ?>"><?= e($a['name']) ?> (<?= e($a['sku']) ?>)</option>
            <?php endforeach; ?>
          </select>
        </div>
        <div class="row g-2">
          <div class="col-6"><input type="text" name="qty" class="form-control" placeholder="Menge" required></div>
          <div class="col-6"><input type="text" name="note" class="form-control" placeholder="Notiz (optional)"></div>
        </div>
        <button class="btn btn-success mt-2" type="submit">Einlagern</button>
      </form>
    </div>
  </div>
  <div class="col-md-6">
    <div class="card p-3">
      <h6>Bestand korrigieren (Inventur)</h6>
      <form method="post" action="lager.php?action=korrektur">
        <?= csrf_field() ?>
        <div class="mb-2">
          <select name="article_id" class="form-select" required>
            <option value="">Artikel wählen…</option>
            <?php foreach ($articles as $a): ?>
              <option value="<?= $a['id'] ?>" data-current="<?= num($a['stock_qty']) ?>"><?= e($a['name']) ?> — aktuell: <?= num($a['stock_qty']) ?> <?= e($a['unit']) ?></option>
            <?php endforeach; ?>
          </select>
        </div>
        <div class="row g-2">
          <div class="col-6"><input type="text" name="new_qty" class="form-control" placeholder="Neuer Ist-Bestand" required></div>
          <div class="col-6"><input type="text" name="note" class="form-control" placeholder="Notiz (optional)"></div>
        </div>
        <button class="btn btn-warning mt-2" type="submit">Korrektur speichern</button>
      </form>
    </div>
  </div>
</div>

<div class="card p-3">
  <h6>Letzte Lagerbewegungen</h6>
  <table class="table table-sm">
    <thead><tr><th>Datum</th><th>Artikel</th><th>Typ</th><th class="text-end">Menge</th><th>Notiz</th><th>Benutzer</th></tr></thead>
    <tbody>
    <?php foreach ($movements as $m): ?>
      <tr>
        <td><?= date('d.m.Y H:i', strtotime($m['created_at'])) ?></td>
        <td><?= e($m['article_name']) ?></td>
        <td><?= e(ucfirst($m['type'])) ?></td>
        <td class="text-end <?= $m['quantity'] < 0 ? 'text-danger' : 'text-success' ?>"><?= ($m['quantity']>0?'+':'').num($m['quantity']) ?></td>
        <td><?= e($m['note']) ?></td>
        <td><?= e($m['full_name'] ?? '—') ?></td>
      </tr>
    <?php endforeach; ?>
    </tbody>
  </table>
</div>
<?php require_once __DIR__ . '/includes/footer.php'; ?>
