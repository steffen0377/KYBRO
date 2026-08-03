-- Migration 014: Rate-Limiting für api/auth.php
CREATE TABLE IF NOT EXISTS api_login_attempts (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) NOT NULL,
    ip_address VARCHAR(45) NOT NULL,
    success TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_lookup (username, ip_address, created_at)
) ENGINE=InnoDB;
