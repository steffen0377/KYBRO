<?php
$pageTitle = 'Kategorien';
require_once __DIR__ . '/includes/header.php';
$pdo = db();
$action = $_GET['action'] ?? 'list';

if ($_SERVER['REQUEST_METHOD'] === 'POST' && $action === 'save') {
    csrf_check();
    $id = (int)($_POST['id'] ?? 0);
    $name = trim($_POST['name'] ?? '');
    if (!$name) {
        flash('danger', 'Name ist Pflichtfeld.');
        redirect('kategorien.php');
    }
    try {
        if ($id) {
            $pdo->prepare('UPDATE categories SET name=? WHERE id=?')->execute([$name, $id]);
            flash('success', 'Kategorie umbenannt.');
        } else {
            $pdo->prepare('INSERT INTO categories (name) VALUES (?)')->execute([$name]);
            flash('success', 'Kategorie angelegt.');
        }
    } catch (PDOException $e) {
        flash('danger', 'Diese Kategorie existiert bereits.');
    }
    redirect('kategorien.php');
}

if ($action === 'delete' && isset($_GET['id']) && hash_equals(csrf_token(), $_GET['token'] ?? '')) {
    $pdo->prepare('DELETE FROM categories WHERE id=?')->execute([(int)$_GET['id']]);
    flash('success', 'Kategorie gelöscht (Zuordnungen bei Artikeln wurden automatisch entfernt).');
    redirect('kategorien.php');
}

$categories = $pdo->query('SELECT c.*, COUNT(ac.article_id) AS article_count
                            FROM categories c
                            LEFT JOIN article_categories ac ON ac.category_id = c.id
                            GROUP BY c.id ORDER BY c.name')->fetchAll();
?>
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4>Kategorien</h4>
  <a href="artikel.php" class="btn btn-outline-secondary">Zurück zu Artikel</a>
</div>

<div class="row g-3">
  <div class="col-md-5">
    <div class="card p-3">
      <h6>Neue Kategorie</h6>
      <form method="post" action="kategorien.php?action=save">
        <?= csrf_field() ?>
        <div class="mb-2">
          <input type="text" name="name" class="form-control" placeholder="Name der Kategorie" required>
        </div>
        <button class="btn btn-primary" type="submit">Anlegen</button>
      </form>
    </div>
  </div>
  <div class="col-md-7">
    <div class="card p-3">
      <h6>Vorhandene Kategorien</h6>
      <?php if (!$categories): ?>
        <p class="text-muted mb-0">Noch keine Kategorien angelegt.</p>
      <?php else: ?>
      <table class="table table-sm align-middle">
        <thead><tr><th>Name</th><th class="text-end">Artikel</th><th></th></tr></thead>
        <tbody>
        <?php foreach ($categories as $c): ?>
          <tr>
            <td>
              <form method="post" action="kategorien.php?action=save" class="d-flex gap-2">
                <?= csrf_field() ?>
                <input type="hidden" name="id" value="<?= $c['id'] ?>">
                <input type="text" name="name" class="form-control form-control-sm" value="<?= e($c['name']) ?>">
                <button class="btn btn-sm btn-outline-secondary" type="submit">Speichern</button>
              </form>
            </td>
            <td class="text-end"><?= $c['article_count'] ?></td>
            <td class="text-end">
              <a href="kategorien.php?action=delete&id=<?= $c['id'] ?>&token=<?= e(csrf_token()) ?>" class="btn btn-sm btn-outline-danger" onclick="return confirm('Kategorie wirklich löschen? Die Zuordnung bei Artikeln wird dabei entfernt (die Artikel selbst bleiben erhalten).')">Löschen</a>
            </td>
          </tr>
        <?php endforeach; ?>
        </tbody>
      </table>
      <?php endif; ?>
    </div>
  </div>
</div>
<?php require_once __DIR__ . '/includes/footer.php'; ?>
