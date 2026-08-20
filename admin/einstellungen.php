<?php
require_once $_SERVER['DOCUMENT_ROOT'] . '/includes/auth.php';
require_once ROOT_PATH . '/includes/functions.php';
require_admin();
$pdo = db();
$action = $_GET['action'] ?? 'view';

// ---------- FIRMENEINSTELLUNGEN SPEICHERN ----------
if ($_SERVER['REQUEST_METHOD'] === 'POST' && $action === 'save_company') {
    csrf_check();
    $stmt = $pdo->prepare('UPDATE company_settings SET company_name=?,street=?,zip=?,city=?,country=?,tax_id=?,vat_id=?,iban=?,bic=?,bank_name=?,email=?,phone=?,offer_prefix=?,invoice_prefix=?,default_tax_rate=? WHERE id=1');
    $stmt->execute([
        trim($_POST['company_name']), trim($_POST['street']), trim($_POST['zip']), trim($_POST['city']),
        trim($_POST['country']), trim($_POST['tax_id']), trim($_POST['vat_id']), trim($_POST['iban']), trim($_POST['bic']),
        trim($_POST['bank_name']), trim($_POST['email']), trim($_POST['phone']),
        trim($_POST['offer_prefix']), trim($_POST['invoice_prefix']),
        (float)str_replace(',', '.', $_POST['default_tax_rate']),
    ]);

    if (!empty($_POST['remove_logo'])) {
        $current = $pdo->query('SELECT logo_path FROM company_settings WHERE id=1')->fetch()['logo_path'];
        if ($current) { @unlink(__DIR__ . '/../' . $current); }
        $pdo->prepare('UPDATE company_settings SET logo_path=NULL WHERE id=1')->execute();
    } elseif (!empty($_FILES['logo']['name']) && $_FILES['logo']['error'] === UPLOAD_ERR_OK) {
        $allowed = ['image/png' => 'png', 'image/jpeg' => 'jpg', 'image/svg+xml' => 'svg', 'image/webp' => 'webp'];
        $finfo = finfo_open(FILEINFO_MIME_TYPE);
        $mime = finfo_file($finfo, $_FILES['logo']['tmp_name']);
        finfo_close($finfo);
        if (isset($allowed[$mime]) && $_FILES['logo']['size'] <= 2 * 1024 * 1024) {
            foreach (glob(__DIR__ . '/../uploads/logo.*') as $old) { @unlink($old); }
            $target = 'uploads/logo.' . $allowed[$mime];
            if (move_uploaded_file($_FILES['logo']['tmp_name'], __DIR__ . '/../' . $target)) {
                $pdo->prepare('UPDATE company_settings SET logo_path=? WHERE id=1')->execute([$target]);
            } else {
                flash('danger', 'Logo konnte nicht gespeichert werden. Bitte Schreibrechte für den Ordner "uploads/" prüfen.');
            }
        } else {
            flash('danger', 'Ungültiges Bildformat oder Datei zu groß (max. 2 MB; erlaubt: PNG, JPG, SVG, WEBP).');
        }
    }

    if (!empty($_POST['remove_letterhead'])) {
        $currentLetterhead = $pdo->query('SELECT letterhead_path FROM company_settings WHERE id=1')->fetch()['letterhead_path'];
        if ($currentLetterhead) { @unlink(__DIR__ . '/../' . $currentLetterhead); }
        $pdo->prepare('UPDATE company_settings SET letterhead_path=NULL WHERE id=1')->execute();
    } elseif (!empty($_FILES['letterhead']['name']) && $_FILES['letterhead']['error'] === UPLOAD_ERR_OK) {
        $allowedLetterhead = ['image/png' => 'png', 'image/jpeg' => 'jpg', 'application/pdf' => 'pdf'];
        $finfo = finfo_open(FILEINFO_MIME_TYPE);
        $mime = finfo_file($finfo, $_FILES['letterhead']['tmp_name']);
        finfo_close($finfo);
        if (isset($allowedLetterhead[$mime]) && $_FILES['letterhead']['size'] <= 5 * 1024 * 1024) {
            foreach (glob(__DIR__ . '/../uploads/letterhead.*') as $old) { @unlink($old); }
            $target = 'uploads/letterhead.' . $allowedLetterhead[$mime];
            if (move_uploaded_file($_FILES['letterhead']['tmp_name'], __DIR__ . '/../' . $target)) {
                $pdo->prepare('UPDATE company_settings SET letterhead_path=? WHERE id=1')->execute([$target]);
            } else {
                flash('danger', 'Briefbogen konnte nicht gespeichert werden. Bitte Schreibrechte für den Ordner "uploads/" prüfen.');
            }
        } else {
            flash('danger', 'Ungültiges Dateiformat oder Datei zu groß für den Briefbogen (max. 5 MB; erlaubt: PNG, JPG, PDF).');
        }
    }

    flash('success', 'Firmeneinstellungen gespeichert.');
    redirect('einstellungen.php?tab=firma');
}

