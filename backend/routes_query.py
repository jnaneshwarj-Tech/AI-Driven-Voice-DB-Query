"""
routes_query.py — AI query engine with caching, CGPA dynamic calc, role-based access.
"""
import json, time
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from database import get_db_connection
from auth import get_current_user
from rag_sql_generator import generate_sql_query
from query_security_validator import validate_sql_query

router = APIRouter(prefix="/api/query", tags=["Query Engine"])


class QueryRequest(BaseModel):
    natural_query: str


class ExecuteRequest(BaseModel):
    query_dict: dict
    original_query: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize_row(row: dict) -> dict:
    clean = {}
    for k, v in row.items():
        if v is None:
            clean[k] = None
        elif hasattr(v, 'isoformat'):
            clean[k] = v.isoformat()
        else:
            clean[k] = v
    return clean


def _run_query(query_dict: dict) -> list:
    op  = query_dict.get("operation", "").lower()
    sql = query_dict.get("sql", "")
    if not sql:
        raise ValueError("Missing SQL.")

    conn = get_db_connection()
    try:
        if op == "select":
            cur = conn.cursor(dictionary=True)
            cur.execute(sql)
            return [_serialize_row(r) for r in cur.fetchall()]
        else:
            cur = conn.cursor()
            cur.execute(sql)
            conn.commit()
            return [{"affected_rows": cur.rowcount}]
    finally:
        conn.close()


def _get_cache(natural_query: str):
    try:
        conn = get_db_connection()
        cur  = conn.cursor(dictionary=True)
        cur.execute("SELECT sql_query, result_json FROM query_cache WHERE user_query=%s", (natural_query[:255],))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row and row.get("result_json"):
            return row["sql_query"], json.loads(row["result_json"])
    except Exception:
        pass
    return None, None


def _set_cache(natural_query: str, sql: str, result: list):
    try:
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO query_cache (user_query, sql_query, result_json) VALUES (%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE sql_query=%s, result_json=%s, created_at=NOW()",
            (natural_query[:255], sql, json.dumps(result), sql, json.dumps(result))
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass


def _log_history(role: str, natural: str, sql: str, elapsed: float):
    try:
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO query_history (user_role, natural_query, generated_query, execution_time) VALUES (%s,%s,%s,%s)",
            (role, natural, sql, elapsed)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/generate")
def generate_query(request: QueryRequest, current_user: dict = Depends(get_current_user)):
    start = time.time()
    nq = request.natural_query.strip()

    # ── Cache lookup (SELECT only) ────────────────────────────────────────────
    cached_sql, cached_result = _get_cache(nq)
    if cached_sql and cached_result is not None:
        op = cached_sql.strip().split()[0].lower()
        if op == "select":
            return {
                "action_required": "none",
                "query": cached_sql,
                "data": cached_result,
                "execution_time": round(time.time() - start, 4),
                "cached": True
            }

    # ── Generate SQL ──────────────────────────────────────────────────────────
    result = generate_sql_query(nq, current_user["role"])
    if not result["success"]:
        raise HTTPException(500, result["error_msg"])

    query_dict = result["query_dict"]
    validation = validate_sql_query(query_dict, current_user["role"])
    if not validation["is_valid"]:
        try:
            conn = get_db_connection()
            cur  = conn.cursor()
            cur.execute(
                "INSERT INTO security_logs (user_role, attempted_query, reason) VALUES (%s,%s,%s)",
                (current_user["role"], str(query_dict), validation["reason"])
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception:
            pass
        raise HTTPException(403, f"Security Alert: {validation['reason']}")

    op = query_dict.get("operation", "").lower()

    # ── Write ops → require confirmation ─────────────────────────────────────
    if op in {"insert", "update", "delete"}:
        return {
            "action_required": "confirm",
            "action_type": op.upper(),
            "query": query_dict["sql"],
            "query_dict": query_dict,
            "original_query": nq,
            "data": [],
            "execution_time": 0
        }

    # ── Execute SELECT ────────────────────────────────────────────────────────
    try:
        data = _run_query(query_dict)
        elapsed = time.time() - start
        _log_history(current_user["role"], nq, query_dict["sql"], elapsed)
        _set_cache(nq, query_dict["sql"], data)
        return {
            "action_required": "none",
            "query": query_dict["sql"],
            "data": data,
            "execution_time": round(elapsed, 4),
            "cached": False
        }
    except Exception as e:
        raise HTTPException(400, f"Query error: {e}")


@router.post("/execute")
def execute_confirmed(request: ExecuteRequest, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "Staff":
        raise HTTPException(403, "Only Staff can execute write operations.")
    start = time.time()
    validation = validate_sql_query(request.query_dict, current_user["role"])
    if not validation["is_valid"]:
        raise HTTPException(403, f"Security Alert: {validation['reason']}")
    try:
        data = _run_query(request.query_dict)
        elapsed = time.time() - start
        _log_history(current_user["role"], request.original_query, request.query_dict.get("sql",""), elapsed)
        # Invalidate cache after write
        try:
            conn = get_db_connection()
            cur  = conn.cursor()
            cur.execute("DELETE FROM query_cache")
            conn.commit()
            cur.close()
            conn.close()
        except Exception:
            pass
        return {"success": True, "message": "Operation executed.", "data": data}
    except Exception as e:
        raise HTTPException(400, f"Execution error: {e}")


@router.get("/history")
def get_history(limit: int = 10, current_user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        if current_user["role"] == "Staff":
            cur.execute(
                "SELECT * FROM query_history WHERE user_role='Staff' ORDER BY timestamp DESC LIMIT %s", (limit,)
            )
        else:
            cur.execute("SELECT * FROM query_history ORDER BY timestamp DESC LIMIT %s", (limit,))
        rows = cur.fetchall()
        for r in rows:
            if r.get("timestamp"):
                r["timestamp"] = str(r["timestamp"])
        return rows
    finally:
        cur.close()
        conn.close()


@router.get("/analytics")
def get_analytics(current_user: dict = Depends(get_current_user)):
    """Admin analytics dashboard data."""
    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT COUNT(*) AS total FROM students")
        total_students = cur.fetchone()["total"]

        cur.execute("SELECT COUNT(*) AS total FROM marks")
        total_marks = cur.fetchone()["total"]

        cur.execute("SELECT COUNT(*) AS total FROM uploaded_files")
        total_files = cur.fetchone()["total"]

        cur.execute("SELECT COUNT(*) AS total FROM query_history")
        total_queries = cur.fetchone()["total"]

        cur.execute(
            "SELECT m.semester, ROUND(AVG(m.sgpa),2) AS avg_sgpa, COUNT(DISTINCT m.usn) AS student_count "
            "FROM marks m GROUP BY m.semester ORDER BY m.semester"
        )
        semester_stats = cur.fetchall()

        cur.execute(
            "SELECT s.usn, s.name, ROUND(AVG(m.sgpa),2) AS cgpa "
            "FROM students s JOIN marks m ON s.usn=m.usn "
            "GROUP BY s.usn, s.name ORDER BY cgpa DESC LIMIT 10"
        )
        top_students = cur.fetchall()

        cur.execute(
            "SELECT user_role, COUNT(*) AS cnt FROM query_history GROUP BY user_role"
        )
        query_by_role = cur.fetchall()

        return {
            "total_students": total_students,
            "total_marks": total_marks,
            "total_files": total_files,
            "total_queries": total_queries,
            "semester_stats": semester_stats,
            "top_students": top_students,
            "query_by_role": query_by_role,
        }
    finally:
        cur.close()
        conn.close()
