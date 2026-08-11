"""
database.py — MySQL connection pool + schema bootstrap.
Uses context manager pattern to guarantee connections are always returned to pool.
"""
import mysql.connector
from mysql.connector import pooling
from contextlib import contextmanager
from config import settings

db_pool = None
db_init_error = None

def init_pool():
    global db_pool, db_init_error
    try:
        db_pool = pooling.MySQLConnectionPool(
            pool_name="mypool",
            pool_size=20,               # increased from 10
            pool_reset_session=True,
            host=settings.MYSQL_HOST,
            port=settings.MYSQL_PORT,
            user=settings.MYSQL_USER,
            password=settings.MYSQL_PASSWORD,
            database=settings.MYSQL_DB,
            connection_timeout=10,
        )
        db_init_error = None
        print("[OK] MySQL connection pool initialized (size=20).")
    except Exception as e:
        db_init_error = e
        db_pool = None
        print(f"[ERR] Pool creation failed: {e}")

def get_db_connection():
    """Get a raw connection from the pool. Caller MUST call conn.close() to return it."""
    global db_pool, db_init_error
    if not db_pool:
        init_pool()
    if not db_pool:
        error_msg = (
            f"Failed to connect to MySQL server at {settings.MYSQL_HOST}:{settings.MYSQL_PORT}. "
            "Please ensure that the MySQL service is running and credentials in your .env are correct. "
            f"Underlying error: {db_init_error}"
        )
        raise RuntimeError(error_msg)
    return db_pool.get_connection()

@contextmanager
def db_conn():
    """
    Context manager — always returns connection to pool even on exception.
    Usage:
        with db_conn() as conn:
            cur = conn.cursor(dictionary=True)
            ...
    """
    conn = get_db_connection()
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass

def _add_col_if_missing(cur, table, col, dtype):
    cur.execute(f"SHOW COLUMNS FROM `{table}` LIKE '{col}'")
    if not cur.fetchone():
        cur.execute(f"ALTER TABLE `{table}` ADD COLUMN `{col}` {dtype}")
        print(f"  Migrated: {table}.{col} {dtype}")


