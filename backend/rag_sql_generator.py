"""
rag_sql_generator.py
Natural language → MySQL SQL using NVIDIA LLM.
Rules: cumulative CGPA, default USN sort, NLP synonyms, schema memory.
Sprint 2: Kannada language support + complete student profile queries.
"""
from llm_service import llm_service
from database import db_conn
import re
from kannada_processor import normalize_query, build_language_context, is_complete_profile_intent


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
   - village (VARCHAR(100))
   - taluk (VARCHAR(100))
   - district (VARCHAR(100))
   - state (VARCHAR(100))
    - region (VARCHAR(20)) - Rural or Urban classification from uploaded data
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
  4. SELECT only the fields explicitly requested by the user. Do not add s.usn or s.name unless requested or needed to identify a broad student listing.
  5. A specific field request such as phone number, email, address, or father name must select only that field, including an alias if useful. For example, "give Karthik phone number" becomes SELECT s.phone FROM students s WHERE s.name LIKE '%Karthik%'.
  6. "full details", "complete information", or "student profile" intentionally selects s.* and any requested academic fields.
  7. For graduation queries, include: s.student_type, s.admission_year, (s.admission_year + 4) AS graduation_year
  8. Admin: SELECT only. Staff: SELECT, INSERT, UPDATE, DELETE.
  9. Search by name: WHERE s.name LIKE '%<name>%'
  10. Search by USN:  WHERE s.usn = '<usn>'
  11. Query order: WHERE → GROUP BY → HAVING → ORDER BY → LIMIT
  12. Never mix semesters in top-N (always filter by semester first).
  13. DELETE/UPDATE must have WHERE clause.
  14. Never use DROP, TRUNCATE, ALTER, CREATE, GRANT, REVOKE.
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
SQL: SELECT s.usn, s.name, s.father_name, s.mother_name, s.dob, s.blood_group, s.address, s.village, s.district, s.state FROM students s WHERE s.name LIKE '%Manoj%';

Q: give village, district and state of Manoj
SQL: SELECT s.village, s.district, s.state FROM students s WHERE s.name LIKE '%Manoj%';

Q: show details of USN 4HG23CS032
SQL: SELECT s.usn, s.name, s.father_name, s.dob, s.address, s.village, s.district, s.state FROM students s WHERE s.usn = '4HG23CS032';

Q: manoj j r father name
SQL: SELECT s.usn, s.name, s.father_name, s.mother_name, s.dob, s.blood_group, s.phone, s.email FROM students s WHERE s.name LIKE '%Manoj%';

Q: show personal details of all students
SQL: SELECT s.usn, s.name, s.father_name, s.mother_name, s.dob, s.gender, s.blood_group, s.religion, s.caste, s.sub_caste, s.category, s.address, s.permanent_address, s.current_address, s.phone, s.email, s.aadhar_no FROM students s ORDER BY s.name ASC;

Q: show all details of manoj
SQL: SELECT s.* FROM students s WHERE s.name LIKE '%manoj%';

Q: show all details of USN 4HG23CS032
SQL: SELECT s.* FROM students s WHERE s.usn = '4HG23CS032';

Q: show everything about Manoj
SQL: SELECT s.*, m.semester, m.sgpa, ROUND(AVG(m.sgpa) OVER (PARTITION BY m.usn ORDER BY m.semester ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),2) AS cgpa FROM students s LEFT JOIN marks m ON m.usn = s.usn WHERE s.name LIKE '%Manoj%' ORDER BY m.semester ASC;

Q: complete information about Manoj
SQL: SELECT s.*, m.semester, m.sgpa, ROUND(AVG(m.sgpa) OVER (PARTITION BY m.usn ORDER BY m.semester ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),2) AS cgpa FROM students s LEFT JOIN marks m ON m.usn = s.usn WHERE s.name LIKE '%Manoj%' ORDER BY m.semester ASC;

Q: full details of 4HG23CS032
SQL: SELECT s.*, m.semester, m.sgpa, ROUND(AVG(m.sgpa) OVER (PARTITION BY m.usn ORDER BY m.semester ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),2) AS cgpa FROM students s LEFT JOIN marks m ON m.usn = s.usn WHERE s.usn = '4HG23CS032' ORDER BY m.semester ASC;

