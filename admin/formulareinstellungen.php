<?php
require_once $_SERVER['DOCUMENT_ROOT'] . '/includes/auth.php';
require_once ROOT_PATH . '/includes/functions.php';
require_admin();
$pdo = db();
$self = 'admin/' . basename($_SERVER['SCRIPT_NAME']);
$action = $_GET['action'] ?? 'view';

// Scopes, für die (neben 'global') jeweils eigene Formulareinstellungen
// existieren. Reihenfolge bestimmt auch die Tab-Reihenfolge in der Ausgabe.
const FORM_SETTING_SCOPES = ['angebot', 'auftrag', 'rechnung'];

// ---------- FORMULAREINSTELLUNGEN SPEICHERN (Allgemein + je Formulartyp) ----------
// Ein gemeinsamer Handler für alle vier Tabs: das gespeicherte Scope-Array
// bestimmt sich aus dem POST-Feld "scope", die zu speichernden Felder aus
// den Keys in form_setting_defaults() für diesen Scope - so muss beim
// Hinzufügen neuer Einstellungsfelder nur form_setting_defaults() ergänzt
// werden, nicht dieser Handler.
if ($_SERVER['REQUEST_METHOD'] === 'POST' && $action === 'save_form_settings') {
    csrf_check();
    $scope = $_POST['scope'] ?? '';
    $validScopes = array_merge(['global'], FORM_SETTING_SCOPES);
    if (!in_array($scope, $validScopes, true)) {
        flash('danger', 'Ungültiger Formulartyp.');
        redirect($self);
    }

    $defaults = form_setting_defaults();
    $checkboxKeys = ['use_letterhead', 'show_page_number', 'show_discount_column', 'show_tax_breakdown', 'show_subtotal'];
    // Tri-State-Keys: aktiviert ('1') / deaktiviert ('0') / vererbt (kein
    // Eintrag) - nur relevant in den Formulartyp-Tabs, da dort ein Scope
    // existiert, von dem geerbt werden kann. Im Tab "Allgemein" gibt es keinen
    // übergeordneten Scope, dort verhält sich der Key wie ein normales Boolean.
    $triStateKeys = ['show_footer_company_block'];

    foreach (array_keys($defaults[$scope]) as $key) {
        if ($key === 'table_columns' || $key === 'columns_override') {
            // Mehrfachauswahl der Spalten kommt als Array checkbox[] aus dem Formular
            // (table_columns[] im Tab "Allgemein", columns_override[] je Formulartyp)
            $postField = $key === 'table_columns' ? 'table_columns' : 'columns_override';
            $selected = array_map('strval', $_POST[$postField] ?? []);
            $allowed = ['pos', 'artikelnr', 'bezeichnung', 'menge', 'einzelpreis', 'rabatt', 'gesamt'];
            $selected = array_values(array_intersect($allowed, $selected));
            save_form_setting($scope, $key, implode(',', $selected));
        } elseif ($scope !== 'global' && in_array($key, $triStateKeys, true)) {
            $val = (string)($_POST[$key] ?? '');
            save_form_setting($scope, $key, in_array($val, ['0', '1'], true) ? $val : '');
        } elseif (in_array($key, array_merge($checkboxKeys, $triStateKeys), true)) {
            save_form_setting($scope, $key, !empty($_POST[$key]) ? '1' : '0');
        } else {
            save_form_setting($scope, $key, trim((string)($_POST[$key] ?? '')));
        }
    }

    flash('success', 'Formulareinstellungen gespeichert.');
    redirect($self . '?tab=' . $scope);
}

// ---------- AB HIER BEGINNT DIE HTML-AUSGABE ----------
$pageTitle = 'Formulareinstellungen';
require_once ROOT_PATH . '/includes/header.php';

$allTabs = array_merge(['global'], FORM_SETTING_SCOPES);
$activeTab = in_array($_GET['tab'] ?? '', $allTabs, true) ? $_GET['tab'] : 'global';

$scopeLabels = [
    'global' => 'Allgemein',
    'angebot' => 'Angebot',
    'auftrag' => 'Auftrag',
    'rechnung' => 'Rechnung',
];

$valuesByScope = [];
foreach ($allTabs as $scope) {
    $valuesByScope[$scope] = get_form_settings_for_scope($scope);
}

