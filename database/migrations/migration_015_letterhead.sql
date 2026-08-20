-- =====================================================
-- Migration 015: Briefbogen (Hintergrundvorlage fuer PDFs)
-- =====================================================

ALTER TABLE company_settings
    ADD COLUMN letterhead_path VARCHAR(255) DEFAULT NULL AFTER logo_path;
