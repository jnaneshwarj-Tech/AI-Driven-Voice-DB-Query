"""
routes_query.py — Natural language → SQL → execute → return results.
"""
import time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone

from auth import get_current_user
from database_connection import execute_query, execute_write
from llm_service import llm_service
from query_optimizer import optimize_sql
from query_security_validator import validate_sql

router = APIRouter(prefix="/api/query", tags=["Query"])

SCHEMA_CONTEXT = """
Tables:
- students_personal(student_id PK, usn UNIQUE, first_name, last_name, email, phone, address, blood_group, father_name, mother_name)
- students_academic(academic_id PK, student_id FK, department, admission_year, current_semester)
- semester_gpa(gpa_id PK, student_id FK, semester, sgpa, cgpa)
- marks(mark_id PK, student_id FK, semester, subject_name, internal_marks, external_marks, total_marks)
- users(id, username, email, role)
- query_history(id, user_role, natural_query, generated_sql, execution_time, timestamp)

Relationships: students_personal.student_id → students_academic, semester_gpa, marks
"""

class QueryRequest(BaseModel):
    natural_query: str

class ExecuteRequest(BaseModel):
    sql: str
    original_query: str

def _generate_sql(natural_query: str, user_role: str) -> str:
    prompt = f"""You are an expert MySQL query generator for a college student database.

{SCHEMA_CONTEXT}

RULES:
- Return ONLY the raw SQL query, no markdown, no explanation.
- Use JOIN across tables when needed.
- User role: "{user_role}". Admin = SELECT only. Staff = SELECT/INSERT/UPDATE/DELETE.
- Always use WHERE clause for UPDATE and DELETE.
- Never use DROP, TRUNCATE, ALTER, CREATE.
- For full student details, JOIN all 4 tables.

USER QUERY: {natural_query}

SQL:"""
    return llm_service.generate(prompt)

@router.post("/generate")
def generate_query(req: QueryRequest, current_user: dict = Depends(get_current_user)):
    start = time.time()
    raw_sql = _generate_sql(req.natural_query, current_user['role'])

    if raw_sql.startswith("ERROR:"):
        raise HTTPException(500, raw_sql)

    sql = optimize_sql(raw_sql)
    validation = validate_sql(sql, current_user['role'])

    if not validation['is_valid']:
        execute_write(
            "INSERT INTO security_logs (user_role, attempted_sql, reason) VALUES (%s,%s,%s)",
            (current_user['role'], sql, validation['reason'])
        )
        raise HTTPException(403, f"Security Alert: {validation['reason']}")

    op = sql.strip().upper().split()[0]
    op = sql.strip().upper().split()[0]
    is_read = op == "SELECT"

    if current_user['role'] == 'Admin' and not is_read:
        raise HTTPException(403, "Admin role cannot execute write operations.")

    try:
        if is_read:
            data = execute_query(sql)
            message = "Query executed successfully."
        else:
            affected = execute_write(sql)
            data = [{"affected_rows": affected}]
            message = "Operation executed successfully."
            
        elapsed = time.time() - start
        execute_write(
            "INSERT INTO query_history (user_role, natural_query, generated_sql, execution_time) VALUES (%s,%s,%s,%s)",
            (current_user['role'], req.natural_query, sql, elapsed)
        )
        return {"action_required": "none", "sql": sql, "data": data, "execution_time": elapsed, "message": message}
    except Exception as e:
        raise HTTPException(400, f"Query error: {e}")

@router.post("/execute")
def execute_confirmed(req: ExecuteRequest, current_user: dict = Depends(get_current_user)):
    if current_user['role'] == 'Admin':
        raise HTTPException(403, "Admin role cannot execute write operations.")
    start = time.time()
    validation = validate_sql(req.sql, current_user['role'])
    if not validation['is_valid']:
        raise HTTPException(403, f"Security Alert: {validation['reason']}")
    try:
        affected = execute_write(req.sql)
        elapsed = time.time() - start
        execute_write(
            "INSERT INTO query_history (user_role, natural_query, generated_sql, execution_time) VALUES (%s,%s,%s,%s)",
            (current_user['role'], req.original_query, req.sql, elapsed)
        )
        return {"success": True, "affected_rows": affected, "message": "Operation executed successfully."}
    except Exception as e:
        raise HTTPException(400, f"Execution error: {e}")

@router.get("/history")
def get_history(limit: int = 10, current_user: dict = Depends(get_current_user)):
    return execute_query(
        "SELECT * FROM query_history ORDER BY timestamp DESC LIMIT %s", (limit,)
    )
