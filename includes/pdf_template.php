<?php
// Erwartet: $doc (offer/order/invoice), $items, $docLabel ('Angebot'/'Auftrag'/'Rechnung'),
//           $docNumberField, $dateField, $dateLabel, $secondDateField, $secondDateLabel, $company
//           $scope ('angebot'/'auftrag'/'rechnung') - steuert die Formulareinstellungen (siehe
//           includes/functions.php: get_form_setting()). Ist $scope nicht gesetzt (z.B. älterer
//           Aufrufer), werden ausschließlich die globalen Default-Werte verwendet.
$scope = $scope ?? 'global';
$fs = fn(string $key, $default = null) => get_form_setting($scope, $key, $default);

$fontFamilyMap = [
    'Helvetica' => 'Helvetica, Arial, sans-serif',
    'Times' => "'Times New Roman', Times, serif",
    'Courier' => "'Courier New', Courier, monospace",
    'DejaVu Sans' => 'DejaVu Sans, sans-serif',
];
$fontFamily = $fontFamilyMap[$fs('font_family')] ?? $fontFamilyMap['DejaVu Sans'];
$fontSize = (float)$fs('font_size');
$marginTop = (float)$fs('margin_top');
$marginBottom = (float)$fs('margin_bottom');
$marginLeft = (float)$fs('margin_left');
$marginRight = (float)$fs('margin_right');
$accentColor = $fs('accent_color');
$showPageNumber = $fs('show_page_number') === '1';
$footerText = $fs('footer_text');
$decimalSeparator = $fs('decimal_separator');
$dateFormat = $fs('date_format');

// Spaltenauswahl: scope-spezifischer Override hat Vorrang vor der globalen
// Auswahl (siehe form_setting_defaults() - 'columns_override' ist im Scope
// leer, solange nichts explizit überschrieben wurde).
$columnsOverride = array_filter(explode(',', $fs('columns_override', '')));
$activeColumns = $columnsOverride ?: array_filter(explode(',', get_form_setting('global', 'table_columns')));
// Hinweis: 'artikelnr' und 'rabatt' sind aktuell noch nicht Teil der Positions-
// Datensätze (offer_items/order_items/invoice_items liefern keine Artikelnummer
// bzw. keinen Rabattwert) - diese beiden Spalten werden daher unabhängig von
// der Auswahl noch nicht gerendert, bis die Positionstabellen entsprechend
// erweitert sind.
$showDiscountColumn = $fs('show_discount_column') === '1'; // derzeit ohne Wirkung, s.o.
$showTaxBreakdown = $fs('show_tax_breakdown') === '1';
$showSubtotal = $fs('show_subtotal') === '1';

$documentTitle = $fs('document_title') ?: $docLabel;
$introText = $fs('intro_text', '');
$closingText = $fs('closing_text', '');
$termLabel = $fs('term_label', $secondDateLabel);
$termDays = $fs('term_days', '');

// Steueraufschlüsselung nach Steuersatz gruppieren (nur benötigt, wenn
// show_tax_breakdown aktiv ist)
$taxGroups = [];
foreach ($items as $it) {
    $rate = (float)$it['tax_rate'];
    $net = $it['quantity'] * $it['unit_price'];
    if (!isset($taxGroups[$rate])) { $taxGroups[$rate] = ['net' => 0, 'tax' => 0]; }
    $taxGroups[$rate]['net'] += $net;
    $taxGroups[$rate]['tax'] += $net * $rate / 100;
}
ksort($taxGroups);

