import mysql.connector
from mysql.connector import pooling
import os

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "Manoj@123",
    "database": "student_db",
    "autocommit": False,
}

_pool = None

def get_pool():
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name="student_pool",
            pool_size=32,
            pool_reset_session=True,
            host=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
            autocommit=False,
            connection_timeout=30,
        )
    return _pool

def get_connection():
    return get_pool().get_connection()

def init_database():
    """Create database and core tables if they don't exist."""
    # Connect without database first
    conn = mysql.connector.connect(
        host=DB_CONFIG["host"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
    )
    cursor = conn.cursor()
    cursor.execute("CREATE DATABASE IF NOT EXISTS student_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cursor.execute("USE student_db")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_metadata (
            id INT AUTO_INCREMENT PRIMARY KEY,
            table_name VARCHAR(100) NOT NULL,
            column_name VARCHAR(100) NOT NULL,
            data_type VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_table_col (table_name, column_name)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS query_cache (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_query TEXT NOT NULL,
            query_hash VARCHAR(64) NOT NULL UNIQUE,
            sql_query TEXT NOT NULL,
            result_json LONGTEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_hash (query_hash)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS semester_data (
            id INT AUTO_INCREMENT PRIMARY KEY,
            usn VARCHAR(50) NOT NULL,
            semester INT NOT NULL,
            sgpa DECIMAL(4,2),
            cgpa DECIMAL(4,2),
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_usn_sem (usn, semester)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS validation_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            usn VARCHAR(50),
            field_name VARCHAR(100),
            issue VARCHAR(255),
            raw_value TEXT,
            logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    cursor.close()
    conn.close()
    print("[DB] Database and core tables initialized.")