// ---------- E-MAIL-/SMTP-EINSTELLUNGEN SPEICHERN ----------
if ($_SERVER['REQUEST_METHOD'] === 'POST' && $action === 'save_email') {
    csrf_check();
    $stmt = $pdo->prepare('UPDATE company_settings SET smtp_host=?,smtp_port=?,smtp_encryption=?,smtp_username=?,smtp_from_email=?,smtp_from_name=? WHERE id=1');
    $stmt->execute([
        trim($_POST['smtp_host']), (int)$_POST['smtp_port'], $_POST['smtp_encryption'],
        trim($_POST['smtp_username']), trim($_POST['smtp_from_email']), trim($_POST['smtp_from_name']),
    ]);
    // Passwort nur überschreiben, wenn ein neuer Wert eingegeben wurde
    if (trim($_POST['smtp_password'] ?? '') !== '') {
        $pdo->prepare('UPDATE company_settings SET smtp_password=? WHERE id=1')->execute([trim($_POST['smtp_password'])]);
    }
    flash('success', 'E-Mail-Einstellungen gespeichert.');
    redirect('einstellungen.php?tab=email');
}

// ---------- LDAP-EINSTELLUNGEN SPEICHERN ----------
if ($_SERVER['REQUEST_METHOD'] === 'POST' && $action === 'save_ldap') {
    csrf_check();
    $stmt = $pdo->prepare('UPDATE ldap_settings SET host=?,port=?,encryption=?,base_dn=?,bind_dn=?,user_filter=?,name_attribute=?,email_attribute=? WHERE id=1');
    $stmt->execute([
        trim($_POST['host']), (int)$_POST['port'], $_POST['encryption'], trim($_POST['base_dn']),
        trim($_POST['bind_dn']), trim($_POST['user_filter']) ?: '(uid=%s)',
        trim($_POST['name_attribute']) ?: 'cn', trim($_POST['email_attribute']) ?: 'mail',
    ]);
    if (trim($_POST['bind_password'] ?? '') !== '') {
        $pdo->prepare('UPDATE ldap_settings SET bind_password=? WHERE id=1')->execute([trim($_POST['bind_password'])]);
    }
    flash('success', 'LDAP-Einstellungen gespeichert.');
    redirect('einstellungen.php?tab=authentifizierung');
}

// ---------- AUTHENTIFIZIERUNGS-REIHENFOLGE SPEICHERN ----------
if ($_SERVER['REQUEST_METHOD'] === 'POST' && $action === 'save_auth_mode') {
    csrf_check();
    $allowedModes = ['local', 'ldap', 'ldap_then_local', 'local_then_ldap'];
    $mode = in_array($_POST['auth_mode'] ?? '', $allowedModes, true) ? $_POST['auth_mode'] : 'local';
    $pdo->prepare('UPDATE auth_config SET auth_mode=? WHERE id=1')->execute([$mode]);
    flash('success', 'Authentifizierungs-Reihenfolge gespeichert.');
    redirect('einstellungen.php?tab=authentifizierung');
}