Q: student profile of Manoj
SQL: SELECT s.*, m.semester, m.sgpa, ROUND(AVG(m.sgpa) OVER (PARTITION BY m.usn ORDER BY m.semester ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),2) AS cgpa FROM students s LEFT JOIN marks m ON m.usn = s.usn WHERE s.name LIKE '%Manoj%' ORDER BY m.semester ASC;

Q: show complete information about Manoj (Kannada: ಮನೋಜ್ ಅವರ ಸಂಪೂರ್ಣ ಮಾಹಿತಿ)
SQL: SELECT s.*, m.semester, m.sgpa, ROUND(AVG(m.sgpa) OVER (PARTITION BY m.usn ORDER BY m.semester ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),2) AS cgpa FROM students s LEFT JOIN marks m ON m.usn = s.usn WHERE s.name LIKE '%Manoj%' ORDER BY m.semester ASC;

Q: show academic details of Manoj (Kannada: Manoj ಅವರ academic details)
SQL: SELECT s.usn, s.name, m.semester, m.sgpa, ROUND(AVG(m.sgpa) OVER (PARTITION BY m.usn ORDER BY m.semester ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),2) AS cgpa FROM students s JOIN marks m ON m.usn = s.usn WHERE s.name LIKE '%Manoj%' ORDER BY m.semester ASC;

Q: show 3rd semester CSE students (Kannada: 3ನೇ semester CSE students)
SQL: SELECT s.usn, s.name, m.semester, m.sgpa FROM students s JOIN marks m ON m.usn = s.usn WHERE m.semester = 3 AND s.usn LIKE '%CS%' ORDER BY s.usn ASC;

Q: show students who graduated in 2024 (Kannada: 2024ರಲ್ಲಿ graduated ಆದ students)
SQL: SELECT s.usn, s.name, s.student_type, s.admission_year, (s.admission_year + 4) AS graduation_year FROM students s WHERE (s.admission_year + 4) = 2024 ORDER BY s.usn ASC;

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

Q: Give only girls names
SQL: SELECT s.name FROM students s WHERE UPPER(s.gender) = 'FEMALE' ORDER BY s.name ASC;

Q: How many students have 8+ CGPA?
SQL: SELECT COUNT(*) AS total_students FROM (SELECT s.usn FROM students s JOIN marks m ON m.usn = s.usn GROUP BY s.usn HAVING AVG(m.sgpa) >= 8.0) AS sub;

Q: Belur
SQL: SELECT DISTINCT s.village, s.taluk, s.district, s.state FROM students s WHERE LOWER(s.village) = 'belur' OR LOWER(s.address) LIKE '%belur%';

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


_RURAL_ADDRESS_PATTERN = r"(^|[^a-z0-9])(village|gram|panchayat|taluk|taluka|tehsil|mandal|rural)([^a-z0-9]|$)"
_URBAN_ADDRESS_PATTERN = r"(^|[^a-z0-9])(urban|city|town|municipal|municipality|corporation|ward|layout|nagar|colony)([^a-z0-9]|$)"


def _address_query(effective_query: str):
    eq = effective_query.strip().lower()
    region_match = re.search(r"\b(rural|urban)\b", eq)
    region_pattern = None
    if region_match:
        region_pattern = _RURAL_ADDRESS_PATTERN if region_match.group(1) == "rural" else _URBAN_ADDRESS_PATTERN

    location_match = re.search(r"\b(?:from|in|at|near)\s+([a-z][a-z .'-]*?)(?:[?.!,;]|$)", eq)
    location = location_match.group(1).strip() if location_match else None
    if location:
        location = re.sub(r"\s+(?:district|taluk|taluka|village|city|town)$", "", location).strip()
        if location in {"rural area", "rural areas", "urban area", "urban areas"}:
            location = None

    if not region_pattern and not location:
        return None

    conditions = []
    params = []
    if region_pattern:
        conditions.append("LOWER(COALESCE(s.address, '')) REGEXP %s")
        params.append(region_pattern)
    if location:
        conditions.append("LOWER(COALESCE(s.address, '')) LIKE %s")
        params.append(f"%{location}%")

    count_query = bool(re.search(r"\b(?:how\s+many|count|number\s+of)\b", eq))
    columns = "COUNT(*) AS total_students" if count_query else "s.usn, s.name, s.address"
    sql = (
        f"SELECT {columns} FROM students s WHERE {' AND '.join(conditions)} "
        + ("" if count_query else "ORDER BY s.usn ASC")
    )
    return sql, params


