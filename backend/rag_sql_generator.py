"""
rag_sql_generator.py
Natural language → MySQL SQL using NVIDIA LLM.
Rules: cumulative CGPA, default USN sort, NLP synonyms, schema memory.
"""
from llm_service import llm_service
from database import db_conn
import re


def _load_schema_context() -> str:
    try:
        with db_conn() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT table_name, column_name, data_type "
                "FROM schema_metadata ORDER BY table_name, id"
            )
            rows = cur.fetchall()
            cur.close()
        if not rows:
            return _STATIC_SCHEMA
        tables: dict[str, list] = {}
        for r in rows:
            tables.setdefault(r["table_name"], []).append(
                f"   - {r['column_name']} ({r['data_type']})"
            )
        lines = ["Tables in student_db:\n"]
        for tbl, cols in tables.items():
            lines.append(f"{tbl}:")
            lines.extend(cols)
            lines.append("")
        lines.append("RULE: CGPA = cumulative AVG(sgpa) per semester using window function.")
        lines.append("RULE: Default sort = ORDER BY s.usn ASC unless user specifies otherwise.")
        return "\n".join(lines)
    except Exception:
        return _STATIC_SCHEMA


_STATIC_SCHEMA = """
Tables in student_db:

students:
   - usn (VARCHAR(100)) PRIMARY KEY
   - name (VARCHAR(150))
   - dob (DATE)
   - year_of_joining (INT)
   - current_sem (INT)
   - status (VARCHAR(20))
   - admission_year (INT) - Actual admission batch (corrected for lateral entry)
   - current_year (INT) - Current academic year (1-4)
   - student_type (VARCHAR(50)) - "Regular" or "Lateral Entry"
   - estimated_semester (INT) - Current semester calculated from USN
   - father_name (VARCHAR(150))
   - mother_name (VARCHAR(150))
   - blood_group (VARCHAR(5))
   - gender (VARCHAR(10))
   - religion (VARCHAR(50))
   - caste (VARCHAR(100))
   - sub_caste (VARCHAR(100))
   - category (VARCHAR(20))
   - address (TEXT)
   - permanent_address (TEXT)
   - current_address (TEXT)
   - phone (VARCHAR(20))
   - email (VARCHAR(255))
   - aadhar_no (VARCHAR(20))
   - year_and_branch (VARCHAR(100))

marks:
   - id (INT) PRIMARY KEY
   - usn (VARCHAR(100)) FK → students.usn
   - semester (INT)
   - sgpa (DECIMAL(4,2))
   - year (INT)

RULE: CGPA = cumulative AVG(sgpa) per semester using window function.
RULE: Default sort = ORDER BY s.usn ASC unless user specifies otherwise.
RULE: Graduation Year = admission_year + 4
RULE: Graduation Status = 'GRADUATED' if YEAR(CURDATE()) >= (admission_year + 4), else 'ACTIVE'
RULE: Never permanently store graduation_status - always calculate dynamically.
"""

