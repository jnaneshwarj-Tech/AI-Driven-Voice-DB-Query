"""
database.py — MySQL connection pool + schema bootstrap
"""
import mysql.connector
from mysql.connector import pooling
from config import settings

db_pool = None

def init_pool():
    global db_pool
    try:
        db_pool = pooling.MySQLConnectionPool(
            pool_name="mypool",
            pool_size=10,
            pool_reset_session=True,
            host=settings.MYSQL_HOST,
            port=settings.MYSQL_PORT,
            user=settings.MYSQL_USER,
            password=settings.MYSQL_PASSWORD,
            database=settings.MYSQL_DB,
            connection_timeout=10,
        )
        print("✅ MySQL connection pool initialized.")
    except Exception as e:
        print(f"❌ Pool creation failed: {e}")

def get_db_connection():
    global db_pool
    if not db_pool:
        init_pool()
    return db_pool.get_connection()

def _add_col_if_missing(cur, table, col, dtype):
    cur.execute(f"SHOW COLUMNS FROM {table} LIKE '{col}'")
    if not cur.fetchone():
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {dtype}")
        print(f"  Migrated: {table}.{col} {dtype}")


def create_indexes():
    """Run once at startup — create tables and indexes."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # ── Core tables ──────────────────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role ENUM('Admin','Staff') DEFAULT 'Staff',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # students — create only if not exists (existing table may have student_id as PK)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS students (
                student_id INT AUTO_INCREMENT PRIMARY KEY,
                usn VARCHAR(20) UNIQUE,
                name VARCHAR(150),
                dob DATE,
                year_of_joining INT,
                current_sem INT DEFAULT 1,
                status VARCHAR(20) DEFAULT 'ACTIVE',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """)

        # Migrate: add columns that may be missing from older installs
        _add_col_if_missing(cur, "students", "father_name", "VARCHAR(150)")
        _add_col_if_missing(cur, "students", "mother_name", "VARCHAR(150)")
        _add_col_if_missing(cur, "students", "blood_group", "VARCHAR(5)")
        _add_col_if_missing(cur, "students", "address",     "TEXT")
        _add_col_if_missing(cur, "marks",    "cgpa",        "DECIMAL(4,2)")
        _add_col_if_missing(cur, "marks",    "year",        "INT")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS marks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                usn VARCHAR(20) NOT NULL,
                semester INT NOT NULL,
                sgpa DECIMAL(4,2),
                cgpa DECIMAL(4,2),
                year INT,
                UNIQUE KEY uq_usn_sem (usn, semester)
            )
        """)

        cur.execute("""
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
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_metadata (
                id INT AUTO_INCREMENT PRIMARY KEY,
                table_name VARCHAR(100) NOT NULL,
                column_name VARCHAR(100) NOT NULL,
                data_type VARCHAR(50),
                is_primary_key TINYINT(1) DEFAULT 0,
                is_foreign_key TINYINT(1) DEFAULT 0,
                UNIQUE KEY uq_table_col (table_name, column_name)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS query_cache (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_query VARCHAR(500) NOT NULL,
                sql_query TEXT NOT NULL,
                result_json LONGTEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uq_user_query (user_query(255))
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS query_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_role VARCHAR(20),
                natural_query TEXT,
                generated_query TEXT,
                execution_time FLOAT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS security_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_role VARCHAR(20),
                attempted_query TEXT,
                reason TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ── Seed schema_metadata ─────────────────────────────────────────────
        # Add missing columns if schema_metadata was created without them
        cur.execute("SHOW COLUMNS FROM schema_metadata LIKE 'is_primary_key'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE schema_metadata ADD COLUMN is_primary_key TINYINT(1) DEFAULT 0")
            cur.execute("ALTER TABLE schema_metadata ADD COLUMN is_foreign_key TINYINT(1) DEFAULT 0")

        seed = [
            ('students','usn','VARCHAR(20)',1,0),
            ('students','name','VARCHAR(150)',0,0),
            ('students','dob','DATE',0,0),
            ('students','year_of_joining','INT',0,0),
            ('students','current_sem','INT',0,0),
            ('students','status','VARCHAR(20)',0,0),
            ('marks','id','INT',1,0),
            ('marks','usn','VARCHAR(20)',0,1),
            ('marks','semester','INT',0,0),
            ('marks','sgpa','DECIMAL(4,2)',0,0),
            ('marks','year','INT',0,0),
        ]
        cur.executemany(
            "INSERT IGNORE INTO schema_metadata (table_name,column_name,data_type,is_primary_key,is_foreign_key) VALUES (%s,%s,%s,%s,%s)",
            seed
        )

        conn.commit()
        cur.close()
        conn.close()
        print("✅ Tables and schema_metadata ready.")
    except Exception as e:
        print(f"⚠️  create_indexes error: {e}")