def _student_lookup_query(effective_query: str):
    eq = effective_query.strip()
    lower_query = eq.lower()
    field_patterns = (
        ("father_name", r"(?:father(?:'s)?|dad(?:'s)?)\s+name"),
        ("mother_name", r"(?:mother(?:'s)?|mom(?:'s)?)\s+name"),
        ("phone", r"(?:phone(?:\s+number)?|mobile(?:\s+number)?)"),
        ("email", r"email(?:\s+address)?"),
        ("address", r"address"),
        ("blood_group", r"blood\s+group"),
        ("dob", r"(?:date\s+of\s+birth|dob|birth\s+date)"),
        ("age", r"age"),
    )
    field_match = None
    selected_field = None
    for column, pattern in field_patterns:
        match = re.search(r"(?:['’]s\s+|\s+)" + pattern + r"\b", lower_query)
        if match:
            field_match = match
            selected_field = column
            break

    usn_match = re.search(r"\b(?=[a-z0-9]*\d)[a-z0-9]{6,}\b", lower_query)
    target = eq[:field_match.start()] if field_match else eq
    if not field_match and not usn_match and not re.search(
        r"\b(?:find|search|show|get|display|look\s+up|details|information|profile)\b", lower_query
    ):
        return None

    target = re.sub(
        r"^\s*(?:(?:what\s+is|find|search(?:\s+for)?|show|get|display|look\s+up|give(?:\s+me)?)\s+)+",
        "",
        target,
        flags=re.I,
    )
    target = re.sub(
        r"^\s*(?:(?:all|complete|full|personal|academic|student)\s+)*(?:details|information|profile)\s+(?:of|for|about)\s+",
        "",
        target,
        flags=re.I,
    )
    target = re.sub(r"\s+(?:(?:personal|complete|full|academic)\s+)?(?:details|information|profile)\s*$", "", target, flags=re.I)
    target = re.sub(r"(?:['’]s|s')\s*$", "", target).strip(" \t\r\n?.!,;:")

    if usn_match:
        identity_sql = "UPPER(s.usn) = %s"
        identity_value = usn_match.group(0).upper()
    elif target:
        identity_sql = "LOWER(TRIM(s.name)) = LOWER(%s)"
        identity_value = target
    else:
        return None

    if selected_field == "age":
        field_sql = "TIMESTAMPDIFF(YEAR, s.dob, CURDATE()) AS age"
    elif selected_field:
        field_sql = f"s.`{selected_field}`"
    else:
        field_sql = "s.*"
    columns = field_sql
    return (
        f"SELECT {columns} FROM students s WHERE {identity_sql} ORDER BY s.usn ASC",
        [identity_value],
    )