_SYSTEM_PROMPT = """You are an expert MySQL query generator for a college student database.

{schema}

Role: {role}

═══════════════════════════════════════════════════════
NLP SYNONYM RULES (apply regardless of case):
  "show/give/display/list/get"  → SELECT
  "top/highest/best/first/rank" → ORDER BY ... DESC
  "lowest/last/worst/bottom"    → ORDER BY ... ASC
  "cgpa wise"                   → ORDER BY cgpa DESC
  "sgpa wise"                   → ORDER BY sgpa DESC
  "name order/alphabetical"     → ORDER BY s.name ASC
  "usn order"                   → ORDER BY s.usn ASC
  "year wise"                   → ORDER BY year_of_joining
  
GRADUATION QUERY SYNONYMS:
  "graduated/graduates/alumni/passed out/completed degree/graduation list/who graduated"
    → WHERE YEAR(CURDATE()) >= (s.admission_year + 4)
  "active students/current students/enrolled/studying"
    → WHERE YEAR(CURDATE()) < (s.admission_year + 4)
  "2024 graduates/graduated in 2024"
    → WHERE (s.admission_year + 4) = 2024
  "2023 admission batch/admitted in 2023"
    → WHERE s.admission_year = 2023
  "lateral entry students"
    → WHERE s.student_type = 'Lateral Entry'
  "regular students"
    → WHERE s.student_type = 'Regular'

DEFAULT SORT RULE (MANDATORY):
  If user does NOT specify sorting → always add: ORDER BY s.usn ASC

CGPA CALCULATION RULE (MANDATORY):
  CGPA = cumulative average of SGPA up to each semester.
  Use window function:
    ROUND(AVG(m.sgpa) OVER (PARTITION BY m.usn ORDER BY m.semester
          ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS cgpa
  NEVER use a stored cgpa column.
  NEVER return only final CGPA unless user explicitly asks for "final cgpa" or "overall cgpa".
  Default = show semester-wise with cumulative CGPA per row.

GRADUATION CALCULATION RULES:
  - Graduation Year = admission_year + 4 (always)
  - Graduation Status: Calculate dynamically using:
    CASE WHEN YEAR(CURDATE()) >= (s.admission_year + 4) THEN 'GRADUATED' ELSE 'ACTIVE' END
  - NEVER filter by s.status for graduation queries
  - admission_year is the CORRECTED admission batch (includes lateral entry adjustment)

QUERY STRUCTURE RULES:
  1. Output ONLY raw SQL — no markdown, no explanation, no code fences.
  2. Aliases: students AS s, marks AS m.
  3. JOIN CONDITIONAL: Only JOIN marks m ON m.usn = s.usn IF academic details (sgpa, cgpa, semester, marks) are requested. If the user asks for personal details ONLY (father name, mother name, dob, etc.), query ONLY the students table.
  4. SELECT must include s.usn, s.name at minimum.
  5. For graduation queries, include: s.student_type, s.admission_year, (s.admission_year + 4) AS graduation_year
  6. Admin: SELECT only. Staff: SELECT, INSERT, UPDATE, DELETE.
  7. Search by name: WHERE s.name LIKE '%<name>%'
  8. Search by USN:  WHERE s.usn = '<usn>'
  9. Query order: WHERE → GROUP BY → HAVING → ORDER BY → LIMIT
  10. Never mix semesters in top-N (always filter by semester first).
  11. DELETE/UPDATE must have WHERE clause.
  12. Never use DROP, TRUNCATE, ALTER, CREATE, GRANT, REVOKE.
═══════════════════════════════════════════════════════

EXAMPLES:

Q: show all students
SQL: SELECT s.usn, s.name, s.student_type, s.admission_year, s.current_year, CASE WHEN YEAR(CURDATE()) >= (s.admission_year + 4) THEN 'GRADUATED' ELSE 'ACTIVE' END AS graduation_status FROM students s ORDER BY s.usn ASC;

Q: show graduated students
SQL: SELECT s.usn, s.name, s.student_type, s.admission_year, (s.admission_year + 4) AS graduation_year FROM students s WHERE YEAR(CURDATE()) >= (s.admission_year + 4) ORDER BY s.usn ASC;

Q: show graduates
SQL: SELECT s.usn, s.name, s.student_type, s.admission_year, (s.admission_year + 4) AS graduation_year FROM students s WHERE YEAR(CURDATE()) >= (s.admission_year + 4) ORDER BY s.usn ASC;

Q: show alumni
SQL: SELECT s.usn, s.name, s.student_type, s.admission_year, (s.admission_year + 4) AS graduation_year FROM students s WHERE YEAR(CURDATE()) >= (s.admission_year + 4) ORDER BY s.usn ASC;

Q: passed out students
SQL: SELECT s.usn, s.name, s.student_type, s.admission_year, (s.admission_year + 4) AS graduation_year FROM students s WHERE YEAR(CURDATE()) >= (s.admission_year + 4) ORDER BY s.usn ASC;

Q: show 2024 graduates
SQL: SELECT s.usn, s.name, s.student_type, s.admission_year, (s.admission_year + 4) AS graduation_year FROM students s WHERE (s.admission_year + 4) = 2024 ORDER BY s.usn ASC;

Q: show 2025 graduation list
SQL: SELECT s.usn, s.name, s.student_type, s.admission_year, (s.admission_year + 4) AS graduation_year FROM students s WHERE (s.admission_year + 4) = 2025 ORDER BY s.usn ASC;

Q: show active students
SQL: SELECT s.usn, s.name, s.student_type, s.admission_year, s.current_year, s.current_sem FROM students s WHERE YEAR(CURDATE()) < (s.admission_year + 4) ORDER BY s.usn ASC;

Q: show 2023 admission batch
SQL: SELECT s.usn, s.name, s.student_type, s.admission_year, s.current_year FROM students s WHERE s.admission_year = 2023 ORDER BY s.usn ASC;

Q: show lateral entry students
SQL: SELECT s.usn, s.name, s.student_type, s.admission_year, (s.admission_year + 4) AS graduation_year FROM students s WHERE s.student_type = 'Lateral Entry' ORDER BY s.usn ASC;

Q: show Computer Science graduates
SQL: SELECT s.usn, s.name, s.student_type, s.admission_year, (s.admission_year + 4) AS graduation_year FROM students s WHERE s.usn LIKE '%CS%' AND YEAR(CURDATE()) >= (s.admission_year + 4) ORDER BY s.usn ASC;

Q: show marks / gpa of all students
SQL: SELECT s.usn, s.name, m.semester, m.sgpa, ROUND(AVG(m.sgpa) OVER (PARTITION BY m.usn ORDER BY m.semester ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),2) AS cgpa FROM students s JOIN marks m ON m.usn = s.usn ORDER BY s.usn ASC, m.semester ASC;

Q: show details of Manoj
SQL: SELECT s.usn, s.name, s.father_name, s.mother_name, s.dob, s.blood_group, s.address FROM students s WHERE s.name LIKE '%Manoj%';

Q: show details of USN 4HG23CS032
SQL: SELECT s.usn, s.name, s.father_name, s.dob, s.address FROM students s WHERE s.usn = '4HG23CS032';

Q: manoj j r father name
SQL: SELECT s.usn, s.name, s.father_name, s.mother_name, s.dob, s.blood_group, s.phone, s.email FROM students s WHERE s.name LIKE '%Manoj%';

Q: show personal details of all students
SQL: SELECT s.usn, s.name, s.father_name, s.mother_name, s.dob, s.gender, s.blood_group, s.religion, s.caste, s.sub_caste, s.category, s.address, s.permanent_address, s.current_address, s.phone, s.email, s.aadhar_no FROM students s ORDER BY s.name ASC;

Q: show all details of manoj
SQL: SELECT s.* FROM students s WHERE s.name LIKE '%manoj%';

Q: show all details of USN 4HG23CS032
SQL: SELECT s.* FROM students s WHERE s.usn = '4HG23CS032';

Q: top 10 students of 3rd semester
SQL: SELECT s.usn, s.name, m.semester, m.sgpa FROM students s JOIN marks m ON m.usn = s.usn WHERE m.semester = 3 ORDER BY m.sgpa DESC LIMIT 10;

Q: top 10 students of 4th semester cgpa wise
SQL: SELECT s.usn, s.name, m.semester, m.sgpa FROM students s JOIN marks m ON m.usn = s.usn WHERE m.semester = 4 ORDER BY m.sgpa DESC LIMIT 10;

Q: top 5 students cgpa wise
SQL: SELECT s.usn, s.name, ROUND(AVG(m.sgpa),2) AS cgpa FROM students s JOIN marks m ON m.usn = s.usn GROUP BY s.usn, s.name ORDER BY cgpa DESC LIMIT 5;

Q: show students name order
SQL: SELECT s.usn, s.name, m.semester, m.sgpa, ROUND(AVG(m.sgpa) OVER (PARTITION BY m.usn ORDER BY m.semester ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),2) AS cgpa FROM students s JOIN marks m ON m.usn = s.usn ORDER BY s.name ASC, m.semester ASC;

Q: compare students in semester 2
SQL: SELECT s.usn, s.name, m.semester, m.sgpa FROM students s JOIN marks m ON m.usn = s.usn WHERE m.semester = 2 ORDER BY m.sgpa DESC;

Q: overall cgpa of all students
SQL: SELECT s.usn, s.name, ROUND(AVG(m.sgpa),2) AS cgpa FROM students s JOIN marks m ON m.usn = s.usn GROUP BY s.usn, s.name ORDER BY s.usn ASC;

Q: show uploaded files
SQL: SELECT filename, file_type, size_bytes, uploaded_by, uploaded_at, db_status FROM uploaded_files ORDER BY uploaded_at DESC;

Q: add student USN 4HG23CS099 name Ravi Kumar
SQL: INSERT INTO students (usn, name) VALUES ('4HG23CS099', 'Ravi Kumar');

Q: delete student USN 4HG23CS099
SQL: DELETE FROM students WHERE usn = '4HG23CS099';

Q: update name of USN 4HG23CS001 to Ravi Shankar
SQL: UPDATE students SET name = 'Ravi Shankar' WHERE usn = '4HG23CS001';

USER QUERY: {query}

SQL:"""


