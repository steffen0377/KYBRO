<?php
/**
 * Erzeugt ZUGFeRD-2.1-XML (Profil BASIC) für eine Rechnung und bettet es
 * als PDF/A-3-Anhang in ein bestehendes PDF ein.
 *
 * Benötigt: composer require horstoeko/zugferd
 *
 * WICHTIG: Die exakten Methodennamen können sich je nach installierter
 * Version von horstoeko/zugferd geringfügig unterscheiden. Bitte nach der
 * Installation einmal mit einer Test-Rechnung prüfen (z.B. Validierung der
 * erzeugten XML mit dem KoSIT-Validator: https://github.com/itplr-kosit/validator)
 * und ggf. anhand des README des installierten Pakets anpassen.
 */

use horstoeko\zugferd\ZugferdDocumentBuilder;
use horstoeko\zugferd\ZugferdDocumentPdfBuilder;
use horstoeko\zugferd\ZugferdProfiles;

/**
 * Baut das ZUGFeRD-XML für eine Rechnung.
 *
 * @param array $doc     Datensatz aus invoices (inkl. gejointer Kundendaten wie in rechnung_pdf.php)
 * @param array $items   Zeilen aus invoice_items
 * @param array $company Firmeneinstellungen (company_settings)
 * @return ZugferdDocumentBuilder
 */
