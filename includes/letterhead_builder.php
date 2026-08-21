<?php
/**
 * Briefbogen-Einbettung per FPDI
 * -------------------------------
 * Legt den in den Firmeneinstellungen hinterlegten Briefbogen
 * (company_settings.letterhead_path, PNG/JPG oder PDF) als Hintergrund
 * auf jede Seite eines bereits fertig gerenderten PDFs (z.B. der Dompdf-
 * Ausgabe von includes/pdf_template.php).
 *
 * Nutzt dieselbe FPDI/FPDF-Bibliothek, die bereits für den ZUGFeRD-Export
 * (setasign/fpdi, setasign/fpdf) über horstoeko/zugferd installiert ist,
 * es ist also keine zusätzliche Composer-Abhängigkeit nötig.
 *
 * WICHTIG (PDF/A-Konformität): Wird ein PDF-Briefbogen mit einer bereits
 * ZUGFeRD-konformen PDF/A-3-Rechnung kombiniert, ist die durch FPDI
 * zusammengeführte Ausgabedatei technisch kein garantiert normkonformes
 * PDF/A mehr (FPDI kopiert Seiteninhalte, nicht die vollständige PDF/A-
 * Metadatenstruktur). Für die meisten Anwendungsfälle (Sichtprüfung,
 * Versand, ERP-Import) ist das unproblematisch; bei strikter PDF/A-3-Pflicht
 * bitte den Briefbogen stattdessen bereits in die Vorlage integrieren, mit
 * der die Rechnung erzeugt wird, oder den Briefbogen ausschließlich als
 * PNG/JPG (kein PDF) hinterlegen.
 */

use setasign\Fpdi\Fpdi;

/**
 * Bequemer Wrapper: liest company_settings['letterhead_path'] aus und legt
 * den Briefbogen (falls vorhanden) auf das übergebene PDF. Gibt bei Fehlern
 * (z.B. beschädigte/inkompatible Briefbogen-Datei) unverändert das
 * Ursprungs-PDF zurück und protokolliert den Fehler, damit ein defekter
 * Briefbogen niemals die eigentliche PDF-Erzeugung (Angebot/Auftrag/
 * Rechnung) verhindert.
 */
function apply_company_letterhead(string $pdfContent, array $company): string {
    if (empty($company['letterhead_path'])) {
        return $pdfContent;
    }
    $letterheadAbsolutePath = realpath(ROOT_PATH . '/' . $company['letterhead_path']);
    if (!$letterheadAbsolutePath || !is_readable($letterheadAbsolutePath)) {
        error_log('[Briefbogen] Datei nicht gefunden oder nicht lesbar: ' . $company['letterhead_path'] . ' (aufgeloest: ' . ROOT_PATH . '/' . $company['letterhead_path'] . ')');
        return $pdfContent;
    }
    try {
        return apply_letterhead_to_pdf($pdfContent, $letterheadAbsolutePath);
    } catch (Throwable $e) {
        error_log('[Briefbogen] Einbettung fehlgeschlagen, PDF wird ohne Briefbogen ausgeliefert: ' . $e->getMessage() . ' in ' . $e->getFile() . ':' . $e->getLine());
        return $pdfContent;
    }
}

/**
 * Legt $letterheadPath (PNG/JPG oder PDF, jeweils nur die erste Seite bei
 * PDF) als Hintergrund auf jede Seite von $pdfContent (Rohdaten eines
 * bereits gerenderten PDFs, z.B. $dompdf->output()) und gibt die
 * zusammengeführten PDF-Rohdaten zurück.
 *
 * @throws Exception falls $pdfContent oder der Briefbogen von FPDI nicht
 *                    gelesen werden können (z.B. verschlüsseltes PDF).
 */
function apply_letterhead_to_pdf(string $pdfContent, string $letterheadPath): string {
    $isPdfLetterhead = strtolower(pathinfo($letterheadPath, PATHINFO_EXTENSION)) === 'pdf';
    error_log(sprintf(
        '[Briefbogen] Start: Typ=%s, Datei=%s, Inhaltsgroesse=%d Bytes',
        $isPdfLetterhead ? 'PDF' : 'Bild',
        $letterheadPath,
        strlen($pdfContent)
    ));

    $tmpContentFile = tempnam(sys_get_temp_dir(), 'kybro_pdf_');
    file_put_contents($tmpContentFile, $pdfContent);

    try {
        $pdf = new Fpdi();

        // Seiten des eigentlichen Dokuments (Angebot/Auftrag/Rechnung) als
        // Vorlagen importieren, bevor ggf. die Quelldatei gewechselt wird.
        $pageCount = $pdf->setSourceFile($tmpContentFile);
        error_log('[Briefbogen] Seitenzahl Inhalt: ' . $pageCount);
        if ($pageCount < 1) {
            error_log('[Briefbogen] WARNUNG: Inhalts-PDF hat 0 Seiten laut FPDI - Original wird durchgereicht.');
            return $pdfContent;
        }

        $contentTemplateIds = [];
        for ($pageNo = 1; $pageNo <= $pageCount; $pageNo++) {
            $contentTemplateIds[$pageNo] = $pdf->importPage($pageNo);
        }

        // Briefbogen-Vorlage importieren: bei PDF die erste Seite, bei
        // PNG/JPG wird stattdessen einfach das Bild pro Seite platziert.
        $letterheadTemplateId = null;
        if ($isPdfLetterhead) {
            $pdf->setSourceFile($letterheadPath);
            $letterheadTemplateId = $pdf->importPage(1);
        }

        for ($pageNo = 1; $pageNo <= $pageCount; $pageNo++) {
            $size = $pdf->getTemplateSize($contentTemplateIds[$pageNo]);
            error_log(sprintf(
                '[Briefbogen] Seite %d: Breite=%.2f Hoehe=%.2f Ausrichtung=%s',
                $pageNo, $size['width'], $size['height'], $size['orientation']
            ));
            if ($size['width'] < 1 || $size['height'] < 1) {
                error_log('[Briefbogen] WARNUNG: Ungueltige Seitengroesse fuer Seite ' . $pageNo . ' - moegliches Parser-Problem mit dem Inhalts-PDF.');
            }

            $pdf->AddPage($size['orientation'], [$size['width'], $size['height']]);

            // 1. Briefbogen als Hintergrund
            if ($isPdfLetterhead) {
                $pdf->useTemplate($letterheadTemplateId, 0, 0, $size['width'], $size['height']);
            } else {
                $pdf->Image($letterheadPath, 0, 0, $size['width'], $size['height']);
            }

            // 2. Eigentlicher Dokumentinhalt darüber
            $pdf->useTemplate($contentTemplateIds[$pageNo], 0, 0, $size['width'], $size['height']);
        }

        $result = $pdf->Output('S');
        error_log('[Briefbogen] Fertig: Ausgabegroesse=' . strlen($result) . ' Bytes');
        return $result;
    } finally {
        @unlink($tmpContentFile);
    }
}
