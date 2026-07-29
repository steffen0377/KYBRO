<?php
$pageTitle = 'Benutzer';
require_once __DIR__ . '/includes/header.php';
require_admin();
$pdo = db();
$action = $_GET['action'] ?? 'list';

if ($_SERVER['REQUEST_METHOD'] === 'POST' && $action === 'save') {
    csrf_check();
    $id = (int)($_POST['id'] ?? 0);
    $username = trim($_POST['username']);
    $fullName = trim($_POST['full_name']);
    $role = $_POST['role'] === 'admin' ? 'admin' : 'user';
    $active = isset($_POST['active']) ? 1 : 0;
    $password = $_POST['password'] ?? '';

    if (strlen($username) < 3) { flash('danger','Benutzername zu kurz.'); redirect('benutzer.php'); }

    if ($id) {
        if ($password) {
            $stmt = $pdo->prepare('UPDATE users SET username=?,full_name=?,role=?,active=?,password_hash=? WHERE id=?');
            $stmt->execute([$username, $fullName, $role, $active, password_hash($password, PASSWORD_DEFAULT), $id]);
        } else {
            $stmt = $pdo->prepare('UPDATE users SET username=?,full_name=?,role=?,active=? WHERE id=?');
            $stmt->execute([$username, $fullName, $role, $active, $id]);
        }
        flash('success', 'Benutzer aktualisiert.');
    } else {
        if (strlen($password) < 8) { flash('danger','Passwort muss mindestens 8 Zeichen haben.'); redirect('benutzer.php?action=new'); }
        try {
            $stmt = $pdo->prepare('INSERT INTO users (username,password_hash,full_name,role,active) VALUES (?,?,?,?,?)');
            $stmt->execute([$username, password_hash($password, PASSWORD_DEFAULT), $fullName, $role, $active]);
            flash('success', 'Benutzer angelegt.');
        } catch (PDOException $e) {
            flash('danger', 'Benutzername bereits vergeben.');
        }
    }
    redirect('benutzer.php');
}

if ($action === 'delete' && isset($_GET['id']) && hash_equals(csrf_token(), $_GET['token'] ?? '')) {
    if ((int)$_GET['id'] === (int)current_user()['id']) {
        flash('danger', 'Du kannst dich nicht selbst löschen.');
    } else {
        $pdo->prepare('UPDATE users SET active=0 WHERE id=?')->execute([(int)$_GET['id']]);
        flash('success', 'Benutzer deaktiviert.');
    }
    redirect('benutzer.php');
}

if ($action === 'new' || $action === 'edit') {
    $user = ['id'=>0,'username'=>'','full_name'=>'','role'=>'user','active'=>1];
    if ($action === 'edit') {
        $stmt = $pdo->prepare('SELECT id,username,full_name,role,active FROM users WHERE id=?');
        $stmt->execute([(int)$_GET['id']]);
        $user = $stmt->fetch();
        if (!$user) { flash('danger','Benutzer nicht gefunden.'); redirect('benutzer.php'); }
    }
    ?>
    <h4><?= $action==='new' ? 'Neuer Benutzer' : e($user['full_name'] ?: $user['username']) ?></h4>
    <form method="post" action="benutzer.php?action=save" class="card p-4" style="max-width:500px;">
      <?= csrf_field() ?>
      <input type="hidden" name="id" value="<?= $user['id'] ?>">
      <div class="mb-3"><label class="form-label">Benutzername</label>
        <input type="text" name="username" class="form-control" required value="<?= e($user['username']) ?>"></div>
      <div class="mb-3"><label class="form-label">Voller Name</label>
        <input type="text" name="full_name" class="form-control" value="<?= e($user['full_name']) ?>"></div>
      <div class="mb-3"><label class="form-label">Passwort <?= $action==='edit' ? '(leer lassen = unverändert)' : '' ?></label>
        <input type="password" name="password" class="form-control" <?= $action==='new'?'required':'' ?>></div>
      <div class="mb-3"><label class="form-label">Rolle</label>
        <select name="role" class="form-select">
          <option value="user" <?= $user['role']==='user'?'selected':'' ?>>Benutzer</option>
          <option value="admin" <?= $user['role']==='admin'?'selected':'' ?>>Administrator</option>
        </select></div>
      <div class="form-check mb-3">
        <input type="checkbox" name="active" class="form-check-input" id="active" <?= $user['active']?'checked':'' ?>>
        <label class="form-check-label" for="active">Aktiv</label>
      </div>
      <button class="btn btn-primary" type="submit">Speichern</button>
      <a href="benutzer.php" class="btn btn-secondary">Abbrechen</a>
    </form>
    <?php require_once __DIR__ . '/includes/footer.php'; exit;
}

$users = $pdo->query('SELECT id,username,full_name,role,active FROM users ORDER BY username')->fetchAll();
?>
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4>Benutzer</h4>
  <a href="benutzer.php?action=new" class="btn btn-primary">+ Neuer Benutzer</a>
</div>
<div class="card p-3">
<table class="table table-hover align-middle">
  <thead><tr><th>Benutzername</th><th>Name</th><th>Rolle</th><th>Status</th><th></th></tr></thead>
  <tbody>
  <?php foreach ($users as $u): ?>
    <tr class="<?= !$u['active'] ? 'text-muted' : '' ?>" style="cursor:pointer;" onclick="window.location='benutzer.php?action=edit&id=<?= $u['id'] ?>';">
      <td><?= e($u['username']) ?></td>
      <td><?= e($u['full_name']) ?></td>
      <td><?= $u['role']==='admin' ? 'Administrator' : 'Benutzer' ?></td>
      <td><?= $u['active'] ? '<span class="badge bg-success">Aktiv</span>' : '<span class="badge bg-secondary">Inaktiv</span>' ?></td>
      <td class="text-end">
        <?php if ($u['active']): ?>
        <a href="benutzer.php?action=delete&id=<?= $u['id'] ?>&token=<?= e(csrf_token()) ?>" class="btn btn-sm btn-outline-danger" onclick="return confirm('Benutzer deaktivieren?')">Deaktivieren</a>
        <?php endif; ?>
      </td>
    </tr>
  <?php endforeach; ?>
  </tbody>
</table>
</div>
<?php require_once __DIR__ . '/includes/footer.php'; ?>
