-- Migration 020: Zahlungsmethoden bei Kunden/Lieferanten, Steuerbefreiung bei Kunden

ALTER TABLE `customers`
  ADD COLUMN `payment_method` ENUM('ueberweisung','lastschrift') NOT NULL DEFAULT 'ueberweisung' AFTER `bank_name`,
  ADD COLUMN `tax_exempt` TINYINT(1) NOT NULL DEFAULT 0 AFTER `payment_method`;

ALTER TABLE `suppliers`
  ADD COLUMN `payment_method` ENUM('ueberweisung','lastschrift','zentralreguliert') NOT NULL DEFAULT 'ueberweisung' AFTER `customer_number_at_supplier`;