function build_zugferd_document(array $doc, array $items, array $company): ZugferdDocumentBuilder
{
    $buyerName = trim($doc['company'] ?: trim($doc['first_name'] . ' ' . $doc['last_name']));
    $issueDate = new DateTime($doc['invoice_date']);
    $serviceDate = new DateTime($doc['service_date'] ?: $doc['invoice_date']);
    $dueDate = $doc['due_date'] ? new DateTime($doc['due_date']) : null;

    $documentBuilder = ZugferdDocumentBuilder::createNew(ZugferdProfiles::PROFILE_BASIC);

    $documentBuilder
        ->setDocumentInformation(
            $doc['invoice_number'],
            '380', // Dokumenttyp-Code: 380 = Handelsrechnung
            $issueDate,
            'EUR'
        )
        ->setDocumentSupplyChainEvent($serviceDate)
        ->setDocumentBuyerReference($doc['invoice_number']);

    if (!empty($doc['notes'])) {
        $documentBuilder->addDocumentNote($doc['notes']);
    }

    // ---------- Verkäufer (eigene Firma) ----------
    $documentBuilder
        ->setDocumentSeller($company['company_name'] ?: 'Firma')
        ->setDocumentSellerAddress(
            $company['street'] ?? '',
            '',
            '',
            $company['zip'] ?? '',
            $company['city'] ?? '',
            'DE'
        );

    if (!empty($company['vat_id'])) {
        $documentBuilder->addDocumentSellerTaxRegistration('VA', $company['vat_id']);
    }
    if (!empty($company['tax_id'])) {
        $documentBuilder->addDocumentSellerTaxRegistration('FC', $company['tax_id']);
    }
    if (!empty($company['email'])) {
        $documentBuilder->setDocumentSellerCommunication('EM', $company['email']);
    }

    // ---------- Käufer (Kunde) ----------
    $documentBuilder
        ->setDocumentBuyer($buyerName)
        ->setDocumentBuyerAddress(
            $doc['street'] ?? '',
            '',
            '',
            $doc['zip'] ?? '',
            $doc['city'] ?? '',
            'DE'
        );

    if (!empty($doc['vat_id'])) {
        $documentBuilder->addDocumentBuyerTaxRegistration('VA', $doc['vat_id']);
    }

    // ---------- Zahlungsbedingungen / Bankverbindung ----------
    if ($dueDate) {
        $documentBuilder->addDocumentPaymentTerm(
            'Zahlbar bis ' . $dueDate->format('d.m.Y'),
            $dueDate
        );
    }
    if (!empty($company['iban'])) {
        // Hinweis: addDocumentPaymentMeanToCreditTransfer() unten setzt den
        // Typ-Code 58 (SEPA-Überweisung) bereits intern selbst
        // (ZugferdPaymentMeans::UNTDID_4461_58). Ein zusätzlicher separater
        // Aufruf von addDocumentPaymentMean('58', ...) hier würde einen
        // ZWEITEN, leeren PaymentMeans-Block (ohne IBAN) erzeugen - das war
        // die Ursache für BR-61 ("Zahlungskonto BT-84 fehlt" bei Typ 58).
        // Daher bewusst NICHT extra aufrufen.

        $accountHolder = !empty($company['account_holder'])
            ? $company['account_holder']
            : $company['company_name'];

        // Signatur laut Quellcode:
        // addDocumentPaymentMeanToCreditTransfer(
        //     string $payeeIban,
        //     ?string $payeeAccountName = null,
        //     ?string $payeePropId = null,   // <- KEIN BIC! (bankfremde Kennung)
        //     ?string $payeeBic = null,      // <- BIC gehört hierher
        //     ?string $paymentReference = null
        // )
        // Bisher wurde der BIC fälschlich an Position 3 (payeePropId) statt
        // Position 4 (payeeBic) übergeben, wodurch er im XML nie ankam.
        $documentBuilder->addDocumentPaymentMeanToCreditTransfer(
            $company['iban'],   // IBAN des Verkäufers (Pflichtfeld, BT-84)
            $accountHolder,     // Kontoinhaber (Optional)
            null,               // payeePropId (bankfremde Kennung) - nicht verwendet
            $company['bic']     // BIC der Bank (Optional, jetzt an korrekter Position)
        );
    }

    // ---------- Positionen ----------
    // Hinweis (BR-S-05): Die Kategorie "S" (Standard) verlangt zwingend
    // einen Steuersatz > 0. Bei 0%-Positionen wegen echter Steuerbefreiung
    // (z.B. §4 Nr. 21a UStG) muss stattdessen Kategorie "E" (Exempt from
    // tax) inkl. Befreiungsgrund (BT-120) gesetzt werden. Die Kategorie
    // wird daher pro Zeile anhand des tatsächlichen Steuersatzes bestimmt,
    // nicht pauschal auf "S" gesetzt.
    $exemptionReason = trim((string)($doc['tax_exemption_reason'] ?? ''));
    if ($exemptionReason === '') {
        $exemptionReason = 'Steuerfrei gemäß §4 Nr. 21a UStG';
    }

    $lineId = 1;
    $taxSummary = []; // rate => ['basis' => x, 'tax' => y]

    foreach ($items as $item) {
        $qty = (float)$item['quantity'];
        $unitPrice = (float)$item['unit_price'];
        $taxRate = (float)$item['tax_rate'];
        $lineTotal = round($qty * $unitPrice, 2);

        $categoryCode = $taxRate > 0 ? 'S' : 'E';

        $documentBuilder->addNewPosition((string)$lineId);
        $documentBuilder
            ->setDocumentPositionProductDetails($item['description'])
            ->setDocumentPositionNetPrice($unitPrice)
            ->setDocumentPositionQuantity($qty, 'C62');

        if ($categoryCode === 'E') {
            $documentBuilder->addDocumentPositionTax('E', 'VAT', $taxRate, null, $exemptionReason);
        } else {
            $documentBuilder->addDocumentPositionTax('S', 'VAT', $taxRate);
        }

        $documentBuilder->setDocumentPositionLineSummation($lineTotal);

        $lineId++;

        $key = $categoryCode . '|' . number_format($taxRate, 2, '.', '');
        if (!isset($taxSummary[$key])) {
            $taxSummary[$key] = ['category' => $categoryCode, 'rate' => $taxRate, 'basis' => 0.0, 'tax' => 0.0];
        }
        $taxSummary[$key]['basis'] += $lineTotal;
        $taxSummary[$key]['tax'] += round($lineTotal * $taxRate / 100, 2);
    }

    // ---------- Steueraufschlüsselung ----------
    foreach ($taxSummary as $sums) {
        if ($sums['category'] === 'E') {
            $documentBuilder->addDocumentTax(
                'E',
                'VAT',
                round($sums['basis'], 2),
                round($sums['tax'], 2),
                (float)$sums['rate'],
                $exemptionReason
            );
        } else {
            $documentBuilder->addDocumentTax(
                'S',
                'VAT',
                round($sums['basis'], 2),
                round($sums['tax'], 2),
                (float)$sums['rate']
            );
        }
    }

    // ---------- Summen ----------
    $lineTotalSum = (float)$doc['total_net'];
    $taxTotalSum = (float)$doc['total_tax'];
    $grandTotal = (float)$doc['total_gross'];

    $documentBuilder->setDocumentSummation(
        $grandTotal,   // grandTotalAmount
        $grandTotal,   // duePayableAmount
        $lineTotalSum, // lineTotalAmount
        0.0,           // chargeTotalAmount
        0.0,           // allowanceTotalAmount
        $lineTotalSum, // taxBasisTotalAmount
        $taxTotalSum   // taxTotalAmount
    );

    return $documentBuilder;
}

/**
 * Fügt das ZUGFeRD-XML in ein bereits gerendertes PDF (z.B. aus Dompdf) ein
 * und liefert das fertige PDF/A-3 als Binärstring zurück.
 *
 * @param ZugferdDocumentBuilder $documentBuilder
 * @param string $pdfContent Rohes PDF (z.B. $dompdf->output())
 * @return string PDF/A-3-Binärdaten inkl. eingebettetem XML
 */
function embed_zugferd_into_pdf(ZugferdDocumentBuilder $documentBuilder, string $pdfContent): string
{
    $pdfBuilder = new ZugferdDocumentPdfBuilder($documentBuilder, $pdfContent);
    $pdfBuilder->generateDocument();
    return $pdfBuilder->downloadString();
}
