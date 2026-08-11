from db import get_connection

def validate_row(row: dict) -> list:
    """Return list of validation issues for a single row."""
    issues = []
    usn = row.get("usn", "")

    if not usn or str(usn).strip() == "":
        issues.append({"field": "usn", "issue": "Missing USN", "value": usn})

    for field in ["cgpa", "sgpa"]:
        val = row.get(field)
        if val is not None and str(val).strip() != "":
            try:
                f = float(val)
                if f < 0 or f > 10:
                    issues.append({"field": field, "issue": f"{field.upper()} out of range (0-10)", "value": val})
            except ValueError:
                issues.append({"field": field, "issue": f"Invalid {field.upper()} value", "value": val})

    sem = row.get("semester")
    if sem is not None and str(sem).strip() != "":
        try:
            s = int(sem)
            if s < 1 or s > 10:
                issues.append({"field": "semester", "issue": "Semester out of range (1-10)", "value": sem})
        except ValueError:
            issues.append({"field": "semester", "issue": "Invalid semester value", "value": sem})

    status = row.get("status", "")
    sem_val = row.get("semester")
    if sem_val:
        try:
            if int(sem_val) >= 8 and status and status.upper() != "GRADUATED":
                issues.append({"field": "status", "issue": "Status should be GRADUATED for semester >= 8", "value": status})
        except (ValueError, TypeError):
            pass

    return issues

def log_validation_issues(usn: str, issues: list):
    if not issues:
        return
    log_validation_issues_bulk([(usn, issues)])

def log_validation_issues_bulk(usn_issues: list):
    """usn_issues: list of (usn, issues_list)"""
    rows = []
    for usn, issues in usn_issues:
        for issue in issues:
            rows.append((usn, issue.get("field"), issue.get("issue"), str(issue.get("value", ""))))
    if not rows:
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.executemany("""
        INSERT INTO validation_log (usn, field_name, issue, raw_value)
        VALUES (%s, %s, %s, %s)
    """, rows)
    conn.commit()
    cursor.close()
    conn.close()

def get_validation_report():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM validation_log ORDER BY logged_at DESC LIMIT 500")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def get_duplicate_usns():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT usn, COUNT(*) as cnt
            FROM students_dynamic
            GROUP BY usn
            HAVING COUNT(*) > 1
        """)
        rows = cursor.fetchall()
    except Exception:
        rows = []
    cursor.close()
    conn.close()
    return rows