// ---------- BENUTZER ANLEGEN/BEARBEITEN ----------
if ($_SERVER['REQUEST_METHOD'] === 'POST' && $action === 'save_user') {
    csrf_check();
    $id = (int)($_POST['id'] ?? 0);
    $username = trim($_POST['username'] ?? '');
    $fullName = trim($_POST['full_name'] ?? '');
    $role = ($_POST['role'] ?? 'user') === 'admin' ? 'admin' : 'user';
    $groupId = (int)($_POST['group_id'] ?? 0) ?: null;
    $active = !empty($_POST['active']) ? 1 : 0;
    $password = $_POST['password'] ?? '';

    if ($username === '' || $fullName === '') {
        flash('danger', 'Bitte Benutzername und Name angeben.');
        redirect('einstellungen.php?tab=authentifizierung');
    }

    if ($id) {
        if ($password !== '') {
            $stmt = $pdo->prepare('UPDATE users SET username=?, full_name=?, role=?, group_id=?, active=?, password_hash=? WHERE id=?');
            $stmt->execute([$username, $fullName, $role, $groupId, $active, password_hash($password, PASSWORD_DEFAULT), $id]);
        } else {
            $stmt = $pdo->prepare('UPDATE users SET username=?, full_name=?, role=?, group_id=?, active=? WHERE id=?');
            $stmt->execute([$username, $fullName, $role, $groupId, $active, $id]);
        }
        flash('success', 'Benutzer aktualisiert.');
    } else {
        if ($password === '') {
            flash('danger', 'Bitte ein Passwort für den neuen Benutzer vergeben.');
            redirect('einstellungen.php?tab=authentifizierung');
        }
        try {
            $stmt = $pdo->prepare('INSERT INTO users (username, password_hash, full_name, role, group_id, active) VALUES (?,?,?,?,?,?)');
            $stmt->execute([$username, password_hash($password, PASSWORD_DEFAULT), $fullName, $role, $groupId, $active]);
            flash('success', 'Benutzer angelegt.');
        } catch (PDOException $e) {
            flash('danger', 'Benutzername bereits vergeben.');
        }
    }
    redirect('einstellungen.php?tab=authentifizierung');
}

// ---------- BENUTZER LÖSCHEN ----------
if ($action === 'delete_user' && isset($_GET['id']) && hash_equals(csrf_token(), $_GET['token'] ?? '')) {
    $id = (int)$_GET['id'];
    if ($id === (int)current_user()['id']) {
        flash('danger', 'Sie können sich nicht selbst löschen.');
    } else {
        $pdo->prepare('DELETE FROM users WHERE id=?')->execute([$id]);
        flash('success', 'Benutzer gelöscht.');
    }
    redirect('einstellungen.php?tab=authentifizierung');
}

// ---------- GRUPPE ANLEGEN/BEARBEITEN INKL. BERECHTIGUNGEN ----------
if ($_SERVER['REQUEST_METHOD'] === 'POST' && $action === 'save_group') {
    csrf_check();
    $id = (int)($_POST['id'] ?? 0);
    $name = trim($_POST['name'] ?? '');
    $description = trim($_POST['description'] ?? '');
    if ($name === '') {
        flash('danger', 'Bitte einen Gruppennamen angeben.');
        redirect('einstellungen.php?tab=authentifizierung');
    }

    if ($id) {
        $pdo->prepare('UPDATE `groups` SET name=?, description=? WHERE id=?')->execute([$name, $description, $id]);
        $groupId = $id;
    } else {
        $pdo->prepare('INSERT INTO `groups` (name, description) VALUES (?,?)')->execute([$name, $description]);
        $groupId = (int)$pdo->lastInsertId();
    }

    $pdo->prepare('DELETE FROM group_permissions WHERE group_id=?')->execute([$groupId]);
    $stmt = $pdo->prepare('INSERT INTO group_permissions (group_id, module, can_read, can_write) VALUES (?,?,?,?)');
    foreach (array_keys(known_modules()) as $module) {
        $canRead = !empty($_POST['perm_read'][$module]) ? 1 : 0;
        $canWrite = !empty($_POST['perm_write'][$module]) ? 1 : 0;
        if ($canWrite) { $canRead = 1; } // Schreibrecht impliziert Leserecht
        if ($canRead || $canWrite) {
            $stmt->execute([$groupId, $module, $canRead, $canWrite]);
        }
    }
    flash('success', 'Gruppe gespeichert.');
    redirect('einstellungen.php?tab=authentifizierung');
}

// ---------- GRUPPE LÖSCHEN ----------
if ($action === 'delete_group' && isset($_GET['id']) && hash_equals(csrf_token(), $_GET['token'] ?? '')) {
    $id = (int)$_GET['id'];
    if ($id === 1) {
        flash('danger', 'Die Administratoren-Gruppe kann nicht gelöscht werden.');
    } else {
        $pdo->prepare('DELETE FROM `groups` WHERE id=?')->execute([$id]);
        flash('success', 'Gruppe gelöscht.');
    }
    redirect('einstellungen.php?tab=authentifizierung');
}

// ---------- AB HIER BEGINNT DIE HTML-AUSGABE ----------
$pageTitle = 'Einstellungen';
require_once ROOT_PATH . '/includes/header.php';

$activeTab = in_array($_GET['tab'] ?? '', ['firma', 'email', 'authentifizierung'], true) ? $_GET['tab'] : 'firma';
$s = company_settings();
$ldap = ldap_settings();
$authMode = auth_config()['auth_mode'];
$modules = known_modules();