$tableColumnLabels = [
    'pos' => 'Pos.',
    'artikelnr' => 'Artikel-Nr.',
    'bezeichnung' => 'Bezeichnung',
    'menge' => 'Menge',
    'einzelpreis' => 'Einzelpreis',
    'rabatt' => 'Rabatt',
    'gesamt' => 'Gesamt',
];
?>
<h4>Formulareinstellungen</h4>
<p class="text-muted">Layout-Einstellungen für Angebote, Aufträge und Rechnungen. Werte im Tab "Allgemein" gelten für alle Formulare, sofern im jeweiligen Formulartyp kein abweichender Wert gesetzt ist. Der Briefkopf selbst wird weiterhin zentral unter <a href="<?= module_url('einstellungen.php') ?>">Firmeneinstellungen</a> hochgeladen.</p>

<ul class="nav nav-tabs mb-3" role="tablist">
  <?php foreach ($allTabs as $scope): ?>
  <li class="nav-item" role="presentation">
    <button class="nav-link <?= $activeTab === $scope ? 'active' : '' ?>" id="tab-<?= $scope ?>-btn" data-bs-toggle="tab" data-bs-target="#tab-<?= $scope ?>" type="button" role="tab" aria-controls="tab-<?= $scope ?>" aria-selected="<?= $activeTab === $scope ? 'true' : 'false' ?>"><?= e($scopeLabels[$scope]) ?></button>
  </li>
  <?php endforeach; ?>
</ul>