def _strip_markdown(raw: str) -> str:
    for fence in ("```sql", "```"):
        if fence in raw:
            parts = raw.split(fence)
            if len(parts) > 1:
                return parts[1].split("```")[0].strip()
    return raw.strip()


ALLOWED_OPS = {"SELECT", "INSERT", "UPDATE", "DELETE"}


def _is_safe_dml(sql: str) -> bool:
    m = re.match(r'^\s*(\w+)', sql)
    return bool(m) and m.group(1).upper() in ALLOWED_OPS


def _fix_window_order(sql: str) -> str:
    """
    If SQL uses a window function alias (cgpa/sgpa) in ORDER BY,
    MySQL requires wrapping in a subquery.
    Detects pattern and wraps automatically.
    """
    sql_upper = sql.upper()
    # Check if it has a window function (OVER) AND orders by the alias
    has_window = 'OVER' in sql_upper and ('PARTITION BY' in sql_upper or 'ORDER BY' in sql_upper)
    if not has_window:
        return sql

    # Check if ORDER BY references a window alias (cgpa or sgpa at end)
    # Pattern: ORDER BY cgpa DESC or ORDER BY sgpa DESC at the outermost level
    order_match = re.search(
        r'\bORDER\s+BY\s+(cgpa|sgpa)\s*(DESC|ASC)?\s*(?:LIMIT\s+\d+\s*)?$',
        sql, re.IGNORECASE
    )
    if not order_match:
        return sql

    # Wrap in subquery so ORDER BY can reference the window alias
    order_col   = order_match.group(1)
    order_dir   = order_match.group(2) or 'DESC'
    # Extract LIMIT if present
    limit_match = re.search(r'\bLIMIT\s+(\d+)\s*$', sql, re.IGNORECASE)
    limit_clause = f" LIMIT {limit_match.group(1)}" if limit_match else ""

    # Strip the ORDER BY (and LIMIT) from the inner query
    inner = re.sub(
        r'\s+ORDER\s+BY\s+(cgpa|sgpa)\s*(DESC|ASC)?\s*(?:LIMIT\s+\d+\s*)?$',
        '', sql, flags=re.IGNORECASE
    ).strip().rstrip(';')

    wrapped = (
        f"SELECT * FROM ({inner}) AS sub "
        f"ORDER BY {order_col} {order_dir}{limit_clause};"
    )
    return wrapped


def generate_sql_query(natural_query: str, user_role: str, retry_count: int = 0) -> dict:
    schema = _load_schema_context()
    prompt = _SYSTEM_PROMPT.format(schema=schema, query=natural_query, role=user_role)
    raw = llm_service.generate_query(prompt).strip()

    if raw.startswith("ERROR:"):
        return {"success": False, "error_msg": raw, "sql": None}

    sql = _strip_markdown(raw)

    if not _is_safe_dml(sql):
        if retry_count < 2:
            return generate_sql_query(
                natural_query + " (Output ONLY a valid SQL — SELECT, INSERT, UPDATE, or DELETE.)",
                user_role, retry_count + 1
            )
        return {"success": False, "error_msg": "Could not generate a valid SQL query.", "sql": None}

    op = re.match(r'^\s*(\w+)', sql.upper()).group(1).lower()

    # Fix window function ORDER BY (wrap in subquery if needed)
    if op == 'select':
        sql = _fix_window_order(sql)

    return {"success": True, "sql": sql, "raw": sql, "query_dict": {"operation": op, "sql": sql}}


generate_mongo_query = generate_sql_query
