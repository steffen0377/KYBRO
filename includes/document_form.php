<?php
// Erwartet: $doc, $docType, $items, $customers, $articles, $dateField, $dateLabel,
//           $secondDateField, $secondDateLabel, $statuses, $saveUrl, $formTitle
//           $specialPrices (optional): [customer_id => [article_id => ['type'=>'fixed'|'percent','value'=>float]]]
if (empty($items)) {
    $items = [['article_id'=>'', 'description'=>'', 'quantity'=>1, 'unit_price'=>0, 'tax_rate'=>company_settings()['default_tax_rate']]];
}
if (!isset($specialPrices)) {
    $specialPrices = [];
}
// $pricingOptions (optional): [article_id => [['id'=>..,'billing_type'=>..,'price'=>..], ...]]
if (!isset($pricingOptions)) {
    $pricingOptions = [];
}
?>
<h4><?= e($formTitle) ?></h4>
<form method="post" action="<?= e($saveUrl) ?>" class="card p-4">
  <?= csrf_field() ?>
  <input type="hidden" name="id" value="<?= $doc['id'] ?>">
  <div class="row g-3 mb-3">
    <div class="col-md-4">
      <label class="form-label">Kunde *</label>
      <select name="customer_id" id="customerSelect" class="form-select" required>
        <option value="">Kunde wählen…</option>
        <?php foreach ($customers as $c): ?>
          <option value="<?= $c['id'] ?>" data-exempt="<?= !empty($c['tax_exempt']) ? '1' : '0' ?>" <?= (int)$doc['customer_id']===(int)$c['id']?'selected':'' ?>>
            <?= e($c['company'] ?: trim($c['first_name'].' '.$c['last_name'])) ?>
          </option>
        <?php endforeach; ?>
      </select>
    </div>
    <div class="col-md-3">
      <label class="form-label"><?= e($dateLabel) ?></label>
      <input type="date" name="<?= $dateField ?>" class="form-control" value="<?= e($doc[$dateField]) ?>">
    </div>
    <div class="col-md-3">
      <label class="form-label"><?= e($secondDateLabel) ?></label>
      <input type="date" name="<?= $secondDateField ?>" class="form-control" value="<?= e($doc[$secondDateField]) ?>">
    </div>
    <div class="col-md-2">
      <label class="form-label">Status</label>
      <select name="status" class="form-select">
        <?php foreach ($statuses as $s): ?>
          <option value="<?= $s ?>" <?= $doc['status']===$s?'selected':'' ?>><?= ucfirst($s) ?></option>
        <?php endforeach; ?>
      </select>
    </div>
  </div>

  <table class="table" id="itemsTable">
    <thead><tr><th style="width:20%">Artikel</th><th>Beschreibung</th><th style="width:9%">Menge</th><th style="width:12%">Einzelpreis</th><th style="width:9%">MwSt. %</th><th style="width:13%">Modell</th><th style="width:5%"></th></tr></thead>
    <tbody>
      <?php foreach ($items as $it): ?>
      <tr>
        <td>
          <select class="form-select article-select">
            <option value="">— manuell —</option>
            <?php foreach ($articles as $a): ?>
              <option value="<?= $a['id'] ?>" data-name="<?= e($a['name']) ?>" data-price="<?= num($a['sale_price']) ?>" data-tax="<?= num($a['tax_rate']) ?>" data-pricing="<?= e(json_encode($pricingOptions[$a['id']] ?? [], JSON_NUMERIC_CHECK)) ?>" <?= (int)($it['article_id']??0)===(int)$a['id']?'selected':'' ?>><?= e($a['name']) ?></option>
            <?php endforeach; ?>
          </select>
          <input type="hidden" name="article_id[]" class="article-id-field" value="<?= e($it['article_id'] ?? '') ?>">
        </td>
        <td><input type="text" name="description[]" class="form-control desc-field" value="<?= e($it['description']) ?>"></td>
        <td><input type="text" name="quantity[]" class="form-control qty-field" value="<?= num($it['quantity']) ?>"></td>
        <td><input type="text" name="unit_price[]" class="form-control price-field" value="<?= num($it['unit_price']) ?>"></td>
        <td><input type="text" name="tax_rate[]" class="form-control tax-field" value="<?= num($it['tax_rate']) ?>"></td>
        <td>
          <select class="form-select billing-type-select" name="billing_type[]">
            <option value="einmalig" <?= ($it['billing_type'] ?? 'einmalig')==='einmalig'?'selected':'' ?>>Einmalig</option>
            <option value="monatlich" <?= ($it['billing_type'] ?? 'einmalig')==='monatlich'?'selected':'' ?>>Monatlich</option>
            <option value="jaehrlich" <?= ($it['billing_type'] ?? 'einmalig')==='jaehrlich'?'selected':'' ?>>Jährlich</option>
          </select>
          <input type="hidden" name="pricing_option_id[]" class="pricing-option-id-field" value="<?= e($it['pricing_option_id'] ?? '') ?>">
        </td>
        <td><button type="button" class="btn btn-sm btn-app-outline-danger remove-row">✕</button></td>
      </tr>
      <?php endforeach; ?>
    </tbody>
  </table>
  <button type="button" id="addRow" class="btn btn-sm btn-app-outline-primary mb-3">+ Position hinzufügen</button>

  <div class="mb-3">
    <label class="form-label">Notizen</label>
    <textarea name="notes" class="form-control" rows="2"><?= e($doc['notes']) ?></textarea>
  </div>

  <div class="mt-3">
    <button class="btn btn-app-primary" type="submit">Speichern</button>
    <a href="<?= $docType === 'offer' ? 'angebote.php' : 'rechnungen.php' ?>" class="btn btn-app-secondary">Abbrechen</a>
  </div>
