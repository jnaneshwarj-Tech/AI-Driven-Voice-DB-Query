import os
import json
import threading
import pandas as pd
from models import normalize_column, ensure_table_exists, add_missing_columns, MAIN_TABLE, infer_sql_type
from validation import validate_row, log_validation_issues_bulk
from cache import clear_cache
from db import get_connection
from schema_memory import register_column

_lock = threading.Lock()

def _read_file(filepath: str) -> pd.DataFrame:
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".csv":
        df = pd.read_csv(filepath, dtype=str, keep_default_na=False)
    elif ext in (".xlsx", ".xls"):
        df = pd.read_excel(filepath, dtype=str, keep_default_na=False)
    elif ext == ".json":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            df = pd.DataFrame(data).astype(str)
        elif isinstance(data, dict):
            df = pd.DataFrame([data]).astype(str)
        else:
            raise ValueError("Unsupported JSON structure")
    elif ext == ".pdf":
        df = _read_pdf(filepath)
    else:
        raise ValueError(f"Unsupported file type: {ext}")
    return df

def _read_pdf(filepath: str) -> pd.DataFrame:
    try:
        import pdfplumber
        rows = []
        headers = None
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if not headers and table:
                        headers = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(table[0])]
                        for row in table[1:]:
                            rows.append([str(c).strip() if c else "" for c in row])
                    elif headers:
                        for row in table:
                            rows.append([str(c).strip() if c else "" for c in row])
        if headers and rows:
            return pd.DataFrame(rows, columns=headers).astype(str)
    except ImportError:
        pass
    raise ValueError("PDF parsing requires pdfplumber. Install with: pip install pdfplumber")

def process_file(filepath: str) -> dict:
    """Main entry: read file, normalize, upsert all rows. Thread-safe."""
    with _lock:
        df = _read_file(filepath)

        # Normalize column names
        df.columns = [normalize_column(c) for c in df.columns]
        df = df.loc[:, ~df.columns.duplicated()]

        columns = list(df.columns)
        sample_row = df.iloc[0].to_dict() if len(df) > 0 else {}

        ensure_table_exists(columns)
        add_missing_columns(columns, sample_row)

        has_semester_cols = "semester" in columns and ("sgpa" in columns or "cgpa" in columns)

        inserted = 0
        updated = 0
        errors = []
        all_validation_issues = []

        # ── Single connection for the entire batch ──────────────────────────
        conn = get_connection()
        try:
            cursor = conn.cursor(dictionary=True)

            # Fetch all existing USNs in one query
            cursor.execute(f"SELECT usn FROM `{MAIN_TABLE}`")
            existing_usns = {r["usn"] for r in cursor.fetchall()}
            cursor.close()

            semester_rows = []

            for _, row_series in df.iterrows():
                row = {
                    k: (None if str(v).strip() in ("", "nan", "None", "NaN") else str(v).strip())
                    for k, v in row_series.items()
                }

                issues = validate_row(row)
                if issues:
                    all_validation_issues.append((row.get("usn", ""), issues))

                # Auto-set GRADUATED
                sem = row.get("semester")
                if sem:
                    try:
                        if int(sem) >= 8:
                            row["status"] = "GRADUATED"
                    except (ValueError, TypeError):
                        pass

                usn = row.get("usn")
                if not usn:
                    continue

                try:
                    _upsert_row(conn, row)
                    if usn in existing_usns:
                        updated += 1
                    else:
                        inserted += 1
                        existing_usns.add(usn)

                    if has_semester_cols and sem:
                        semester_rows.append((usn, row))
                except Exception as e:
                    errors.append(str(e))
                    conn.rollback()

            # Bulk upsert semester data
            if semester_rows:
                _bulk_upsert_semester(conn, semester_rows)

            conn.commit()
        finally:
            conn.close()

        # Log validation issues (uses its own short-lived connection)
        if all_validation_issues:
            log_validation_issues_bulk(all_validation_issues)

        clear_cache()

        return {
            "total_rows": len(df),
            "inserted": inserted,
            "updated": updated,
            "errors": errors[:10],
            "validation_issues": sum(len(v) for _, v in all_validation_issues),
            "columns": columns,
        }

def _upsert_row(conn, row: dict):
    """Insert or update using the shared connection."""
    clean = {k: v for k, v in row.items() if v is not None and str(v).strip() != ""}
    if "usn" not in clean:
        return

    cols = list(clean.keys())
    vals = [clean[c] for c in cols]
    placeholders = ", ".join(["%s"] * len(cols))
    col_names = ", ".join([f"`{c}`" for c in cols])

    update_parts = [
        f"`{c}` = IF(VALUES(`{c}`) IS NOT NULL AND VALUES(`{c}`) != '', VALUES(`{c}`), `{c}`)"
        for c in cols if c != "usn"
    ]

    if update_parts:
        sql = f"""
            INSERT INTO `{MAIN_TABLE}` ({col_names})
            VALUES ({placeholders})
            ON DUPLICATE KEY UPDATE {', '.join(update_parts)}
        """
    else:
        sql = f"INSERT IGNORE INTO `{MAIN_TABLE}` ({col_names}) VALUES ({placeholders})"

    cursor = conn.cursor()
    cursor.execute(sql, vals)
    cursor.close()

def _bulk_upsert_semester(conn, semester_rows: list):
    """Batch insert semester data using the shared connection."""
    cursor = conn.cursor()
    sql = """
        INSERT INTO semester_data (usn, semester, sgpa, cgpa)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            sgpa = IF(VALUES(sgpa) IS NOT NULL, VALUES(sgpa), sgpa),
            cgpa = IF(VALUES(cgpa) IS NOT NULL, VALUES(cgpa), cgpa)
    """
    batch = []
    for usn, row in semester_rows:
        sem = row.get("semester")
        sgpa = row.get("sgpa")
        cgpa = row.get("cgpa")
        if sem:
            try:
                batch.append((
                    usn,
                    int(sem),
                    float(sgpa) if sgpa else None,
                    float(cgpa) if cgpa else None,
                ))
            except (ValueError, TypeError):
                pass
    if batch:
        cursor.executemany(sql, batch)
    cursor.close()
