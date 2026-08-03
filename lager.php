<?php
$pageTitle = 'Lager';
$pdo = db();
$action = $_GET['action'] ?? 'list';

// ---------- Bestandskorrektur (nur für nicht-seriennummerpflichtige Artikel) ----------
if ($_SERVER['REQUEST_METHOD'] === 'POST' && $action === 'korrektur') {
    csrf_check();
    $articleId = (int)$_POST['article_id'];
    $newQty = (float)str_replace(',', '.', $_POST['new_qty']);
    $note = trim($_POST['note']) ?: 'Manuelle Korrektur';
    $stmt = $pdo->prepare('SELECT stock_qty, track_serials FROM articles WHERE id=?');
    $stmt->execute([$articleId]);
    $current = $stmt->fetch();
    if ($current && !$current['track_serials']) {
        $delta = $newQty - (float)$current['stock_qty'];
        if ($delta != 0) {
            adjust_stock($articleId, $delta, 'korrektur', 'manual', null, $note);
        }
        flash('success', 'Bestand korrigiert.');
    } elseif ($current) {
        flash('danger', 'Für Artikel mit Seriennummern bitte über die Seriennummern-Verwaltung korrigieren.');
    }
    redirect('lager.php');
}

// ---------- Wareneingang ohne Seriennummern ----------
if ($action === 'einlagern' && $_SERVER['REQUEST_METHOD'] === 'POST') {
    csrf_check();
    $articleId = (int)$_POST['article_id'];
    $qty = (float)str_replace(',', '.', $_POST['qty']);
    $note = trim($_POST['note']) ?: 'Wareneingang';
    $stmt = $pdo->prepare('SELECT track_serials FROM articles WHERE id=?');
    $stmt->execute([$articleId]);
    $art = $stmt->fetch();
    if ($art && $art['track_serials']) {
        flash('danger', 'Dieser Artikel benötigt Seriennummern – bitte das Formular "Wareneingang mit Seriennummern" nutzen.');
    } elseif ($qty > 0) {
        adjust_stock($articleId, $qty, 'einlagerung', 'manual', null, $note);
        flash('success', 'Wareneingang gebucht.');
    }
    redirect('lager.php');
}

// ---------- Wareneingang MIT Seriennummern ----------
if ($action === 'einlagern_seriell' && $_SERVER['REQUEST_METHOD'] === 'POST') {
    csrf_check();
    $articleId = (int)$_POST['article_id'];
    $note = trim($_POST['note']) ?: 'Wareneingang';
    $lines = preg_split('/\r\n|\r|\n/', trim($_POST['serials'] ?? ''));
    $serials = array_values(array_unique(array_filter(array_map('trim', $lines))));

    if (!$serials) {
        flash('danger', 'Bitte mindestens eine Seriennummer angeben (eine pro Zeile).');
        redirect('lager.php');
    }

    $pdo->beginTransaction();
    try {
        $check = $pdo->prepare('SELECT COUNT(*) c FROM article_serials WHERE article_id=? AND serial_number=?');
        $insert = $pdo->prepare('INSERT INTO article_serials (article_id, serial_number, status, note) VALUES (?,?,\'lager\',?)');
        $duplicates = [];
        foreach ($serials as $sn) {
            $check->execute([$articleId, $sn]);
            if ($check->fetch()['c'] > 0) {
                $duplicates[] = $sn;
                continue;
            }
            $insert->execute([$articleId, $sn, $note]);
        }
        $addedCount = count($serials) - count($duplicates);
        if ($addedCount > 0) {
            adjust_stock($articleId, $addedCount, 'einlagerung', 'manual', null, $note);
        }
        $pdo->commit();
        if ($duplicates) {
            flash('danger', 'Bereits vorhandene Seriennummern übersprungen: ' . e(implode(', ', $duplicates)));
        }
        if ($addedCount > 0) {
            flash('success', "$addedCount Seriennummer(n) eingelagert.");
        }
    } catch (Exception $e) {
        $pdo->rollBack();
        flash('danger', 'Fehler: ' . $e->getMessage());
    }
    redirect('lager.php');
}

// ---------- Einzelne Seriennummer als defekt markieren ----------
if ($action === 'seriennummer_defekt' && isset($_GET['id']) && hash_equals(csrf_token(), $_GET['token'] ?? '')) {
    $stmt = $pdo->prepare("SELECT * FROM article_serials WHERE id=? AND status='lager'");
    $stmt->execute([(int)$_GET['id']]);
    $serial = $stmt->fetch();
    if ($serial) {
        $pdo->prepare("UPDATE article_serials SET status='defekt' WHERE id=?")->execute([$serial['id']]);
        adjust_stock((int)$serial['article_id'], -1, 'korrektur', 'manual', null, 'Als defekt markiert: ' . $serial['serial_number']);
        flash('success', 'Seriennummer als defekt markiert und Bestand angepasst.');
    } else {
        flash('danger', 'Seriennummer nicht gefunden oder bereits verkauft/defekt.');
    }
    redirect('lager.php?view_serials=' . (int)($_GET['article_id'] ?? 0));
}