def _rule_based_fallback_sql(effective_query: str) -> str | None:
    """Generate deterministic SQL for standard queries when LLM is unavailable or for fast-path queries."""
    eq = effective_query.strip().lower()

    address_query = _address_query(effective_query)
    if address_query:
        return address_query

    if re.search(r"\b(?:how\s+many|count|number\s+of)\b.*\bstudents?\b", eq):
        return "SELECT COUNT(*) AS total_students FROM students"

    if re.search(r'\b(show|list|display|get)?\s*all\s+students\b', eq):
        return "SELECT s.usn, s.name, s.current_sem, s.email, s.phone, s.status FROM students s ORDER BY s.usn ASC"

    student_query = _student_lookup_query(effective_query)
    if student_query:
        return student_query

    # 0a. Girls names: "Give only girls names" / "show female students names"
    if re.search(r'\b(?:give|show|list|get|display)?\s*only\s*(?:girls?|female|women)\s*names?\b|\b(?:girls?|female|women)\s*names?\s*only\b|\b(?:give|show|list|get|display)?\s*(?:girls?|female)\s*names?\b', eq):
        return "SELECT s.name FROM students s WHERE UPPER(s.gender) = 'FEMALE' ORDER BY s.name ASC"

    # 0b. 8+ CGPA count: "How many students have 8+ CGPA?"
    if re.search(r'\bhow\s+many\s+students\b.*\b(?:8\+|8\.0\+|>=?\s*8|greater\s+than\s+(?:or\s+equal\s+to\s+)?8)\s*cgpa\b|\bhow\s+many\s+students\b.*\bcgpa\b.*(?:8\+|8\.0|\b8\b)|\bcount\b.*\b(?:8\+|8\.0)\s*cgpa\b', eq):
        return "SELECT COUNT(*) AS total_students FROM (SELECT s.usn FROM students s JOIN marks m ON m.usn = s.usn GROUP BY s.usn HAVING AVG(m.sgpa) >= 8.0) AS sub"

    # 2. Semester-specific top N: rank by SGPA within the requested semester.
    top_match = re.search(r'\btop\s+(\d+)\s+students\b', eq)
    if top_match:
        n = top_match.group(1)
        until_match = re.search(
            r'\b(?:till|until|upto|through)\s+'
            r'(?:semester\s+|sem\s+)?(\d+)\s*(?:st|nd|rd|th)?\s*(?:semester|sem)?\b'
            r'|\bup\s+to\s+(?:semester\s+|sem\s+)?(\d+)\s*'
            r'(?:st|nd|rd|th)?\s*(?:semester|sem)?\b',
            eq,
            re.I,
        )
        if until_match:
            semester = int(next(group for group in until_match.groups() if group))
            return (
                f"SELECT s.usn, s.name, "
                f"ROUND(AVG(m.sgpa),2) AS cgpa, {semester} AS through_semester "
                f"FROM students s JOIN marks m ON s.usn=m.usn "
                f"WHERE m.semester BETWEEN 1 AND {semester} "
                f"GROUP BY s.usn, s.name "
                f"HAVING COUNT(DISTINCT m.semester) >= {semester} "
                f"ORDER BY cgpa DESC, s.usn ASC LIMIT {n}"
            )

        semester_match = re.search(
            r'\b(?:semester|sem)\s*(?:number\s*)?(\d+)\b'
            r'|\b(\d+)(?:st|nd|rd|th)\s+(?:semester|sem)\b'
            r'|\b(\d+)\s*(?:st|nd|rd|th)?\s+sem\b',
            eq,
            re.I,
        )
        if semester_match:
            semester = next(group for group in semester_match.groups() if group)
            return (
                f"SELECT s.usn, s.name, m.semester, m.sgpa "
                f"FROM students s JOIN marks m ON s.usn=m.usn "
                f"WHERE m.semester = {int(semester)} "
                f"ORDER BY m.sgpa DESC, s.usn ASC LIMIT {n}"
            )

        # General top N: rank each student by overall CGPA across all semesters.
        return f"SELECT s.usn, s.name, ROUND(AVG(m.sgpa),2) AS cgpa FROM students s JOIN marks m ON s.usn=m.usn GROUP BY s.usn, s.name ORDER BY cgpa DESC LIMIT {n}"

    # 3. Student specific queries: "<Name> personal details"
    pers_match = re.search(r'(?:show|give|display)?\s*([a-zA-Z0-9]+)\s+personal\s+details\b', eq)
    if pers_match:
        name = pers_match.group(1)
        return f"SELECT s.usn, s.name, s.father_name, s.mother_name, s.dob, s.gender, s.blood_group, s.address, s.phone, s.email, s.aadhar_no FROM students s WHERE s.name LIKE '%{name}%'"

    # 4. Student specific queries: "<Name> academic details"
    acad_match = re.search(r'(?:show|give|display)?\s*([a-zA-Z0-9]+)\s+academic\s+details\b', eq)
    if acad_match:
        name = acad_match.group(1)
        return f"SELECT s.usn, s.name, m.semester, m.sgpa, ROUND(AVG(m.sgpa) OVER (PARTITION BY m.usn ORDER BY m.semester ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),2) AS cgpa FROM students s JOIN marks m ON m.usn = s.usn WHERE s.name LIKE '%{name}%' ORDER BY m.semester ASC"

    # 5. Student specific queries: "<Name> details" / "give <Name> full details" / "show <Name> information"
    if re.search(r'\b(?:details|information|profile)\b', eq):
        name_clean = re.sub(r'\b(show|give|display|get|full|complete|all|details|information|profile|of|about|for)\b', ' ', eq, flags=re.I).strip()
        if name_clean and len(name_clean) >= 2:
            return f"SELECT s.*, m.semester, m.sgpa, ROUND(AVG(m.sgpa) OVER (PARTITION BY m.usn ORDER BY m.semester ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),2) AS cgpa FROM students s LEFT JOIN marks m ON m.usn = s.usn WHERE s.name LIKE '%{name_clean}%' OR s.usn = '{name_clean.upper()}' ORDER BY m.semester ASC"


    # 6. Single name search: "Karthik"
    if re.fullmatch(r'[a-zA-Z0-9]{2,}', eq):
        return f"SELECT s.*, m.semester, m.sgpa, ROUND(AVG(m.sgpa) OVER (PARTITION BY m.usn ORDER BY m.semester ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),2) AS cgpa FROM students s LEFT JOIN marks m ON m.usn = s.usn WHERE s.name LIKE '%{eq}%' OR s.usn = '{eq.upper()}' ORDER BY m.semester ASC"

    return None


