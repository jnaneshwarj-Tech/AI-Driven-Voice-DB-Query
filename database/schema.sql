-- ============================================================
-- Student Data Management System - Complete MySQL Schema
-- ============================================================

CREATE DATABASE IF NOT EXISTS student_db;
USE student_db;

-- Users (Authentication)
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('Admin','Staff') DEFAULT 'Staff',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Students (core entity)
CREATE TABLE IF NOT EXISTS students (
    usn VARCHAR(20) PRIMARY KEY,
    name VARCHAR(150),
    dob DATE,
    year_of_joining INT,
    current_sem INT DEFAULT 1,
    father_name VARCHAR(150),
    mother_name VARCHAR(150),
    blood_group VARCHAR(5),
    address TEXT,
    status VARCHAR(20) DEFAULT 'ACTIVE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Marks (per semester SGPA only — CGPA is always computed as AVG(sgpa))
CREATE TABLE IF NOT EXISTS marks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usn VARCHAR(20) NOT NULL,
    semester INT NOT NULL,
    sgpa DECIMAL(4,2),
    year INT,
    UNIQUE KEY uq_usn_sem (usn, semester),
    FOREIGN KEY (usn) REFERENCES students(usn) ON DELETE CASCADE
);

-- Uploaded files metadata
CREATE TABLE IF NOT EXISTS uploaded_files (
    id INT AUTO_INCREMENT PRIMARY KEY,
    filename VARCHAR(255) UNIQUE NOT NULL,
    content_type VARCHAR(100),
    file_type VARCHAR(20),
    size_bytes INT,
    uploaded_by VARCHAR(100),
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    db_status VARCHAR(20) DEFAULT 'pending',
    row_count INT DEFAULT 0,
    students_saved INT DEFAULT 0,
    marks_saved INT DEFAULT 0,
    gpa_rows INT DEFAULT 0
);

-- Schema memory (AI uses this to generate SQL)
CREATE TABLE IF NOT EXISTS schema_metadata (
    id INT AUTO_INCREMENT PRIMARY KEY,
    table_name VARCHAR(100) NOT NULL,
    column_name VARCHAR(100) NOT NULL,
    data_type VARCHAR(50),
    is_primary_key TINYINT(1) DEFAULT 0,
    is_foreign_key TINYINT(1) DEFAULT 0,
    UNIQUE KEY uq_table_col (table_name, column_name)
);

-- Query cache
CREATE TABLE IF NOT EXISTS query_cache (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_query VARCHAR(500) NOT NULL,
    sql_query TEXT NOT NULL,
    result_json LONGTEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_user_query (user_query(255))
);

-- Query history
CREATE TABLE IF NOT EXISTS query_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_role VARCHAR(20),
    natural_query TEXT,
    generated_query TEXT,
    execution_time FLOAT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Security logs
CREATE TABLE IF NOT EXISTS security_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_role VARCHAR(20),
    attempted_query TEXT,
    reason TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Deletion logs (activity tracking)
CREATE TABLE IF NOT EXISTS deletion_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usn VARCHAR(20),
    student_name VARCHAR(150),
    deleted_by VARCHAR(100),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Addition logs (activity tracking)
CREATE TABLE IF NOT EXISTS addition_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usn VARCHAR(20),
    student_name VARCHAR(150),
    added_by VARCHAR(100),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Soft-delete store — deleted students live here until permanently purged
CREATE TABLE IF NOT EXISTS soft_deleted_students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usn VARCHAR(20) NOT NULL,
    student_json LONGTEXT NOT NULL,   -- full students row as JSON
    marks_json   LONGTEXT,            -- all marks rows as JSON array
    deleted_by   VARCHAR(100),
    deleted_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    restore_token CHAR(36) NOT NULL,  -- UUID for safe restore
    restored     TINYINT(1) DEFAULT 0,
    INDEX idx_usn (usn),
    INDEX idx_token (restore_token)
);

-- Student change history (version control)
CREATE TABLE IF NOT EXISTS student_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usn VARCHAR(20) NOT NULL,
    field_name VARCHAR(100),
    old_value TEXT,
    new_value TEXT,
    updated_by VARCHAR(100),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_usn (usn)
);

-- ── Seed schema_metadata ──────────────────────────────────────────────────────
INSERT IGNORE INTO schema_metadata (table_name, column_name, data_type, is_primary_key, is_foreign_key) VALUES
('students','usn','VARCHAR(20)',1,0),
('students','name','VARCHAR(150)',0,0),
('students','dob','DATE',0,0),
('students','year_of_joining','INT',0,0),
('students','current_sem','INT',0,0),
('students','father_name','VARCHAR(150)',0,0),
('students','mother_name','VARCHAR(150)',0,0),
('students','blood_group','VARCHAR(5)',0,0),
('students','address','TEXT',0,0),
('students','status','VARCHAR(20)',0,0),
('marks','id','INT',1,0),
('marks','usn','VARCHAR(20)',0,1),
('marks','semester','INT',0,0),
('marks','sgpa','DECIMAL(4,2)',0,0),
('marks','year','INT',0,0);