<div class="tab-content">

  <!-- ========================= TAB: ALLGEMEIN ========================= -->
  <div class="tab-pane fade <?= $activeTab === 'global' ? 'show active' : '' ?>" id="tab-global" role="tabpanel" aria-labelledby="tab-global-btn">
    <?php $v = $valuesByScope['global']; ?>
    <form method="post" action="formulareinstellungen.php?action=save_form_settings" class="card p-4" style="max-width:800px;">
      <?= csrf_field() ?>
      <input type="hidden" name="scope" value="global">

      <h6 class="mb-3">Layout</h6>
      <div class="row g-3 mb-4">
        <div class="col-md-6">
          <label class="form-label">Schriftart</label>
          <select name="font_family" class="form-select">
            <?php foreach (['Helvetica', 'Times', 'Courier', 'DejaVu Sans'] as $font): ?>
              <option value="<?= e($font) ?>" <?= $v['font_family'] === $font ? 'selected' : '' ?>><?= e($font) ?></option>
            <?php endforeach; ?>
          </select>
        </div>
        <div class="col-md-6"><label class="form-label">Schriftgröße (Basis, pt)</label><input type="number" step="0.5" name="font_size" class="form-control" value="<?= e($v['font_size']) ?>"></div>
        <div class="col-md-3"><label class="form-label">Rand oben (mm)</label><input type="number" step="0.5" name="margin_top" class="form-control" value="<?= e($v['margin_top']) ?>"></div>
        <div class="col-md-3"><label class="form-label">Rand unten (mm)</label><input type="number" step="0.5" name="margin_bottom" class="form-control" value="<?= e($v['margin_bottom']) ?>"></div>
        <div class="col-md-3"><label class="form-label">Rand links (mm)</label><input type="number" step="0.5" name="margin_left" class="form-control" value="<?= e($v['margin_left']) ?>"></div>
        <div class="col-md-3"><label class="form-label">Rand rechts (mm)</label><input type="number" step="0.5" name="margin_right" class="form-control" value="<?= e($v['margin_right']) ?>"></div>
      </div>

      <h6 class="mb-3">Briefkopf</h6>
      <div class="row g-3 mb-4">
        <div class="col-12">
          <div class="form-check">
            <input type="checkbox" name="use_letterhead" value="1" class="form-check-input" id="use_letterhead" <?= $v['use_letterhead'] === '1' ? 'checked' : '' ?>>
            <label class="form-check-label" for="use_letterhead">Briefkopf standardmäßig auf allen Formularen verwenden</label>
          </div>
          <div class="form-text">Der Briefkopf selbst wird unter Firmeneinstellungen hochgeladen. Diese Option steuert nur, ob er standardmäßig eingeblendet wird.</div>
        </div>
        <div class="col-md-6">
          <label class="form-label">Logo-Position</label>
          <select name="logo_position" class="form-select">
            <option value="links" <?= $v['logo_position'] === 'links' ? 'selected' : '' ?>>Links</option>
            <option value="mittig" <?= $v['logo_position'] === 'mittig' ? 'selected' : '' ?>>Mittig</option>
            <option value="rechts" <?= $v['logo_position'] === 'rechts' ? 'selected' : '' ?>>Rechts</option>
          </select>
        </div>
        <div class="col-md-6"><label class="form-label">Logo-Höhe (mm)</label><input type="number" step="0.5" name="logo_height" class="form-control" value="<?= e($v['logo_height']) ?>"></div>
      </div>

      <h6 class="mb-3">Farben & Fußzeile</h6>
      <div class="row g-3 mb-4">
        <div class="col-md-4">
          <label class="form-label">Akzentfarbe</label>
          <input type="color" name="accent_color" class="form-control form-control-color" value="<?= e($v['accent_color']) ?>">
        </div>
        <div class="col-md-8 d-flex align-items-end">
          <div class="form-check">
            <input type="checkbox" name="show_page_number" value="1" class="form-check-input" id="show_page_number" <?= $v['show_page_number'] === '1' ? 'checked' : '' ?>>
            <label class="form-check-label" for="show_page_number">Seitenzahl in der Fußzeile anzeigen</label>
          </div>
        </div>
        <div class="col-md-8 d-flex align-items-end">
          <div class="form-check">
            <input type="checkbox" name="show_footer_company_block" value="1" class="form-check-input" id="show_footer_company_block" <?= $v['show_footer_company_block'] === '1' ? 'checked' : '' ?>>
            <label class="form-check-label" for="show_footer_company_block">Firmendaten (Name, Adresse, IBAN/BIC) in der Fußzeile anzeigen</label>
          </div>
          <div class="form-text ms-2">Deaktivieren, wenn diese Angaben bereits im Briefpapier enthalten sind. Kann je Formulartyp überschrieben werden.</div>
        </div>
        <div class="col-12">
          <label class="form-label">Standard-Fußzeilentext</label>
          <textarea name="footer_text" class="form-control" rows="2" placeholder="z.B. Bankverbindung, Geschäftsführer, Registergericht"><?= e($v['footer_text']) ?></textarea>
        </div>
      </div>

      <h6 class="mb-3">Positionstabelle (Standard-Spalten)</h6>
      <div class="row g-2 mb-4">
        <?php $activeColumns = explode(',', $v['table_columns']); ?>
        <?php foreach ($tableColumnLabels as $col => $label): ?>
          <div class="col-md-3 col-6">
            <div class="form-check">
              <input type="checkbox" name="table_columns[]" value="<?= $col ?>" class="form-check-input" id="col_<?= $col ?>" <?= in_array($col, $activeColumns, true) ? 'checked' : '' ?>>
              <label class="form-check-label" for="col_<?= $col ?>"><?= e($label) ?></label>
            </div>
          </div>
        <?php endforeach; ?>
        <div class="form-text">Kann je Formulartyp im jeweiligen Tab überschrieben werden.</div>
      </div>

      <h6 class="mb-3">Zahlen & Formate</h6>
      <div class="row g-3">
        <div class="col-md-4">
          <label class="form-label">Währungsformat</label>
          <select name="currency_format" class="form-select">
            <option value="de_DE" <?= $v['currency_format'] === 'de_DE' ? 'selected' : '' ?>>1.234,56 € (Deutschland)</option>
            <option value="en_US" <?= $v['currency_format'] === 'en_US' ? 'selected' : '' ?>>€1,234.56 (US)</option>
          </select>
        </div>
        <div class="col-md-4">
          <label class="form-label">Datumsformat</label>
          <select name="date_format" class="form-select">
            <option value="d.m.Y" <?= $v['date_format'] === 'd.m.Y' ? 'selected' : '' ?>>31.12.2026</option>
            <option value="Y-m-d" <?= $v['date_format'] === 'Y-m-d' ? 'selected' : '' ?>>2026-12-31</option>
            <option value="d/m/Y" <?= $v['date_format'] === 'd/m/Y' ? 'selected' : '' ?>>31/12/2026</option>
          </select>
        </div>
        <div class="col-md-4">
          <label class="form-label">Dezimaltrennzeichen</label>
          <select name="decimal_separator" class="form-select">
            <option value="," <?= $v['decimal_separator'] === ',' ? 'selected' : '' ?>>Komma (1.234,56)</option>
            <option value="." <?= $v['decimal_separator'] === '.' ? 'selected' : '' ?>>Punkt (1,234.56)</option>
          </select>
        </div>
      </div>

      <button class="btn btn-app-primary mt-4" type="submit">Speichern</button>
    </form>
  </div>

  <!-- ========================= TABS: ANGEBOT / AUFTRAG / RECHNUNG ========================= -->
  <?php foreach (FORM_SETTING_SCOPES as $scope): $v = $valuesByScope[$scope]; ?>
  <div class="tab-pane fade <?= $activeTab === $scope ? 'show active' : '' ?>" id="tab-<?= $scope ?>" role="tabpanel" aria-labelledby="tab-<?= $scope ?>-btn">
    <form method="post" action="formulareinstellungen.php?action=save_form_settings" class="card p-4" style="max-width:800px;">
      <?= csrf_field() ?>
      <input type="hidden" name="scope" value="<?= $scope ?>">

      <div class="row g-3 mb-4">
        <div class="col-md-6"><label class="form-label">Bezeichnung des Dokuments</label><input type="text" name="document_title" class="form-control" value="<?= e($v['document_title']) ?>"></div>
        <?php if ($scope === 'rechnung'): ?>
        <div class="col-md-6">
          <label class="form-label">ZUGFeRD-Profil</label>
          <select name="zugferd_profile" class="form-select">
            <option value="BASIC" <?= $v['zugferd_profile'] === 'BASIC' ? 'selected' : '' ?>>BASIC</option>
          </select>
          <div class="form-text">Aktuell wird nur BASIC unterstützt (siehe horstoeko/zugferd-Integration).</div>
        </div>
        <?php endif; ?>
      </div>

      <h6 class="mb-3">Textbausteine</h6>
      <div class="row g-3 mb-4">
        <div class="col-12">
          <label class="form-label">Einleitungstext</label>
          <textarea name="intro_text" class="form-control" rows="2"><?= e($v['intro_text']) ?></textarea>
        </div>
        <div class="col-12">
          <label class="form-label">Schlusstext</label>
          <textarea name="closing_text" class="form-control" rows="2"><?= e($v['closing_text']) ?></textarea>
          <div class="form-text">Platzhalter wie <code>{kunde_name}</code> können hier verwendet werden.</div>
        </div>
        <?php if ($scope === 'rechnung'): ?>
        <div class="col-12">
          <label class="form-label">Skonto-Hinweistext (optional)</label>
          <input type="text" name="skonto_text" class="form-control" value="<?= e($v['skonto_text']) ?>" placeholder="z.B. Bei Zahlung innerhalb von 7 Tagen 2% Skonto">
        </div>
        <?php endif; ?>
      </div>

      <h6 class="mb-3">Frist</h6>
      <div class="row g-3 mb-4">
        <div class="col-md-6"><label class="form-label">Bezeichnung</label><input type="text" name="term_label" class="form-control" value="<?= e($v['term_label']) ?>"></div>
        <div class="col-md-6"><label class="form-label">Anzahl Tage (ab Dokumentdatum)</label><input type="number" name="term_days" class="form-control" value="<?= e($v['term_days']) ?>"></div>
      </div>

      <h6 class="mb-3">Positionstabelle & Summenblock</h6>
      <div class="row g-3 mb-2">
        <div class="col-12">
          <label class="form-label">Spalten-Override (leer = globale Auswahl verwenden)</label>
          <?php $scopeColumns = array_filter(explode(',', $v['columns_override'])); ?>
          <div class="row g-2">
            <?php foreach ($tableColumnLabels as $col => $label): ?>
              <div class="col-md-3 col-6">
                <div class="form-check">
                  <input type="checkbox" name="columns_override[]" value="<?= $col ?>" class="form-check-input" id="<?= $scope ?>_col_<?= $col ?>" <?= in_array($col, $scopeColumns, true) ? 'checked' : '' ?>>
                  <label class="form-check-label" for="<?= $scope ?>_col_<?= $col ?>"><?= e($label) ?></label>
                </div>
              </div>
            <?php endforeach; ?>
          </div>
        </div>
        <div class="col-md-4">
          <div class="form-check">
            <input type="checkbox" name="show_discount_column" value="1" class="form-check-input" id="<?= $scope ?>_show_discount" <?= $v['show_discount_column'] === '1' ? 'checked' : '' ?>>
            <label class="form-check-label" for="<?= $scope ?>_show_discount">Rabattspalte anzeigen</label>
          </div>
        </div>
        <div class="col-md-4">
          <div class="form-check">
            <input type="checkbox" name="show_tax_breakdown" value="1" class="form-check-input" id="<?= $scope ?>_show_tax" <?= $v['show_tax_breakdown'] === '1' ? 'checked' : '' ?>>
            <label class="form-check-label" for="<?= $scope ?>_show_tax">Steueraufschlüsselung anzeigen</label>
          </div>
        </div>
        <div class="col-md-4">
          <div class="form-check">
            <input type="checkbox" name="show_subtotal" value="1" class="form-check-input" id="<?= $scope ?>_show_subtotal" <?= $v['show_subtotal'] === '1' ? 'checked' : '' ?>>
            <label class="form-check-label" for="<?= $scope ?>_show_subtotal">Zwischensumme anzeigen</label>
          </div>
        </div>
      </div>

      <h6 class="mb-3">Fußzeile</h6>
      <div class="row g-3 mb-4">
        <?php
          $rawFooterBlock = get_raw_form_setting($scope, 'show_footer_company_block'); // '0'|'1'|null (null = vererbt)
          $inheritedOn = get_form_setting('global', 'show_footer_company_block') === '1';
          $triState = $rawFooterBlock === null ? 'inherit' : ($rawFooterBlock === '1' ? 'on' : 'off');
          $inheritLabel = 'Vererbt (' . ($inheritedOn ? 'aktiviert' : 'deaktiviert') . ')';
        ?>
        <div class="col-md-6">
          <label class="form-label d-block">Firmendaten-Fußzeile (Name, Adresse, IBAN/BIC)</label>
          <button type="button"
                  class="btn tristate-toggle tristate-<?= $triState ?>"
                  data-state="<?= $triState ?>"
                  data-inherit-label="<?= e($inheritLabel) ?>"
                  data-target="footer_block_<?= $scope ?>">
            <?= $triState === 'inherit' ? e($inheritLabel) : ($triState === 'on' ? 'Aktiviert' : 'Deaktiviert') ?>
          </button>
          <input type="hidden" name="show_footer_company_block" id="footer_block_<?= $scope ?>" value="<?= e($rawFooterBlock ?? '') ?>">
          <div class="form-text">Deaktivieren, wenn diese Angaben bereits im Briefpapier enthalten sind. Ohne Klick bleibt der globale Wert (Tab "Allgemein") wirksam.</div>
        </div>
      </div>

      <button class="btn btn-app-primary mt-3" type="submit">Speichern</button>
    </form>
  </div>
  <?php endforeach; ?>

