-- ============================================================
-- Password Reset System Migration
-- ============================================================
-- This script adds/updates the password_reset_requests table
-- for the OTP-based password reset system.
--
-- Run this ONCE to update your existing database:
-- mysql -u root -p student_db < migration_password_reset.sql
-- ============================================================

USE student_db;

-- Drop old table if it exists (rename first for safety)
DROP TABLE IF EXISTS password_reset_tokens_old;
RENAME TABLE password_reset_tokens TO password_reset_tokens_old;

-- Create new password_reset_requests table
CREATE TABLE IF NOT EXISTS password_reset_requests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    otp_hash CHAR(64) NOT NULL,
    otp_created_at DATETIME NOT NULL,
    otp_expires_at DATETIME NOT NULL,
    otp_used_at DATETIME DEFAULT NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    reset_token_hash CHAR(64) DEFAULT NULL,
    reset_token_expires_at DATETIME DEFAULT NULL,
    reset_token_used_at DATETIME DEFAULT NULL,
    created_ip VARCHAR(60) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_user_id (user_id),
    INDEX idx_otp_hash (otp_hash),
    INDEX idx_reset_token_hash (reset_token_hash),
    INDEX idx_otp_expires (otp_expires_at),
    INDEX idx_created_at (created_at),
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Add theme column to users table if it doesn't exist
ALTER TABLE users ADD COLUMN IF NOT EXISTS theme VARCHAR(20) DEFAULT 'system';

-- Add unique constraint on email if it doesn't exist
-- (This prevents duplicate email accounts as required by the specification)
ALTER TABLE users ADD UNIQUE INDEX idx_email_unique (email);

-- Verify the migration
SELECT 'Migration completed successfully!' AS status;
SELECT COUNT(*) AS user_count FROM users;
SELECT COUNT(*) AS reset_request_count FROM password_reset_requests;

-- ============================================================
-- Cleanup Script (Optional - Run after verifying system works)
-- ============================================================
-- DROP TABLE IF EXISTS password_reset_tokens_old;
-- ============================================================