def generate_sql_query(natural_query: str, user_role: str, retry_count: int = 0) -> dict:
    schema = _load_schema_context()

    # Sprint 2: Preprocess Kannada/mixed queries
    normalized_query, lang = normalize_query(natural_query)
    lang_context = build_language_context(natural_query, normalized_query, lang)

    # Use normalized query for SQL generation
    effective_query = normalized_query if normalized_query != natural_query else natural_query

    # Try rule-based matching first for deterministic and high-confidence queries
    fallback_query = _rule_based_fallback_sql(effective_query)
    if fallback_query:
        fallback_sql, fallback_params = fallback_query if isinstance(fallback_query, tuple) else (fallback_query, [])
        return {
            "success": True,
            "sql": fallback_sql,
            "raw": fallback_sql,
            "query_dict": {"operation": "select", "sql": fallback_sql, "params": fallback_params},
            "response_language": lang if 'lang' in locals() else 'english',
        }


    # Prepend language context to prompt if non-English
    schema_with_context = lang_context + schema if lang_context else schema
    prompt = _SYSTEM_PROMPT.format(schema=schema_with_context, query=effective_query, role=user_role)
    raw = llm_service.generate_query(prompt).strip()

    if raw.startswith("ERROR:"):
        if fallback_sql:
            raw = fallback_sql
        else:
            return {"success": False, "error_msg": raw, "sql": None}

    sql = _strip_markdown(raw)

    if not _is_safe_dml(sql):
        if fallback_sql:
            sql = fallback_sql
        elif retry_count < 2:
            return generate_sql_query(
                natural_query + " (Output ONLY a valid SQL — SELECT, INSERT, UPDATE, or DELETE.)",
                user_role, retry_count + 1
            )
        else:
            return {"success": False, "error_msg": "Could not generate a valid SQL query.", "sql": None}

    op = re.match(r'^\s*(\w+)', sql.upper()).group(1).lower()

    # Fix window function ORDER BY (wrap in subquery if needed)
    if op == 'select':
        sql = _fix_window_order(sql)

    return {
        "success": True,
        "sql": sql,
        "raw": sql,
        "query_dict": {"operation": op, "sql": sql},
        "response_language": lang if 'lang' in dir() else 'english',
    }


generate_mongo_query = generate_sql_query
