"""
rag_sql_generator.py
Natural language → MySQL SQL using NVIDIA LLM.
Uses schema_metadata for context. CGPA is always AVG(sgpa).
"""
from llm_service import llm_service
from database import get_db_connection
import re


def _load_schema_context() -> str:
    """Load live schema from schema_metadata table."""
    try:
        conn = get_db_connection()
        cur  = conn.cursor(dictionary=True)
        cur.execute("SELECT table_name, column_name, data_type FROM schema_metadata ORDER BY table_name, id")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        if not rows:
            return _STATIC_SCHEMA
        tables: dict[str, list] = {}
        for r in rows:
            tables.setdefault(r["table_name"], []).append(f"   - {r['column_name']} ({r['data_type']})")
        lines = ["Tables in student_db:\n"]
        for tbl, cols in tables.items():
            lines.append(f"{tbl}:")
            lines.extend(cols)
            lines.append("")
        lines.append("NOTE: CGPA is NEVER stored. Always compute as AVG(sgpa) from marks table.")
        return "\n".join(lines)
    except Exception:
        return _STATIC_SCHEMA


_STATIC_SCHEMA = """
Tables in student_db:

students:
   - usn (VARCHAR(20)) PRIMARY KEY
   - name (VARCHAR(150))
   - dob (DATE)
   - year_of_joining (INT)
   - current_sem (INT)
   - status (VARCHAR(20))

marks:
   - id (INT) PRIMARY KEY
   - usn (VARCHAR(20)) FK → students.usn
   - semester (INT)
   - sgpa (DECIMAL(4,2))
   - year (INT)

NOTE: CGPA is NEVER stored. Always compute as AVG(sgpa) from marks table.
NOTE: Do NOT select father_name, mother_name, blood_group, address unless explicitly asked.
"""

_SYSTEM_PROMPT = """You are an expert MySQL query generator for a college student database.

{schema}

Role: {role}

STRICT RULES:
1. Output ONLY a raw SQL statement — no explanation, no markdown, no code fences.
2. Aliases: students AS s, marks AS m.
3. JOIN marks: JOIN marks m ON m.usn = s.usn
4. SELECT must include s.usn, s.name at minimum.
5. Admin: SELECT only. Staff: SELECT, INSERT, UPDATE, DELETE.
6. Search by name: WHERE s.name LIKE '%<name>%'
7. Search by USN: WHERE s.usn = '<usn>'
8. CGPA = ROUND(AVG(m.sgpa),2) — NEVER use a stored cgpa column.
9. Query order: WHERE → GROUP BY → ORDER BY → LIMIT
10. Never mix semesters in top-N queries (always filter by semester first).
11. DELETE/UPDATE must have WHERE clause.
12. Never use DROP, TRUNCATE, ALTER, CREATE, GRANT, REVOKE.

EXAMPLES:
Q: Show all students
SQL: SELECT s.usn, s.name, s.current_sem, s.status FROM students s ORDER BY s.name;

Q: Show GPA of all students
SQL: SELECT s.usn, s.name, m.semester, m.sgpa, ROUND(AVG(m.sgpa) OVER (PARTITION BY s.usn),2) AS cgpa FROM students s JOIN marks m ON m.usn = s.usn ORDER BY s.name, m.semester;

Q: Show details of Manoj
SQL: SELECT s.usn, s.name, m.semester, m.sgpa FROM students s JOIN marks m ON m.usn = s.usn WHERE s.name LIKE '%Manoj%' ORDER BY m.semester;

Q: Show details of USN 4HG23CS001
SQL: SELECT s.usn, s.name, m.semester, m.sgpa FROM students s JOIN marks m ON m.usn = s.usn WHERE s.usn = '4HG23CS001' ORDER BY m.semester;

Q: Top 10 students of 3rd semester
SQL: SELECT s.usn, s.name, m.semester, m.sgpa FROM students s JOIN marks m ON m.usn = s.usn WHERE m.semester = 3 ORDER BY m.sgpa DESC LIMIT 10;

Q: CGPA of all students
SQL: SELECT s.usn, s.name, ROUND(AVG(m.sgpa),2) AS cgpa FROM students s JOIN marks m ON m.usn = s.usn GROUP BY s.usn, s.name ORDER BY cgpa DESC;

Q: Compare students in semester 2
SQL: SELECT s.usn, s.name, m.semester, m.sgpa FROM students s JOIN marks m ON m.usn = s.usn WHERE m.semester = 2 ORDER BY m.sgpa DESC;

Q: Show uploaded files
SQL: SELECT filename, file_type, size_bytes, uploaded_by, uploaded_at, db_status FROM uploaded_files ORDER BY uploaded_at DESC;

Q: Add student USN 4HG23CS099 name Ravi Kumar
SQL: INSERT INTO students (usn, name) VALUES ('4HG23CS099', 'Ravi Kumar');

Q: Delete student USN 4HG23CS099
SQL: DELETE FROM students WHERE usn = '4HG23CS099';

Q: Update name of USN 4HG23CS001 to Ravi Shankar
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
    return {"success": True, "sql": sql, "raw": sql, "query_dict": {"operation": op, "sql": sql}}


# backward-compat alias
generate_mongo_query = generate_sql_query