ob_start();
?>
<style>
  @page { margin: <?= $marginTop ?>mm <?= $marginRight ?>mm <?= $marginBottom ?>mm <?= $marginLeft ?>mm; }
  body { font-family: <?= $fontFamily ?>; font-size: <?= $fontSize ?>px; color: #222; }
  /* Beide Blöcke sind seitenabsolut (dompdf unterstützt keine zuverlässige
     Verschachtelung von position:absolute-Containern). dompdf positioniert
     absolute Elemente ohne positionierten Vorfahren relativ zur Content-Box
     innerhalb von @page margin, nicht relativ zur physischen Seitenkante -
     d.h. top:20mm würde real bei marginTop+20mm landen. Deshalb wird der
     bereits durch @page margin verursachte Versatz per calc() abgezogen,
     damit die Werte absolut ab Seitenkante stimmen.
     Absenderzeile (schmal, für Fensterumschlag) oberhalb des Empfängerfelds
     (DIN-5008-Standardmaß 85x45mm). */
  .header-company { position: absolute; top: calc(20mm - <?= $marginTop ?>mm); left: calc(20mm - <?= $marginLeft ?>mm); width: 170mm; }
  .header-recipient { position: absolute; top: calc(45mm - <?= $marginTop ?>mm); left: calc(20mm - <?= $marginLeft ?>mm); width: 85mm; height: 40mm; }
  /* Da die Header-Blöcke aus dem normalen Fluss genommen sind, kennt der
     nachfolgende Inhalt ihre Höhe nicht und würde sonst direkt unter dem
     @page margin-top beginnen. Dieser Spacer im Fluss schiebt den Rest des
     Dokuments manuell unter den Empfängerblock. 85mm = top+height von
     .header-recipient (ab Seitenkante); marginTop wird abgezogen, weil der
     normale Fluss durch @page margin-top bereits um diesen Betrag versetzt
     beginnt. */
  .header-spacer { height: calc(85mm - <?= $marginTop ?>mm); }
  .company-addressline { font-size: 8px; font-weight: bold; }
  h1 { font-size: 20px; margin-bottom: 0; color: <?= e($accentColor) ?>; }
  table { width: 100%; border-collapse: collapse; margin-top: 15px; }
  th { background: #eee; text-align: left; padding: 6px; border-bottom: 2px solid <?= e($accentColor) ?>; }
  td { padding: 6px; border-bottom: 1px solid #ddd; }
  .text-end { text-align: right; }
  .totals td { border: none; padding: 3px 6px; }
  .totals .fw-bold { font-weight: bold; font-size: <?= $fontSize + 2 ?>px; }
  .meta { margin: 20px 0; }
  .intro, .closing { margin: 15px 0; }
  .footer { margin-top: 50px; font-size: 9px; color: #666; border-top: 1px solid #ccc; padding-top: 10px; }
  .page-number:before { content: counter(page); }
  .page-number-total:before { content: counter(pages); }
</style>

<div class="header-company">
  <div class="company-addressline"><?= e($company['company_name'] . ' | ' . $company['street'] . ' | ' . $company['zip'] . ' ' . $company['city']) ?></div>
  <?php if ($company['email']): ?><div>E-Mail: <?= e($company['email']) ?></div><?php endif; ?>
  <?php if ($company['phone']): ?><div>Tel.: <?= e($company['phone']) ?></div><?php endif; ?>
  <?php if ($company['tax_id']): ?><div>USt-IdNr.: <?= e($company['tax_id']) ?></div><?php endif; ?>
</div>

<div class="header-recipient">
  <?= e($doc['company'] ?: trim($doc['first_name'].' '.$doc['last_name'])) ?><br>
  <?= e($doc['street']) ?><br>
  <?= e($doc['zip'] . ' ' . $doc['city']) ?>
</div>

<div class="header-spacer"></div>

<h1><?= e($documentTitle) ?> <?= e($doc[$docNumberField]) ?></h1>

<div class="meta">
  <strong><?= e($dateLabel) ?>:</strong> <?= date($dateFormat, strtotime($doc[$dateField])) ?>
  <?php if (!empty($doc[$secondDateField])): ?>
    &nbsp;&nbsp; <strong><?= e($secondDateLabel) ?>:</strong> <?= date($dateFormat, strtotime($doc[$secondDateField])) ?>
  <?php elseif ($termDays !== ''): ?>
    &nbsp;&nbsp; <strong><?= e($termLabel) ?>:</strong> <?= date($dateFormat, strtotime($doc[$dateField] . ' +' . (int)$termDays . ' days')) ?>
  <?php endif; ?>
</div>

<?php if ($introText !== ''): ?>
  <div class="intro"><?= nl2br(e($introText)) ?></div>
<?php endif; ?>

<table>
  <thead>
    <tr>
      <?php if (in_array('pos', $activeColumns, true)): ?><th>Pos.</th><?php endif; ?>
      <th>Beschreibung</th>
      <?php if (in_array('menge', $activeColumns, true)): ?><th class="text-end">Menge</th><?php endif; ?>
      <?php if (in_array('einzelpreis', $activeColumns, true)): ?><th class="text-end">Einzelpreis</th><?php endif; ?>
      <th class="text-end">MwSt.</th>
      <?php if (in_array('gesamt', $activeColumns, true)): ?><th class="text-end">Gesamt (netto)</th><?php endif; ?>
    </tr>
  </thead>
  <tbody>
    <?php foreach ($items as $i => $it): ?>
    <tr>
      <?php if (in_array('pos', $activeColumns, true)): ?><td><?= (int)($it['position'] ?? $i + 1) ?></td><?php endif; ?>
      <td><?= e($it['description']) ?></td>
      <?php if (in_array('menge', $activeColumns, true)): ?><td class="text-end"><?= num($it['quantity']) ?></td><?php endif; ?>
      <?php if (in_array('einzelpreis', $activeColumns, true)): ?><td class="text-end"><?= money($it['unit_price']) ?></td><?php endif; ?>
      <td class="text-end"><?= num($it['tax_rate']) ?>%</td>
      <?php if (in_array('gesamt', $activeColumns, true)): ?><td class="text-end"><?= money($it['quantity'] * $it['unit_price']) ?></td><?php endif; ?>
    </tr>
    <?php endforeach; ?>
  </tbody>
</table>

<table class="totals" style="width:300px; margin-left:auto;">
  <?php if ($showSubtotal): ?>
  <tr><td>Netto-Summe</td><td class="text-end"><?= money($doc['total_net']) ?></td></tr>
  <?php endif; ?>
  <?php if ($showTaxBreakdown && count($taxGroups) > 1): ?>
    <?php foreach ($taxGroups as $rate => $sums): ?>
    <tr><td>zzgl. <?= num($rate) ?>% MwSt. (auf <?= money($sums['net']) ?>)</td><td class="text-end"><?= money($sums['tax']) ?></td></tr>
    <?php endforeach; ?>
  <?php else: ?>
  <tr><td>zzgl. MwSt.</td><td class="text-end"><?= money($doc['total_tax']) ?></td></tr>
  <?php endif; ?>
  <tr><td class="fw-bold">Gesamtbetrag</td><td class="text-end fw-bold"><?= money($doc['total_gross']) ?></td></tr>
</table>

<?php if (!empty($doc['notes'])): ?>
  <div style="margin-top:20px;"><?= nl2br(e($doc['notes'])) ?></div>
<?php endif; ?>

<?php if ($closingText !== ''): ?>
  <div class="closing"><?= nl2br(e($closingText)) ?></div>
<?php endif; ?>

<div class="footer">
  <?= e($company['company_name']) ?> · <?= e($company['street']) ?>, <?= e($company['zip'].' '.$company['city']) ?>
  <?php if ($company['iban']): ?> · IBAN: <?= e($company['iban']) ?><?php endif; ?>
  <?php if ($company['bic']): ?> · BIC: <?= e($company['bic']) ?><?php endif; ?>
  <?php if ($footerText !== ''): ?><br><?= nl2br(e($footerText)) ?><?php endif; ?>
  <?php if ($showPageNumber): ?><div style="margin-top:4px;">Seite <span class="page-number"></span> von <span class="page-number-total"></span></div><?php endif; ?>
</div>
<?php
return ob_get_clean();
