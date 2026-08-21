-- migration_018_account_holder.sql
-- Fügt ein eigenes Feld für den Kontoinhaber hinzu, damit dieser nicht mehr
-- fest im Code (zugferd_builder.php) hinterlegt werden muss.
-- Fällt der Wert leer aus, wird beim ZUGFeRD-Export auf company_name
-- zurückgefallen (siehe includes/zugferd_builder.php).

ALTER TABLE company_settings
    ADD COLUMN account_holder VARCHAR(150) NOT NULL DEFAULT '' AFTER bank_name;