// ---------- Fälschlich erfasste Seriennummer wieder entfernen ----------
if ($action === 'seriennummer_entfernen' && isset($_GET['id']) && hash_equals(csrf_token(), $_GET['token'] ?? '')) {
    $stmt = $pdo->prepare("SELECT * FROM article_serials WHERE id=? AND status='lager'");
    $stmt->execute([(int)$_GET['id']]);
    $serial = $stmt->fetch();
    if ($serial) {
        $pdo->prepare('DELETE FROM article_serials WHERE id=?')->execute([$serial['id']]);
        adjust_stock((int)$serial['article_id'], -1, 'korrektur', 'manual', null, 'Fälschlich erfasst, entfernt: ' . $serial['serial_number']);
        flash('success', 'Seriennummer entfernt und Bestand angepasst.');
    } else {
        flash('danger', 'Seriennummer nicht gefunden oder bereits verkauft/defekt.');
    }
    redirect('lager.php?view_serials=' . (int)($_GET['article_id'] ?? 0));
}

$articles = $pdo->query('SELECT id, name, sku, stock_qty, min_stock, unit, track_serials FROM articles WHERE active=1 AND track_stock=1 ORDER BY name')->fetchAll();
$plainArticles = array_values(array_filter($articles, fn($a) => !$a['track_serials']));
$serialArticles = array_values(array_filter($articles, fn($a) => $a['track_serials']));
$movements = $pdo->query('SELECT sm.*, a.name AS article_name, u.full_name FROM stock_movements sm
                           JOIN articles a ON a.id=sm.article_id
                           LEFT JOIN users u ON u.id=sm.created_by
                           ORDER BY sm.created_at DESC LIMIT 100')->fetchAll();

$viewSerialsArticleId = (int)($_GET['view_serials'] ?? 0);
$serialsOfArticle = [];
if ($viewSerialsArticleId) {
    $stmt = $pdo->prepare('SELECT * FROM article_serials WHERE article_id=? ORDER BY status, created_at DESC');
    $stmt->execute([$viewSerialsArticleId]);
    $serialsOfArticle = $stmt->fetchAll();
}

require_once __DIR__ . '/includes/header.php';
?>
<h4>Lagerverwaltung</h4>

<div class="row g-3 mb-4">
  <div class="col-md-6">
    <div class="card p-3">
      <h6>Wareneingang buchen (ohne Seriennummer)</h6>
      <?php if (!$plainArticles): ?>
        <p class="text-muted mb-0">Keine passenden Artikel vorhanden.</p>
      <?php else: ?>
      <form method="post" action="lager.php?action=einlagern">
        <?= csrf_field() ?>
        <div class="mb-2">
          <select name="article_id" class="form-select" required>
            <option value="">Artikel wählen…</option>
            <?php foreach ($plainArticles as $a): ?>
              <option value="<?= $a['id'] ?>"><?= e($a['name']) ?> (<?= e($a['sku']) ?>)</option>
            <?php endforeach; ?>
          </select>
        </div>
        <div class="row g-2">
          <div class="col-6"><input type="text" name="qty" class="form-control" placeholder="Menge" required></div>
          <div class="col-6"><input type="text" name="note" class="form-control" placeholder="Notiz (optional)"></div>
        </div>
        <button class="btn btn-app-success mt-2" type="submit">Einlagern</button>
      </form>
      <?php endif; ?>
    </div>
  </div>
  <div class="col-md-6">
    <div class="card p-3">
      <h6>Bestand korrigieren (Inventur, ohne Seriennummer)</h6>
      <?php if (!$plainArticles): ?>
        <p class="text-muted mb-0">Keine passenden Artikel vorhanden.</p>
      <?php else: ?>
      <form method="post" action="lager.php?action=korrektur">
        <?= csrf_field() ?>
        <div class="mb-2">
          <select name="article_id" class="form-select" required>
            <option value="">Artikel wählen…</option>
            <?php foreach ($plainArticles as $a): ?>
              <option value="<?= $a['id'] ?>"><?= e($a['name']) ?> — aktuell: <?= num($a['stock_qty']) ?> <?= e($a['unit']) ?></option>
            <?php endforeach; ?>
          </select>
        </div>
        <div class="row g-2">
          <div class="col-6"><input type="text" name="new_qty" class="form-control" placeholder="Neuer Ist-Bestand" required></div>
          <div class="col-6"><input type="text" name="note" class="form-control" placeholder="Notiz (optional)"></div>
        </div>
        <button class="btn btn-app-warning mt-2" type="submit">Korrektur speichern</button>
      </form>
      <?php endif; ?>
    </div>
  </div>
</div>

<div class="row g-3 mb-4">
  <div class="col-md-6">
    <div class="card p-3">
      <h6>Wareneingang mit Seriennummern</h6>
      <?php if (!$serialArticles): ?>
        <p class="text-muted mb-0">Kein Artikel hat die Seriennummern-Erfassung aktiviert. Das lässt sich pro Artikel in der Artikelverwaltung einschalten.</p>
      <?php else: ?>
      <form method="post" action="lager.php?action=einlagern_seriell">
        <?= csrf_field() ?>
        <div class="mb-2">
          <select name="article_id" class="form-select" required>
            <option value="">Artikel wählen…</option>
            <?php foreach ($serialArticles as $a): ?>
              <option value="<?= $a['id'] ?>"><?= e($a['name']) ?> (<?= e($a['sku']) ?>) — aktuell: <?= num($a['stock_qty']) ?></option>
            <?php endforeach; ?>
          </select>
        </div>
        <div class="mb-2">
          <textarea name="serials" class="form-control" rows="4" placeholder="Eine Seriennummer pro Zeile" required></textarea>
          <div class="form-text">Die Anzahl der Zeilen ergibt automatisch die eingelagerte Menge.</div>
        </div>
        <input type="text" name="note" class="form-control mb-2" placeholder="Notiz (optional)">
        <button class="btn btn-app-success" type="submit">Seriennummern einlagern</button>
      </form>
      <?php endif; ?>
    </div>
  </div>
  <div class="col-md-6">
    <div class="card p-3">
      <h6>Seriennummern ansehen / verwalten</h6>
      <?php if (!$serialArticles): ?>
        <p class="text-muted mb-0">—</p>
      <?php else: ?>
      <form method="get" action="lager.php" class="mb-3">
        <select name="view_serials" class="form-select" onchange="this.form.submit()">
          <option value="">Artikel wählen…</option>
          <?php foreach ($serialArticles as $a): ?>
            <option value="<?= $a['id'] ?>" <?= $viewSerialsArticleId===(int)$a['id']?'selected':'' ?>><?= e($a['name']) ?></option>
          <?php endforeach; ?>
        </select>
      </form>
      <?php if ($viewSerialsArticleId): ?>
        <?php if (!$serialsOfArticle): ?>
          <p class="text-muted">Noch keine Seriennummern erfasst.</p>
        <?php else: ?>
        <table class="table table-sm">
          <thead><tr><th>S/N</th><th>Status</th><th></th></tr></thead>
          <tbody>
          <?php foreach ($serialsOfArticle as $s): ?>
            <tr>
              <td><?= e($s['serial_number']) ?></td>
              <td>
                <?php
                  $badgeMap = ['lager'=>'success','verkauft'=>'secondary','defekt'=>'danger'];
                  echo '<span class="badge bg-app-'.$badgeMap[$s['status']].'">'.e(ucfirst($s['status'])).'</span>';
                ?>
              </td>
              <td class="text-end">
                <?php if ($s['status'] === 'lager'): ?>
                  <a href="lager.php?action=seriennummer_defekt&id=<?= $s['id'] ?>&article_id=<?= $viewSerialsArticleId ?>&token=<?= e(csrf_token()) ?>" class="btn btn-sm btn-app-outline-danger" onclick="return confirm('Als defekt markieren? Der Bestand wird um 1 reduziert.')">Defekt melden</a>
                  <a href="lager.php?action=seriennummer_entfernen&id=<?= $s['id'] ?>&article_id=<?= $viewSerialsArticleId ?>&token=<?= e(csrf_token()) ?>" class="btn btn-sm btn-app-outline-secondary" onclick="return confirm('Fälschlich erfasste Seriennummer wirklich entfernen?')">Entfernen</a>
                <?php endif; ?>
              </td>
            </tr>
          <?php endforeach; ?>
          </tbody>
        </table>
        <?php endif; ?>
      <?php endif; ?>
      <?php endif; ?>
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
        <td class="text-end <?= $m['quantity'] < 0 ? 'text-app-danger' : 'text-app-success' ?>"><?= ($m['quantity']>0?'+':'').num($m['quantity']) ?></td>
        <td><?= e($m['note']) ?></td>
        <td><?= e($m['full_name'] ?? '—') ?></td>
      </tr>
    <?php endforeach; ?>
    </tbody>
  </table>
</div>
<?php require_once __DIR__ . '/includes/footer.php'; ?>
