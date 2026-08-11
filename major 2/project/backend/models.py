import re
from db import get_connection
from schema_memory import register_column

MAIN_TABLE = "students_dynamic"

INFERRED_TYPES = {
    "usn": "VARCHAR(50)",
    "name": "VARCHAR(150)",
    "email": "VARCHAR(150)",
    "phone": "VARCHAR(20)",
    "dob": "DATE",
    "gender": "VARCHAR(10)",
    "branch": "VARCHAR(100)",
    "department": "VARCHAR(100)",
    "cgpa": "DECIMAL(4,2)",
    "sgpa": "DECIMAL(4,2)",
    "semester": "INT",
    "year": "INT",
    "status": "VARCHAR(30)",
    "address": "TEXT",
    "city": "VARCHAR(100)",
    "state": "VARCHAR(100)",
    "pincode": "VARCHAR(10)",
    "marks": "DECIMAL(6,2)",
    "percentage": "DECIMAL(5,2)",
    "attendance": "DECIMAL(5,2)",
    "age": "INT",
    "batch": "VARCHAR(20)",
    "section": "VARCHAR(10)",
}

def normalize_column(col: str) -> str:
    col = col.strip().lower()
    col = re.sub(r"[^a-z0-9_]", "_", col)
    col = re.sub(r"_+", "_", col).strip("_")
    return col

def infer_sql_type(col_name: str, sample_value=None) -> str:
    for key, dtype in INFERRED_TYPES.items():
        if key in col_name:
            return dtype
    if sample_value is not None:
        try:
            int(sample_value)
            return "INT"
        except (ValueError, TypeError):
            pass
        try:
            float(sample_value)
            return "DECIMAL(10,2)"
        except (ValueError, TypeError):
            pass
    return "TEXT"

def ensure_table_exists(columns: list):
    """Create students_dynamic if not exists with given columns."""
    conn = get_connection()
    cursor = conn.cursor()

    # Always ensure usn is first
    if "usn" not in columns:
        columns = ["usn"] + columns

    col_defs = ["id INT AUTO_INCREMENT PRIMARY KEY"]
    for col in columns:
        dtype = infer_sql_type(col)
        if col == "usn":
            col_defs.append(f"`{col}` VARCHAR(50) NOT NULL")
        else:
            col_defs.append(f"`{col}` {dtype}")

    col_defs.append("UNIQUE KEY uq_usn (usn)")
    col_defs.append("updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")

    ddl = f"CREATE TABLE IF NOT EXISTS `{MAIN_TABLE}` ({', '.join(col_defs)})"
    cursor.execute(ddl)
    conn.commit()

    # Register in schema_metadata
    for col in columns:
        register_column(MAIN_TABLE, col, infer_sql_type(col))
    register_column(MAIN_TABLE, "updated_at", "TIMESTAMP")

    cursor.close()
    conn.close()

def get_existing_columns() -> list:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"SHOW COLUMNS FROM `{MAIN_TABLE}`")
        cols = [row[0] for row in cursor.fetchall()]
    except Exception:
        cols = []
    cursor.close()
    conn.close()
    return cols

def add_missing_columns(new_columns: list, sample_row: dict = None):
    """ALTER TABLE to add any columns not yet present."""
    existing = get_existing_columns()
    conn = get_connection()
    cursor = conn.cursor()
    for col in new_columns:
        if col not in existing:
            sample_val = sample_row.get(col) if sample_row else None
            dtype = infer_sql_type(col, sample_val)
            cursor.execute(f"ALTER TABLE `{MAIN_TABLE}` ADD COLUMN `{col}` {dtype}")
            register_column(MAIN_TABLE, col, dtype)
            print(f"[Schema] Added column `{col}` ({dtype})")
    conn.commit()
    cursor.close()
    conn.close()

def upsert_student(row: dict):
    """Insert or update a student row. Never overwrite with NULL."""
    if not row.get("usn"):
        return
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Filter out None/empty values for update
    clean = {k: v for k, v in row.items() if v is not None and str(v).strip() != ""}

    if "usn" not in clean:
        cursor.close()
        conn.close()
        return

    cols = list(clean.keys())
    vals = [clean[c] for c in cols]
    placeholders = ", ".join(["%s"] * len(cols))
    col_names = ", ".join([f"`{c}`" for c in cols])

    # ON DUPLICATE KEY UPDATE — skip NULLs
    update_parts = [f"`{c}` = IF(VALUES(`{c}`) IS NOT NULL AND VALUES(`{c}`) != '', VALUES(`{c}`), `{c}`)"
                    for c in cols if c != "usn"]

    if update_parts:
        sql = f"""
            INSERT INTO `{MAIN_TABLE}` ({col_names})
            VALUES ({placeholders})
            ON DUPLICATE KEY UPDATE {', '.join(update_parts)}
        """
    else:
        sql = f"INSERT IGNORE INTO `{MAIN_TABLE}` ({col_names}) VALUES ({placeholders})"

    cursor.execute(sql, vals)
    conn.commit()
    cursor.close()
    conn.close()
