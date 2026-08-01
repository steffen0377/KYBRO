<?php
require_once __DIR__ . '/includes/auth.php';
require_once __DIR__ . '/includes/functions.php';

if (current_user()) {
    redirect('index.php');
}

$error = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    csrf_check();
    $username = trim($_POST['username'] ?? '');
    $password = $_POST['password'] ?? '';
    if (attempt_login($username, $password)) {
        redirect('index.php');
    } elseif (!empty($_SESSION['ldap_unavailable_hint'])) {
        unset($_SESSION['ldap_unavailable_hint']);
        $error = 'Der LDAP-Server ist derzeit nicht erreichbar. Bitte wenden Sie sich an einen Administrator.';
    } else {
        $error = 'Benutzername oder Passwort ist falsch.';
    }
}
?>
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Anmelden – Warenwirtschaft</title>
<link href="<?= APP_URL ?>/assets/vendor/bootstrap/css/bootstrap.min.css" rel="stylesheet">
<link href="<?= APP_URL ?>/assets/css/style.css?v=<?= @filemtime(__DIR__ . '/assets/css/style.css') ?: '1' ?>" rel="stylesheet">
</head>
<body class="bg-light">
<div class="container d-flex align-items-center justify-content-center" style="min-height:100vh;">
  <div class="card p-4 shadow-sm" style="max-width:380px; width:100%;">
    <h4 class="mb-3 text-center">📦 Warenwirtschaft</h4>
    <?php if ($error): ?><div class="alert alert-danger"><?= e($error) ?></div><?php endif; ?>
    <form method="post">
      <?= csrf_field() ?>
      <div class="mb-3">
        <label class="form-label">Benutzername</label>
        <input type="text" name="username" class="form-control" required autofocus>
      </div>
      <div class="mb-3">
        <label class="form-label">Passwort</label>
        <input type="password" name="password" class="form-control" required>
      </div>
      <button type="submit" class="btn btn-primary w-100">Anmelden</button>
    </form>
  </div>
</div>
</body>
</html>