</form>

<script>
// Aktive kundenbezogene Sonderpreise, serverseitig geladen: {customerId: {articleId: {type, value}}}
// type 'fixed' = fester Preis in €, type 'percent' = Rabatt in % auf den Artikel-Standardpreis (data-price).
var specialPrices = <?= json_encode($specialPrices, JSON_NUMERIC_CHECK) ?>;

function getSpecialPrice(customerId, articleId, basePrice) {
  if (!customerId || !articleId) return null;
  var forCustomer = specialPrices[customerId];
  if (!forCustomer) return null;
  var sp = forCustomer[articleId];
  if (!sp) return null;
  if (sp.type === 'percent') {
    return Math.round(basePrice * (1 - sp.value / 100) * 100) / 100;
  }
  return sp.value;
}

function isCurrentCustomerTaxExempt() {
  var sel = document.getElementById('customerSelect');
  var opt = sel.options[sel.selectedIndex];
  return !!(opt && opt.dataset.exempt === '1');
}

function applyTaxExemptToRow(row) {
  var taxField = row.querySelector('.tax-field');
  if (isCurrentCustomerTaxExempt()) {
    taxField.value = '0,00';
    taxField.readOnly = true;
  } else {
    taxField.readOnly = false;
  }
}

function applyTaxExemptToAllRows() {
  document.querySelectorAll('#itemsTable tbody tr').forEach(applyTaxExemptToRow);
}

// Wendet für eine Zeile mit ausgewähltem Artikel den Sonderpreis des aktuell
// gewählten Kunden an (falls vorhanden), sonst bleibt der zuletzt gesetzte
// Preis (z.B. Standardpreis oder manuelle Eingabe) unverändert.
// Sonderpreise gelten nur für den Einmalkauf-Standardpreis, nicht für
// Abo-Preismodelle (dort gilt der beim Artikel hinterlegte Abo-Preis).
function applySpecialPriceToRow(row) {
  var billingSelect = row.querySelector('.billing-type-select');
  if (billingSelect && billingSelect.value !== 'einmalig') return;
  var articleId = row.querySelector('.article-id-field').value;
  if (!articleId) return;
  var articleSelect = row.querySelector('.article-select');
  var opt = articleSelect.options[articleSelect.selectedIndex];
  if (!opt || !opt.dataset.price) return;
  var customerId = document.getElementById('customerSelect').value;
  var basePrice = parseFloat(opt.dataset.price.replace(',', '.'));
  var special = getSpecialPrice(customerId, articleId, basePrice);
  var priceField = row.querySelector('.price-field');
  priceField.value = (special !== null ? special : basePrice).toFixed(2).replace('.', ',');
}