</div>

<style>
  /* Tri-State-Steuerelement (aktiviert/deaktiviert/vererbt): "vererbt" wird
     blassgrau dargestellt, um zu signalisieren, dass der Wert vom globalen
     Tab übernommen wird; ein explizit gesetzter Wert (aktiviert/deaktiviert)
     wird kräftig eingefärbt, damit die Überschreibung sofort auffällt. */
  .tristate-toggle { min-width: 170px; text-align: left; }
  .tristate-toggle.tristate-inherit { color: #6c757d; background: #f1f3f5; border: 1px dashed #adb5bd; }
  .tristate-toggle.tristate-on { color: #fff; background: #198754; border: 1px solid #198754; font-weight: 600; }
  .tristate-toggle.tristate-off { color: #fff; background: #dc3545; border: 1px solid #dc3545; font-weight: 600; }
</style>
<script>
(function () {
  // Zyklus per Klick: vererbt -> aktiviert -> deaktiviert -> vererbt.
  // Der tatsächliche Wert wird im zugehörigen hidden input gespeichert
  // ('' = vererbt, '1' = aktiviert, '0' = deaktiviert) und so mitgesendet.
  var order = ['inherit', 'on', 'off'];
  document.querySelectorAll('.tristate-toggle').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var input = document.getElementById(btn.dataset.target);
      var next = order[(order.indexOf(btn.dataset.state) + 1) % order.length];
      btn.dataset.state = next;
      btn.classList.remove('tristate-inherit', 'tristate-on', 'tristate-off');
      btn.classList.add('tristate-' + next);
      if (next === 'inherit') {
        input.value = '';
        btn.textContent = btn.dataset.inheritLabel;
      } else if (next === 'on') {
        input.value = '1';
        btn.textContent = 'Aktiviert';
      } else {
        input.value = '0';
        btn.textContent = 'Deaktiviert';
      }
    });
  });
})();
</script>
<?php require_once ROOT_PATH . '/includes/footer.php'; ?>