$users = $pdo->query('SELECT u.*, g.name AS group_name FROM users u LEFT JOIN `groups` g ON g.id = u.group_id ORDER BY u.username')->fetchAll();
$groups = $pdo->query('SELECT * FROM `groups` ORDER BY name')->fetchAll();
$permsByGroup = [];
foreach ($pdo->query('SELECT * FROM group_permissions') as $p) {
    $permsByGroup[$p['group_id']][$p['module']] = $p;
}

$editUser = ['id' => 0, 'username' => '', 'full_name' => '', 'role' => 'user', 'group_id' => null, 'active' => 1];
if (($_GET['edit_user'] ?? '') !== '') {
    $stmt = $pdo->prepare('SELECT * FROM users WHERE id=?');
    $stmt->execute([(int)$_GET['edit_user']]);
    $editUser = $stmt->fetch() ?: $editUser;
}

$editGroup = ['id' => 0, 'name' => '', 'description' => ''];
if (($_GET['edit_group'] ?? '') !== '') {
    $stmt = $pdo->prepare('SELECT * FROM `groups` WHERE id=?');
    $stmt->execute([(int)$_GET['edit_group']]);
    $editGroup = $stmt->fetch() ?: $editGroup;
}
$editGroupPerms = $permsByGroup[$editGroup['id']] ?? [];
?>
<h4>Einstellungen</h4>

<ul class="nav nav-tabs mb-3" role="tablist">
  <li class="nav-item" role="presentation">
    <button class="nav-link <?= $activeTab === 'firma' ? 'active' : '' ?>" id="tab-firma-btn" data-bs-toggle="tab" data-bs-target="#tab-firma" type="button" role="tab" aria-controls="tab-firma" aria-selected="<?= $activeTab === 'firma' ? 'true' : 'false' ?>">Firmeneinstellungen</button>
  </li>
  <li class="nav-item" role="presentation">
    <button class="nav-link <?= $activeTab === 'email' ? 'active' : '' ?>" id="tab-email-btn" data-bs-toggle="tab" data-bs-target="#tab-email" type="button" role="tab" aria-controls="tab-email" aria-selected="<?= $activeTab === 'email' ? 'true' : 'false' ?>">E-Mail</button>
  </li>
  <li class="nav-item" role="presentation">
    <button class="nav-link <?= $activeTab === 'authentifizierung' ? 'active' : '' ?>" id="tab-authentifizierung-btn" data-bs-toggle="tab" data-bs-target="#tab-authentifizierung" type="button" role="tab" aria-controls="tab-authentifizierung" aria-selected="<?= $activeTab === 'authentifizierung' ? 'true' : 'false' ?>">Authentifizierung</button>
  </li>
</ul>

