-- migration_023_subscriptions.sql
-- Fügt Abonnement-Verkauf (Einmalkauf/monatlich/jährlich) für Artikel sowie
-- Abo-Verwaltung inkl. Kündigungslogik und automatisierter Entwurfs-Rechnungen ein.

-- 1) Verkaufsmodelle pro Artikel: ein Artikel kann mehrere Preisoptionen
--    besitzen, aus denen bei der Bestellung gewählt wird.
CREATE TABLE `article_pricing_options` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `article_id` int(11) NOT NULL,
  `billing_type` enum('einmalig','monatlich','jaehrlich') NOT NULL DEFAULT 'einmalig',
  `price` decimal(10,2) NOT NULL DEFAULT 0.00,
  `min_runtime_months` int(11) DEFAULT NULL COMMENT 'Mindestlaufzeit in Monaten, nur bei Abo relevant',
  `notice_period_days` int(11) DEFAULT NULL COMMENT 'Kündigungsfrist in Tagen, nur bei Abo relevant',
  `is_active` tinyint(1) NOT NULL DEFAULT 1,
  `sort_order` int(11) NOT NULL DEFAULT 0,
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_article` (`article_id`),
  CONSTRAINT `fk_apo_article` FOREIGN KEY (`article_id`) REFERENCES `articles` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2) Gewähltes Verkaufsmodell je Position (Snapshot, da sich die
--    article_pricing_options später ändern können).
ALTER TABLE `offer_items`
  ADD COLUMN `pricing_option_id` int(11) DEFAULT NULL AFTER `article_id`,
  ADD COLUMN `billing_type` enum('einmalig','monatlich','jaehrlich') NOT NULL DEFAULT 'einmalig' AFTER `pricing_option_id`,
  ADD KEY `idx_offer_items_pricing_option` (`pricing_option_id`),
  ADD CONSTRAINT `fk_offer_items_pricing_option` FOREIGN KEY (`pricing_option_id`) REFERENCES `article_pricing_options` (`id`) ON DELETE SET NULL;

ALTER TABLE `order_items`
  ADD COLUMN `pricing_option_id` int(11) DEFAULT NULL AFTER `article_id`,
  ADD COLUMN `billing_type` enum('einmalig','monatlich','jaehrlich') NOT NULL DEFAULT 'einmalig' AFTER `pricing_option_id`,
  ADD KEY `idx_order_items_pricing_option` (`pricing_option_id`),
  ADD CONSTRAINT `fk_order_items_pricing_option` FOREIGN KEY (`pricing_option_id`) REFERENCES `article_pricing_options` (`id`) ON DELETE SET NULL;

ALTER TABLE `invoice_items`
  ADD COLUMN `pricing_option_id` int(11) DEFAULT NULL AFTER `article_id`,
  ADD COLUMN `billing_type` enum('einmalig','monatlich','jaehrlich') NOT NULL DEFAULT 'einmalig' AFTER `pricing_option_id`,
  ADD KEY `idx_invoice_items_pricing_option` (`pricing_option_id`),
  ADD CONSTRAINT `fk_invoice_items_pricing_option` FOREIGN KEY (`pricing_option_id`) REFERENCES `article_pricing_options` (`id`) ON DELETE SET NULL;

-- 3) Rechnungen: Verknüpfung zu einem Abo sowie Leistungszeitraum für
--    automatisch erzeugte Folgerechnungen (auch für ZUGFeRD BT-134/BT-135 nutzbar).
ALTER TABLE `invoices`
  ADD COLUMN `subscription_id` int(11) DEFAULT NULL AFTER `order_id`,
  ADD COLUMN `period_start` date DEFAULT NULL AFTER `service_date`,
  ADD COLUMN `period_end` date DEFAULT NULL AFTER `period_start`,
  ADD KEY `idx_invoices_subscription` (`subscription_id`);

-- 4) Abo-Verwaltung: Laufzeit, nächster Abrechnungstermin, Kündigungslogik.
CREATE TABLE `subscriptions` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `customer_id` int(11) NOT NULL,
  `article_id` int(11) NOT NULL,
  `pricing_option_id` int(11) DEFAULT NULL,
  `order_id` int(11) DEFAULT NULL,
  `origin_invoice_id` int(11) DEFAULT NULL COMMENT 'Rechnung, mit der das Abo begründet wurde',
  `billing_cycle` enum('monatlich','jaehrlich') NOT NULL,
  `price` decimal(10,2) NOT NULL DEFAULT 0.00,
  `start_date` date NOT NULL,
  `next_billing_date` date NOT NULL,
  `end_date` date DEFAULT NULL,
  `min_runtime_months` int(11) DEFAULT NULL,
  `notice_period_days` int(11) DEFAULT NULL,
  `earliest_cancellation_date` date DEFAULT NULL COMMENT 'Frühestmögliches Vertragsende laut Mindestlaufzeit',
  `status` enum('aktiv','gekuendigt','beendet') NOT NULL DEFAULT 'aktiv',
  `cancellation_requested_date` date DEFAULT NULL,
  `cancellation_effective_date` date DEFAULT NULL,
  `notes` text DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_sub_customer` (`customer_id`),
  KEY `idx_sub_article` (`article_id`),
  KEY `idx_sub_pricing_option` (`pricing_option_id`),
  KEY `idx_sub_order` (`order_id`),
  KEY `idx_sub_status_billing` (`status`,`next_billing_date`),
  CONSTRAINT `fk_sub_customer` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`),
  CONSTRAINT `fk_sub_article` FOREIGN KEY (`article_id`) REFERENCES `articles` (`id`),
  CONSTRAINT `fk_sub_pricing_option` FOREIGN KEY (`pricing_option_id`) REFERENCES `article_pricing_options` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_sub_order` FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_sub_origin_invoice` FOREIGN KEY (`origin_invoice_id`) REFERENCES `invoices` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Rückwirkend erst jetzt möglich, da subscriptions.id nun existiert.
ALTER TABLE `invoices`
  ADD CONSTRAINT `fk_invoices_subscription` FOREIGN KEY (`subscription_id`) REFERENCES `subscriptions` (`id`) ON DELETE SET NULL;