// Baut das Preismodell-Auswahlfeld einer Zeile passend zum aktuell
// ausgewählten Artikel neu auf: bietet nur die Verkaufsmodelle (einmalig/
// monatlich/jährlich) an, die für diesen Artikel als aktive Preisoption
// hinterlegt sind. Ohne Artikelauswahl bzw. ohne hinterlegte Abo-Preise
// bleibt nur "Einmalig" (deaktiviert) übrig.
var billingTypeLabels = {einmalig: 'Einmalig', monatlich: 'Monatlich', jaehrlich: 'Jährlich'};
function refreshBillingOptions(row) {
  var billingSelect = row.querySelector('.billing-type-select');
  var pricingField = row.querySelector('.pricing-option-id-field');
  var articleId = row.querySelector('.article-id-field').value;
  if (!articleId) {
    billingSelect.innerHTML = '<option value="einmalig">Einmalig</option>';
    billingSelect.disabled = true;
    pricingField.value = '';
    return;
  }
  var articleSelect = row.querySelector('.article-select');
  var opt = articleSelect.options[articleSelect.selectedIndex];
  var pricing = [];
  try { pricing = JSON.parse(opt.dataset.pricing || '[]'); } catch (e) { pricing = []; }
  if (!pricing.length) {
    billingSelect.innerHTML = '<option value="einmalig">Einmalig</option>';
    billingSelect.disabled = true;
    pricingField.value = '';
    return;
  }
  billingSelect.disabled = false;
  billingSelect.innerHTML = pricing.map(function(p) {
    return '<option value="' + p.billing_type + '" data-option-id="' + p.id + '" data-price="' + p.price + '">' + billingTypeLabels[p.billing_type] + '</option>';
  }).join('');
}

// Übernimmt den zum aktuell gewählten Preismodell gehörenden Preis und die
// pricing_option_id in die Zeile.
function applyBillingSelection(row) {
  var billingSelect = row.querySelector('.billing-type-select');
  var opt = billingSelect.options[billingSelect.selectedIndex];
  var pricingField = row.querySelector('.pricing-option-id-field');
  if (!opt) return;
  pricingField.value = opt.dataset.optionId || '';
  if (opt.dataset.price !== undefined) {
    row.querySelector('.price-field').value = parseFloat(opt.dataset.price).toFixed(2).replace('.', ',');
  }
}

function applySpecialPriceToAllRows() {
  document.querySelectorAll('#itemsTable tbody tr').forEach(applySpecialPriceToRow);
}

document.getElementById('customerSelect').addEventListener('change', function() {
  applyTaxExemptToAllRows();
  applySpecialPriceToAllRows();
});

document.getElementById('addRow').addEventListener('click', function() {
  const tbody = document.querySelector('#itemsTable tbody');
  const row = tbody.rows[0].cloneNode(true);
  row.querySelectorAll('input').forEach(i => { if (i.type !== 'hidden') i.value = ''; else i.value=''; });
  row.querySelector('.article-select').value = '';
  row.querySelector('.qty-field').value = '1';
  row.querySelector('.tax-field').readOnly = false;
  row.querySelector('.tax-field').value = '<?= num(company_settings()['default_tax_rate']) ?>';
  row.querySelector('.billing-type-select').innerHTML = '<option value="einmalig">Einmalig</option>';
  row.querySelector('.billing-type-select').disabled = true;
  row.querySelector('.pricing-option-id-field').value = '';
  tbody.appendChild(row);
  bindRow(row);
  applyTaxExemptToRow(row);
});

function bindRow(row) {
  row.querySelector('.remove-row').addEventListener('click', function() {
    if (document.querySelectorAll('#itemsTable tbody tr').length > 1) row.remove();
  });
  row.querySelector('.article-select').addEventListener('change', function() {
    const opt = this.options[this.selectedIndex];
    row.querySelector('.article-id-field').value = this.value;
    if (this.value) {
      row.querySelector('.desc-field').value = opt.dataset.name;
      row.querySelector('.price-field').value = opt.dataset.price;
      row.querySelector('.tax-field').value = opt.dataset.tax;
    }
    refreshBillingOptions(row);
    applyBillingSelection(row);
    applyTaxExemptToRow(row);
    applySpecialPriceToRow(row);
  });
  row.querySelector('.billing-type-select').addEventListener('change', function() {
    applyBillingSelection(row);
    applySpecialPriceToRow(row);
  });
}
document.querySelectorAll('#itemsTable tbody tr').forEach(bindRow);
applyTaxExemptToAllRows();
</script>
