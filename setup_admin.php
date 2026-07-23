<?php
// EINMALIGES SETUP-SKRIPT
// Legt den ersten Admin-Benutzer an. Danach BITTE DIESE DATEI LÖSCHEN!
require_once __DIR__ . '/includes/db.php';

$pdo = db();
$count = $pdo->query('SELECT COUNT(*) c FROM users')->fetch()['c'];

$message = '';
$done = false;

if ($count > 0) {
    $message = 'Es existiert bereits mindestens ein Benutzer. Aus Sicherheitsgründen bitte diese Datei jetzt löschen. Neue Benutzer können danach im Menü "Benutzer" (als Admin) angelegt werden.';
} elseif ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $username = trim($_POST['username'] ?? '');
    $fullName = trim($_POST['full_name'] ?? '');
    $password = $_POST['password'] ?? '';
    $password2 = $_POST['password2'] ?? '';

    if (strlen($username) < 3) {
        $message = 'Benutzername muss mindestens 3 Zeichen haben.';
    } elseif (strlen($password) < 8) {
        $message = 'Passwort muss mindestens 8 Zeichen haben.';
    } elseif ($password !== $password2) {
        $message = 'Die Passwörter stimmen nicht überein.';
    } else {
        $hash = password_hash($password, PASSWORD_DEFAULT);
        $stmt = $pdo->prepare('INSERT INTO users (username, password_hash, full_name, role, active) VALUES (?,?,?,"admin",1)');
        $stmt->execute([$username, $hash, $fullName ?: $username]);
        $done = true;
        $message = 'Admin-Konto "' . htmlspecialchars($username) . '" wurde erfolgreich erstellt. Bitte LÖSCHE jetzt diese Datei (setup_admin.php) vom Server und melde dich unter login.php an.';
    }
}
?>
<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"><title>Ersteinrichtung</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet"></head>
<body class="bg-light">
<div class="container py-5" style="max-width:500px;">
  <div class="card p-4 shadow-sm">
    <h4>Ersteinrichtung: Admin-Konto anlegen</h4>
    <?php if ($message): ?>
      <div class="alert alert-<?= $done || $count > 0 ? 'success' : 'danger' ?>"><?= $message ?></div>
    <?php endif; ?>
    <?php if ($count == 0 && !$done): ?>
    <form method="post">
      <div class="mb-3"><label class="form-label">Benutzername</label>
        <input type="text" name="username" class="form-control" required></div>
      <div class="mb-3"><label class="form-label">Voller Name</label>
        <input type="text" name="full_name" class="form-control"></div>
      <div class="mb-3"><label class="form-label">Passwort (mind. 8 Zeichen)</label>
        <input type="password" name="password" class="form-control" required></div>
      <div class="mb-3"><label class="form-label">Passwort wiederholen</label>
        <input type="password" name="password2" class="form-control" required></div>
      <button class="btn btn-primary w-100" type="submit">Admin-Konto erstellen</button>
    </form>
    <?php endif; ?>
  </div>
</div>
</body>
</html>