<div class="tab-content">

  <!-- ========================= TAB: FIRMENEINSTELLUNGEN ========================= -->
  <div class="tab-pane fade <?= $activeTab === 'firma' ? 'show active' : '' ?>" id="tab-firma" role="tabpanel" aria-labelledby="tab-firma-btn">
    <form method="post" action="einstellungen.php?action=save_company" enctype="multipart/form-data" class="card p-4" style="max-width:700px;">
      <?= csrf_field() ?>
      <div class="row g-3">
        <div class="col-12">
          <label class="form-label">Logo</label><br>
          <?php if (!empty($s['logo_path'])): ?>
            <img src="<?= APP_URL ?>/<?= e($s['logo_path']) ?>?v=<?= time() ?>" alt="Aktuelles Logo" style="max-height:80px; max-width:240px;" class="d-block mb-2 border rounded p-1">
            <div class="form-check mb-2">
              <input type="checkbox" name="remove_logo" value="1" class="form-check-input" id="remove_logo">
              <label class="form-check-label" for="remove_logo">Aktuelles Logo entfernen</label>
            </div>
          <?php else: ?>
            <div class="text-muted mb-2">Kein Logo hinterlegt – es wird stattdessen nur der Firmenname angezeigt.</div>
          <?php endif; ?>
          <input type="file" name="logo" class="form-control" accept=".png,.jpg,.jpeg,.svg,.webp">
          <div class="form-text">PNG, JPG, SVG oder WEBP, max. 2 MB. Wird links in der Seitenleiste angezeigt.</div>
        </div>
        <div class="col-12">
          <label class="form-label">Briefbogen (Hintergrund für PDFs)</label><br>
          <?php if (!empty($s['letterhead_path'])): ?>
            <?php if (str_ends_with($s['letterhead_path'], '.pdf')): ?>
              <div class="mb-2"><a href="<?= APP_URL ?>/<?= e($s['letterhead_path']) ?>?v=<?= time() ?>" target="_blank">Aktuellen Briefbogen (PDF) ansehen</a></div>
            <?php else: ?>
              <img src="<?= APP_URL ?>/<?= e($s['letterhead_path']) ?>?v=<?= time() ?>" alt="Aktueller Briefbogen" style="max-height:120px; max-width:300px;" class="d-block mb-2 border rounded p-1">
            <?php endif; ?>
            <div class="form-check mb-2">
              <input type="checkbox" name="remove_letterhead" value="1" class="form-check-input" id="remove_letterhead">
              <label class="form-check-label" for="remove_letterhead">Aktuellen Briefbogen entfernen</label>
            </div>
          <?php else: ?>
            <div class="text-muted mb-2">Kein Briefbogen hinterlegt – PDFs werden ohne Hintergrundvorlage erzeugt.</div>
          <?php endif; ?>
          <input type="file" name="letterhead" class="form-control" accept=".png,.jpg,.jpeg,.pdf">
          <div class="form-text">PNG, JPG oder PDF, max. 5 MB. Wird als Hintergrund auf jede Seite der Angebots-, Auftrags- und Rechnungs-PDFs gelegt (bei PDF-Briefbogen wird nur dessen erste Seite verwendet).</div>
        </div>
        <div class="col-12"><label class="form-label">Firmenname / Anwendungsname</label><input type="text" name="company_name" class="form-control" value="<?= e($s['company_name']) ?>"></div>
        <div class="col-md-8"><label class="form-label">Straße & Nr.</label><input type="text" name="street" class="form-control" value="<?= e($s['street']) ?>"></div>
        <div class="col-md-4"><label class="form-label">PLZ</label><input type="text" name="zip" class="form-control" value="<?= e($s['zip']) ?>"></div>
        <div class="col-md-6"><label class="form-label">Ort</label><input type="text" name="city" class="form-control" value="<?= e($s['city']) ?>"></div>
        <div class="col-md-6"><label class="form-label">Land</label><input type="text" name="country" class="form-control" value="<?= e($s['country']) ?>"></div>
        <div class="col-md-6"><label class="form-label">E-Mail</label><input type="email" name="email" class="form-control" value="<?= e($s['email']) ?>"></div>
        <div class="col-md-6"><label class="form-label">Telefon</label><input type="text" name="phone" class="form-control" value="<?= e($s['phone']) ?>"></div>
        <div class="col-md-6"><label class="form-label">Steuernummer</label><input type="text" name="tax_id" class="form-control" value="<?= e($s['tax_id']) ?>"></div>
        <div class="col-md-6"><label class="form-label">USt-IdNr.</label><input type="text" name="vat_id" class="form-control" value="<?= e($s['vat_id']) ?>" placeholder="z.B. DE123456789"></div>
        <div class="col-md-6"><label class="form-label">Standard-MwSt.-Satz (%)</label><input type="text" name="default_tax_rate" class="form-control" value="<?= num($s['default_tax_rate']) ?>"></div>
        <div class="col-md-4"><label class="form-label">IBAN</label><input type="text" name="iban" class="form-control" value="<?= e($s['iban']) ?>"></div>
        <div class="col-md-4"><label class="form-label">BIC</label><input type="text" name="bic" class="form-control" value="<?= e($s['bic']) ?>"></div>
        <div class="col-md-4"><label class="form-label">Bank</label><input type="text" name="bank_name" class="form-control" value="<?= e($s['bank_name']) ?>"></div>
        <div class="col-md-6"><label class="form-label">Präfix Angebotsnummer</label><input type="text" name="offer_prefix" class="form-control" value="<?= e($s['offer_prefix']) ?>"></div>
        <div class="col-md-6"><label class="form-label">Präfix Rechnungsnummer</label><input type="text" name="invoice_prefix" class="form-control" value="<?= e($s['invoice_prefix']) ?>"></div>
      </div>
      <button class="btn btn-app-primary mt-3" type="submit">Speichern</button>
    </form>
  </div>

  <!-- ========================= TAB: E-MAIL ========================= -->
  <div class="tab-pane fade <?= $activeTab === 'email' ? 'show active' : '' ?>" id="tab-email" role="tabpanel" aria-labelledby="tab-email-btn">
    <form method="post" action="einstellungen.php?action=save_email" class="card p-4" style="max-width:700px;">
      <?= csrf_field() ?>
      <div class="row g-3">
        <div class="col-md-8"><label class="form-label">SMTP-Server</label><input type="text" name="smtp_host" class="form-control" value="<?= e($s['smtp_host']) ?>" placeholder="smtp.example.com"></div>
        <div class="col-md-4"><label class="form-label">Port</label><input type="number" name="smtp_port" class="form-control" value="<?= (int)$s['smtp_port'] ?>"></div>
        <div class="col-md-4">
          <label class="form-label">Verschlüsselung</label>
          <select name="smtp_encryption" class="form-select">
            <option value="none" <?= $s['smtp_encryption'] === 'none' ? 'selected' : '' ?>>Keine</option>
            <option value="ssl" <?= $s['smtp_encryption'] === 'ssl' ? 'selected' : '' ?>>SSL</option>
            <option value="tls" <?= $s['smtp_encryption'] === 'tls' ? 'selected' : '' ?>>TLS</option>
          </select>
        </div>
        <div class="col-md-4"><label class="form-label">Benutzername</label><input type="text" name="smtp_username" class="form-control" value="<?= e($s['smtp_username']) ?>"></div>
        <div class="col-md-4">
          <label class="form-label">Passwort</label>
          <input type="password" name="smtp_password" class="form-control" placeholder="<?= $s['smtp_password'] ? '•••••••• (unverändert lassen)' : '' ?>">
        </div>
        <div class="col-md-6"><label class="form-label">Absender-E-Mail</label><input type="email" name="smtp_from_email" class="form-control" value="<?= e($s['smtp_from_email']) ?>"></div>
        <div class="col-md-6"><label class="form-label">Absender-Name</label><input type="text" name="smtp_from_name" class="form-control" value="<?= e($s['smtp_from_name']) ?>"></div>
      </div>
      <button class="btn btn-app-primary mt-3" type="submit">Speichern</button>
    </form>
  </div>

  <!-- ========================= TAB: AUTHENTIFIZIERUNG ========================= -->
  <div class="tab-pane fade <?= $activeTab === 'authentifizierung' ? 'show active' : '' ?>" id="tab-authentifizierung" role="tabpanel" aria-labelledby="tab-authentifizierung-btn">

    <!-- --- LDAP --- -->
    <div class="card p-4 mb-4">
      <h5 class="mb-3">LDAP</h5>
      <form method="post" action="einstellungen.php?action=save_ldap">
        <?= csrf_field() ?>
        <div class="row g-3">
          <div class="col-md-8"><label class="form-label">LDAP-Server</label><input type="text" name="host" class="form-control" value="<?= e($ldap['host']) ?>" placeholder="ldap.example.com"></div>
          <div class="col-md-4"><label class="form-label">Port</label><input type="number" name="port" class="form-control" value="<?= (int)$ldap['port'] ?>"></div>
          <div class="col-md-4">
            <label class="form-label">Verschlüsselung</label>
            <select name="encryption" class="form-select">
              <option value="none" <?= $ldap['encryption'] === 'none' ? 'selected' : '' ?>>Keine</option>
              <option value="starttls" <?= $ldap['encryption'] === 'starttls' ? 'selected' : '' ?>>StartTLS</option>
              <option value="ldaps" <?= $ldap['encryption'] === 'ldaps' ? 'selected' : '' ?>>LDAPS</option>
            </select>
          </div>
          <div class="col-md-8"><label class="form-label">Base DN</label><input type="text" name="base_dn" class="form-control" value="<?= e($ldap['base_dn']) ?>" placeholder="dc=example,dc=com"></div>
          <div class="col-md-6"><label class="form-label">Bind-DN (Service-Account)</label><input type="text" name="bind_dn" class="form-control" value="<?= e($ldap['bind_dn']) ?>" placeholder="cn=service,dc=example,dc=com"></div>
          <div class="col-md-6">
            <label class="form-label">Bind-Passwort</label>
            <input type="password" name="bind_password" class="form-control" placeholder="<?= $ldap['bind_password'] ? '•••••••• (unverändert lassen)' : '' ?>">
          </div>
          <div class="col-md-4"><label class="form-label">Benutzer-Filter</label><input type="text" name="user_filter" class="form-control" value="<?= e($ldap['user_filter']) ?>" placeholder="(uid=%s)"></div>
          <div class="col-md-4"><label class="form-label">Attribut Anzeigename</label><input type="text" name="name_attribute" class="form-control" value="<?= e($ldap['name_attribute']) ?>"></div>
          <div class="col-md-4"><label class="form-label">Attribut E-Mail</label><input type="text" name="email_attribute" class="form-control" value="<?= e($ldap['email_attribute']) ?>"></div>
        </div>
        <button class="btn btn-app-primary mt-3" type="submit">LDAP-Einstellungen speichern</button>
      </form>
    </div>

    <!-- --- AUTHENTIFIZIERUNGSVERFAHREN --- -->
    <div class="card p-4 mb-4">
      <h5 class="mb-3">Authentifizierungsverfahren</h5>
      <form method="post" action="einstellungen.php?action=save_auth_mode" class="row g-2 align-items-end">
        <?= csrf_field() ?>
        <div class="col-auto">
          <label class="form-label" for="auth_mode">Authentifizierungsmethode</label>
          <select class="form-select" name="auth_mode" id="auth_mode">
            <option value="local" <?= $authMode === 'local' ? 'selected' : '' ?>>Nur lokale Datenbank</option>
            <option value="ldap" <?= $authMode === 'ldap' ? 'selected' : '' ?>>Nur LDAP</option>
            <option value="ldap_then_local" <?= $authMode === 'ldap_then_local' ? 'selected' : '' ?>>LDAP vor lokaler Datenbank</option>
            <option value="local_then_ldap" <?= $authMode === 'local_then_ldap' ? 'selected' : '' ?>>Lokale Datenbank vor LDAP</option>
          </select>
        </div>
        <div class="col-auto">
          <button class="btn btn-app-primary" type="submit">Speichern</button>
        </div>
      </form>
    </div>

    <!-- --- BENUTZERVERWALTUNG --- -->
    <div class="card p-4 mb-4">
      <h5 class="mb-3">Benutzerverwaltung</h5>
      <div class="table-responsive mb-4">
        <table class="table table-hover align-middle">
          <thead><tr><th>Benutzername</th><th>Name</th><th>Rolle</th><th>Gruppe</th><th>Quelle</th><th>Aktiv</th><th></th></tr></thead>
          <tbody>
          <?php if (!$users): ?>
            <tr><td colspan="7" class="text-muted text-center py-3">Keine Benutzer vorhanden.</td></tr>
          <?php endif; ?>
          <?php foreach ($users as $usr): ?>
            <tr class="<?= !$usr['active'] ? 'text-muted' : '' ?>">
              <td><?= e($usr['username']) ?></td>
              <td><?= e($usr['full_name']) ?></td>
              <td><?= $usr['role'] === 'admin' ? 'Administrator' : 'Benutzer' ?></td>
              <td><?= e($usr['group_name'] ?? '–') ?></td>
              <td><?= $usr['auth_source'] === 'ldap' ? 'LDAP' : 'Lokal' ?></td>
              <td><?= $usr['active'] ? 'Ja' : 'Nein' ?></td>
              <td class="text-end">
                <a href="einstellungen.php?tab=authentifizierung&edit_user=<?= $usr['id'] ?>#user-form" class="btn btn-sm btn-app-outline-secondary">Bearbeiten</a>
                <?php if ((int)$usr['id'] !== (int)current_user()['id']): ?>
                <a href="einstellungen.php?action=delete_user&id=<?= $usr['id'] ?>&token=<?= e(csrf_token()) ?>" class="btn btn-sm btn-app-outline-danger" onclick="return confirm('Benutzer wirklich löschen?')">Löschen</a>
                <?php endif; ?>
              </td>
            </tr>
          <?php endforeach; ?>
          </tbody>
        </table>
      </div>

      <h6 id="user-form"><?= $editUser['id'] ? 'Benutzer bearbeiten' : 'Neuen Benutzer anlegen' ?></h6>
      <form method="post" action="einstellungen.php?action=save_user" class="row g-3">
        <?= csrf_field() ?>
        <input type="hidden" name="id" value="<?= (int)$editUser['id'] ?>">
        <div class="col-md-4"><label class="form-label">Benutzername</label><input type="text" name="username" class="form-control" value="<?= e($editUser['username']) ?>" required></div>
        <div class="col-md-4"><label class="form-label">Name</label><input type="text" name="full_name" class="form-control" value="<?= e($editUser['full_name']) ?>" required></div>
        <div class="col-md-4"><label class="form-label">Passwort <?= $editUser['id'] ? '(leer lassen für unverändert)' : '' ?></label><input type="password" name="password" class="form-control"></div>
        <div class="col-md-4">
          <label class="form-label">Rolle</label>
          <select name="role" class="form-select">
            <option value="user" <?= $editUser['role'] === 'user' ? 'selected' : '' ?>>Benutzer</option>
            <option value="admin" <?= $editUser['role'] === 'admin' ? 'selected' : '' ?>>Administrator</option>
          </select>
        </div>
        <div class="col-md-4">
          <label class="form-label">Gruppe</label>
          <select name="group_id" class="form-select">
            <option value="">Keine</option>
            <?php foreach ($groups as $g): ?>
              <option value="<?= $g['id'] ?>" <?= (int)$editUser['group_id'] === (int)$g['id'] ? 'selected' : '' ?>><?= e($g['name']) ?></option>
            <?php endforeach; ?>
          </select>
        </div>
        <div class="col-md-4 d-flex align-items-end">
          <div class="form-check">
            <input class="form-check-input" type="checkbox" name="active" id="user_active" value="1" <?= $editUser['active'] ? 'checked' : '' ?>>
            <label class="form-check-label" for="user_active">Aktiv</label>
          </div>
        </div>
        <div class="col-12">
          <button class="btn btn-app-primary" type="submit">Speichern</button>
          <?php if ($editUser['id']): ?><a href="einstellungen.php?tab=authentifizierung" class="btn btn-app-secondary">Abbrechen</a><?php endif; ?>
        </div>
      </form>
    </div>

    <!-- --- GRUPPENVERWALTUNG --- -->
    <div class="card p-4">
      <h5 class="mb-3">Gruppenverwaltung</h5>
      <div class="table-responsive mb-4">
        <table class="table table-hover align-middle">
          <thead><tr><th>Name</th><th>Beschreibung</th><th></th></tr></thead>
          <tbody>
          <?php foreach ($groups as $g): ?>
            <tr>
              <td><?= e($g['name']) ?></td>
              <td><?= e($g['description']) ?></td>
              <td class="text-end">
                <a href="einstellungen.php?tab=authentifizierung&edit_group=<?= $g['id'] ?>#group-form" class="btn btn-sm btn-app-outline-secondary">Bearbeiten</a>
                <?php if ((int)$g['id'] !== 1): ?>
                <a href="einstellungen.php?action=delete_group&id=<?= $g['id'] ?>&token=<?= e(csrf_token()) ?>" class="btn btn-sm btn-app-outline-danger" onclick="return confirm('Gruppe wirklich löschen?')">Löschen</a>
                <?php endif; ?>
              </td>
            </tr>
          <?php endforeach; ?>
          </tbody>
        </table>
      </div>

      <h6 id="group-form"><?= $editGroup['id'] ? 'Gruppe bearbeiten' : 'Neue Gruppe anlegen' ?></h6>
      <form method="post" action="einstellungen.php?action=save_group">
        <?= csrf_field() ?>
        <input type="hidden" name="id" value="<?= (int)$editGroup['id'] ?>">
        <div class="row g-3 mb-3">
          <div class="col-md-4"><label class="form-label">Name</label><input type="text" name="name" class="form-control" value="<?= e($editGroup['name']) ?>" required <?= (int)$editGroup['id'] === 1 ? 'readonly' : '' ?>></div>
          <div class="col-md-8"><label class="form-label">Beschreibung</label><input type="text" name="description" class="form-control" value="<?= e($editGroup['description']) ?>"></div>
        </div>

        <label class="form-label">Zugriffsberechtigungen je Modul</label>
        <div class="table-responsive mb-3">
          <table class="table table-sm">
            <thead><tr><th>Modul</th><th class="text-center">Lesen</th><th class="text-center">Schreiben</th></tr></thead>
            <tbody>
            <?php foreach ($modules as $key => $label): $p = $editGroupPerms[$key] ?? ['can_read' => 0, 'can_write' => 0]; ?>
              <tr>
                <td><?= e($label) ?></td>
                <td class="text-center"><input type="checkbox" name="perm_read[<?= $key ?>]" value="1" <?= $p['can_read'] ? 'checked' : '' ?>></td>
                <td class="text-center"><input type="checkbox" name="perm_write[<?= $key ?>]" value="1" <?= $p['can_write'] ? 'checked' : '' ?>></td>
              </tr>
            <?php endforeach; ?>
            </tbody>
          </table>
        </div>

        <button class="btn btn-app-primary" type="submit">Speichern</button>
        <?php if ($editGroup['id']): ?><a href="einstellungen.php?tab=authentifizierung" class="btn btn-app-secondary">Abbrechen</a><?php endif; ?>
      </form>
    </div>

  </div>
</div>
<?php require_once ROOT_PATH . '/includes/footer.php'; ?>