def create_indexes():
    """Run once at startup — create tables, migrate schema."""
    try:
        with db_conn() as conn:
            cur = conn.cursor()

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

            cur.execute("""
                CREATE TABLE IF NOT EXISTS students (
                    student_id INT AUTO_INCREMENT PRIMARY KEY,
                    usn VARCHAR(100) UNIQUE,
                    name VARCHAR(150),
                    dob DATE,
                    year_of_joining INT,
                    current_sem INT DEFAULT 1,
                    status VARCHAR(20) DEFAULT 'ACTIVE',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """)

            _add_col_if_missing(cur, "students", "father_name",       "VARCHAR(150)")
            _add_col_if_missing(cur, "students", "mother_name",       "VARCHAR(150)")
            _add_col_if_missing(cur, "students", "blood_group",       "VARCHAR(5)")
            _add_col_if_missing(cur, "students", "address",           "TEXT")
            _add_col_if_missing(cur, "students", "gender",            "VARCHAR(10)")
            _add_col_if_missing(cur, "students", "religion",          "VARCHAR(50)")
            _add_col_if_missing(cur, "students", "caste",             "VARCHAR(100)")
            _add_col_if_missing(cur, "students", "sub_caste",         "VARCHAR(100)")
            _add_col_if_missing(cur, "students", "category",          "VARCHAR(20)")
            _add_col_if_missing(cur, "students", "permanent_address", "TEXT")
            _add_col_if_missing(cur, "students", "current_address",   "TEXT")
            _add_col_if_missing(cur, "students", "phone",             "VARCHAR(20)")
            _add_col_if_missing(cur, "students", "email",             "VARCHAR(255)")
            _add_col_if_missing(cur, "students", "aadhar_no",         "VARCHAR(20)")
            _add_col_if_missing(cur, "students", "year_and_branch",   "VARCHAR(100)")
            _add_col_if_missing(cur, "students", "source_file",       "VARCHAR(255)")
            _add_col_if_missing(cur, "students", "admission_year",    "INT")
            _add_col_if_missing(cur, "students", "current_year",      "INT")
            _add_col_if_missing(cur, "students", "student_type",      "VARCHAR(50)")
            _add_col_if_missing(cur, "students", "estimated_semester","INT")
            _add_col_if_missing(cur, "students", "branch",            "VARCHAR(50)")
            _add_col_if_missing(cur, "students", "division",          "VARCHAR(50)")
            _add_col_if_missing(cur, "students", "domain",            "VARCHAR(100)")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS marks (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    usn VARCHAR(100) NOT NULL,
                    semester INT NOT NULL,
                    sgpa DECIMAL(4,2),
                    cgpa DECIMAL(4,2),
                    year INT,
                    UNIQUE KEY uq_usn_sem (usn, semester)
                )
            """)

            _add_col_if_missing(cur, "marks", "cgpa", "DECIMAL(4,2)")
            _add_col_if_missing(cur, "marks", "year", "INT")

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

            cur.execute("""
                CREATE TABLE IF NOT EXISTS addition_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    usn VARCHAR(100),
                    student_name VARCHAR(150),
                    added_by VARCHAR(100),
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS deletion_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    usn VARCHAR(100),
                    student_name VARCHAR(150),
                    deleted_by VARCHAR(100),
                    restore_token CHAR(36),
                    restored TINYINT(1) DEFAULT 0,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            _add_col_if_missing(cur, "deletion_logs", "restore_token", "CHAR(36)")
            _add_col_if_missing(cur, "deletion_logs", "restored", "TINYINT(1) DEFAULT 0")

            # ── Undo / Soft-delete tables ─────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS soft_deleted_students (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    usn VARCHAR(100) NOT NULL,
                    student_json LONGTEXT NOT NULL,
                    marks_json   LONGTEXT,
                    deleted_by   VARCHAR(100),
                    deleted_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    restore_token CHAR(36) NOT NULL,
                    restored     TINYINT(1) DEFAULT 0,
                    INDEX idx_usn (usn),
                    INDEX idx_token (restore_token)
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS student_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    usn VARCHAR(100) NOT NULL,
                    field_name VARCHAR(100),
                    old_value TEXT,
                    new_value TEXT,
                    updated_by VARCHAR(100),
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_usn (usn)
                )
            """)

            # Theme column on users table
            _add_col_if_missing(cur, "users", "theme", "VARCHAR(20) DEFAULT 'system'")

            # global_undo_snapshots table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS global_undo_snapshots (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    undo_token VARCHAR(100) UNIQUE NOT NULL,
                    operation_type VARCHAR(50) NOT NULL,
                    snapshot_data LONGTEXT NOT NULL,
                    performed_by VARCHAR(100),
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    description TEXT,
                    undone TINYINT(1) DEFAULT 0,
                    committed TINYINT(1) DEFAULT 0,
                    post_state_data LONGTEXT,
                    undone_by VARCHAR(100),
                    undone_at TIMESTAMP NULL
                )
            """)

            # Rollback snapshots are written inside the same transaction as the
            # mutation.  These migrations keep existing Sprint 1 databases safe.
            _add_col_if_missing(cur, "global_undo_snapshots", "committed", "TINYINT(1) DEFAULT 0")
            _add_col_if_missing(cur, "global_undo_snapshots", "post_state_data", "LONGTEXT")
            _add_col_if_missing(cur, "global_undo_snapshots", "undone_by", "VARCHAR(100)")
            _add_col_if_missing(cur, "global_undo_snapshots", "undone_at", "TIMESTAMP NULL")

            # export_logs table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS export_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    format VARCHAR(20) NOT NULL,
                    record_count INT,
                    exported_by VARCHAR(100),
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ── Sprint 1: Backup metadata table ─────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS db_backups (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    backup_name VARCHAR(255) UNIQUE NOT NULL,
                    backup_path TEXT NOT NULL,
                    backup_type ENUM('manual','auto_daily','auto_weekly','pre_restore') DEFAULT 'manual',
                    size_bytes BIGINT DEFAULT 0,
                    status ENUM('running','success','failed','verified') DEFAULT 'running',
                    verified TINYINT(1) DEFAULT 0,
                    created_by VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP NULL,
                    error_message TEXT,
                    record_count INT DEFAULT 0
                )
            """)

            # ── Sprint 1: Enterprise audit log ───────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(100),
                    role VARCHAR(20),
                    action VARCHAR(80) NOT NULL,
                    target_table VARCHAR(100),
                    target_id VARCHAR(200),
                    summary TEXT,
                    success TINYINT(1) DEFAULT 1,
                    error_info TEXT,
                    ip_address VARCHAR(60),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_al_username (username),
                    INDEX idx_al_action (action),
                    INDEX idx_al_created_at (created_at)
                )
            """)

            # ── Sprint 1: Upload version / snapshot history ───────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS upload_versions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    filename VARCHAR(255),
                    rows_parsed INT DEFAULT 0,
                    students_added INT DEFAULT 0,
                    students_updated INT DEFAULT 0,
                    students_unchanged INT DEFAULT 0,
                    marks_added INT DEFAULT 0,
                    marks_updated INT DEFAULT 0,
                    skipped_rows INT DEFAULT 0,
                    status ENUM('success','failed','rolled_back') DEFAULT 'success',
                    undo_token VARCHAR(100),
                    performed_by VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    error_message TEXT,
                    INDEX idx_uv_created_at (created_at),
                    INDEX idx_uv_status (status)
                )
            """)

            # ── Sprint 1: Performance indexes ─────────────────────────────────────
            _add_index_if_missing(cur, 'students', 'idx_stu_name',        'name(50)')
            _add_index_if_missing(cur, 'students', 'idx_stu_status',      'status')
            _add_index_if_missing(cur, 'students', 'idx_stu_yr_joining',  'year_of_joining')
            _add_index_if_missing(cur, 'students', 'idx_stu_adm_year',    'admission_year')
            _add_index_if_missing(cur, 'students', 'idx_stu_cur_sem',     'current_sem')
            _add_index_if_missing(cur, 'marks',    'idx_marks_semester',  'semester')
            _add_index_if_missing(cur, 'marks',    'idx_marks_sgpa',      'sgpa')
            _add_index_if_missing(cur, 'query_history', 'idx_qh_ts',      'timestamp')
            _add_index_if_missing(cur, 'global_undo_snapshots', 'idx_gus_ts', 'timestamp')
            _add_index_if_missing(cur, 'global_undo_snapshots', 'idx_gus_op', 'operation_type')

            # schema_metadata migration
            cur.execute("SHOW COLUMNS FROM schema_metadata LIKE 'is_primary_key'")
            if not cur.fetchone():
                cur.execute("ALTER TABLE schema_metadata ADD COLUMN is_primary_key TINYINT(1) DEFAULT 0")
                cur.execute("ALTER TABLE schema_metadata ADD COLUMN is_foreign_key TINYINT(1) DEFAULT 0")

            seed = [
                ('students','usn','VARCHAR(100)',1,0),
                ('students','name','VARCHAR(150)',0,0),
                ('students','dob','DATE',0,0),
                ('students','year_of_joining','INT',0,0),
                ('students','current_sem','INT',0,0),
                ('students','status','VARCHAR(20)',0,0),
                ('students','admission_year','INT',0,0),
                ('students','current_year','INT',0,0),
                ('students','student_type','VARCHAR(50)',0,0),
                ('students','estimated_semester','INT',0,0),
                ('students','father_name','VARCHAR(150)',0,0),
                ('students','mother_name','VARCHAR(150)',0,0),
                ('students','blood_group','VARCHAR(5)',0,0),
                ('students','gender','VARCHAR(10)',0,0),
                ('students','religion','VARCHAR(50)',0,0),
                ('students','caste','VARCHAR(100)',0,0),
                ('students','sub_caste','VARCHAR(100)',0,0),
                ('students','category','VARCHAR(20)',0,0),
                ('students','address','TEXT',0,0),
                ('students','permanent_address','TEXT',0,0),
                ('students','current_address','TEXT',0,0),
                ('students','phone','VARCHAR(20)',0,0),
                ('students','email','VARCHAR(255)',0,0),
                ('students','aadhar_no','VARCHAR(20)',0,0),
                ('students','year_and_branch','VARCHAR(100)',0,0),
                ('marks','id','INT',1,0),
                ('marks','usn','VARCHAR(100)',0,1),
                ('marks','semester','INT',0,0),
                ('marks','sgpa','DECIMAL(4,2)',0,0),
                ('marks','year','INT',0,0),
            ]
            cur.executemany(
                "INSERT IGNORE INTO schema_metadata "
                "(table_name,column_name,data_type,is_primary_key,is_foreign_key) VALUES (%s,%s,%s,%s,%s)",
                seed
            )

            conn.commit()
            cur.close()
        print("[OK] Tables, indexes, and schema_metadata ready.")
    except Exception as e:
        print(f"[WARN] create_indexes error: {e}")


def _add_index_if_missing(cur, table: str, index_name: str, columns: str):
    """Create an index only if it does not already exist."""
    try:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.statistics "
            "WHERE table_schema=DATABASE() AND table_name=%s AND index_name=%s",
            (table, index_name)
        )
        row = cur.fetchone()
        count = row[0] if isinstance(row, (list, tuple)) else list(row.values())[0]
        if count == 0:
            cur.execute(f"CREATE INDEX `{index_name}` ON `{table}` ({columns})")
            print(f"  Index created: {table}.{index_name}")
    except Exception as e:
        print(f"  [WARN] Index {index_name} on {table}: {e}")


def write_audit_log(
    action: str,
    username: str = "system",
    role: str = "",
    target_table: str = "",
    target_id: str = "",
    summary: str = "",
    success: bool = True,
    error_info: str = "",
    ip_address: str = "",
):
    """
    Fire-and-forget audit log writer.
    Never raises — always logs silently to prevent disrupting main operations.
    """
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO audit_log
                  (username, role, action, target_table, target_id,
                   summary, success, error_info, ip_address)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    username[:100] if username else "system",
                    role[:20] if role else "",
                    action[:80],
                    target_table[:100] if target_table else "",
                    target_id[:200] if target_id else "",
                    summary[:1000] if summary else "",
                    1 if success else 0,
                    error_info[:1000] if error_info else "",
                    ip_address[:60] if ip_address else "",
                )
            )
            conn.commit()
            cur.close()
    except Exception:
        pass  # Audit log must never crash the main operation
