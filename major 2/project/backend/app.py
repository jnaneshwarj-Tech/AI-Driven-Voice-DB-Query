import os
import io
import json
import threading
import secrets
import hashlib
from datetime import datetime, timedelta
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, EmailStr
import pandas as pd

from db import init_database, get_connection
from file_processor import process_file
from ai_engine import run_ai_query, execute_sql
from validation import get_validation_report, get_duplicate_usns
from cache import clear_cache
from models import MAIN_TABLE
from auth import (
    init_users_table, register_user, login_user, hash_password,
    get_current_user, require_staff, require_any
)
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
try:
    from email_service import send_reset_password_email
except ImportError:
    def send_reset_password_email(to_email, reset_link):
        print(f"[RESET EMAIL LINK] {reset_link}")

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads")
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

init_database()
init_users_table()

app = FastAPI(title="Student Data Management System", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Auth Routes ─────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    confirm_password: str

@app.post("/auth/register")
async def register(req: RegisterRequest):
    if len(req.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters.")
    return register_user(req.name, req.email, req.password)

@app.post("/auth/login")
async def login(req: LoginRequest):
    return login_user(req.email, req.password)

@app.post("/auth/forgot-password")
async def forgot_password(req: ForgotPasswordRequest):
    generic_msg = "If an account exists for this email, a password reset link has been sent."
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name, email FROM users WHERE email = %s", (req.email,))
    user = cursor.fetchone()

    if not user:
        cursor.close()
        conn.close()
        return {"message": generic_msg}

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = datetime.now() + timedelta(minutes=20)

    cursor.execute("UPDATE password_reset_tokens SET used=1 WHERE user_id=%s AND used=0", (user["id"],))
    cursor.execute(
        "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
        (user["id"], token_hash, expires_at)
    )
    conn.commit()
    cursor.close()
    conn.close()

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    reset_link = f"{frontend_url}/reset-password/{raw_token}"
    send_reset_password_email(req.email, reset_link)

    return {"message": generic_msg}

@app.post("/auth/reset-password")
async def reset_password(req: ResetPasswordRequest):
    if not req.new_password:
        raise HTTPException(400, "New password cannot be empty.")
    if req.new_password != req.confirm_password:
        raise HTTPException(400, "Passwords do not match.")
    if len(req.new_password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters.")

    token_hash = hashlib.sha256(req.token.encode()).hexdigest()
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM password_reset_tokens WHERE token_hash=%s AND used=0 AND expires_at > NOW()",
        (token_hash,)
    )
    token_record = cursor.fetchone()

    if not token_record:
        cursor.close()
        conn.close()
        raise HTTPException(400, "Invalid, expired, or already-used reset token.")

    user_id = token_record["user_id"]
    new_hashed = hash_password(req.new_password)
    cursor.execute("UPDATE users SET password=%s WHERE id=%s", (new_hashed, user_id))
    cursor.execute("UPDATE password_reset_tokens SET used=1 WHERE id=%s", (token_record["id"],))
    conn.commit()
    cursor.close()
    conn.close()

    return {"message": "Password reset successfully. You can now log in with your new password."}

@app.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user

# ─── File Upload (STAFF ONLY) ─────────────────────────────────────────────────

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    user: dict = Depends(require_staff)
):
    allowed = {".csv", ".xlsx", ".xls", ".json", ".pdf"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    save_path = os.path.join(UPLOAD_DIR, file.filename)
    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    result_holder = {}
    error_holder = {}

    def run():
        try:
            result_holder["result"] = process_file(save_path)
        except Exception as e:
            error_holder["error"] = str(e)

    t = threading.Thread(target=run)
    t.start()
    t.join(timeout=120)

    if error_holder:
        raise HTTPException(500, error_holder["error"])

    return {"status": "success", **result_holder.get("result", {})}

# ─── AI Query ─────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str
    confirm: bool = False

@app.post("/query")
async def ai_query(req: QueryRequest, user: dict = Depends(get_current_user)):
    if not req.query.strip():
        raise HTTPException(400, "Query cannot be empty")

    query_upper = req.query.upper()
    is_destructive = any(kw in query_upper for kw in ["DELETE", "INSERT", "UPDATE", "DROP", "TRUNCATE"])

    # Admin cannot do destructive operations
    if is_destructive and user["role"] == "admin":
        raise HTTPException(403, "Admins are not allowed to modify data.")

    # Staff must confirm destructive operations
    if is_destructive and user["role"] == "staff" and not req.confirm:
        return {
            "requires_confirmation": True,
            "message": "⚠️ You are about to perform a critical operation. This may affect database integrity. Do you want to continue?",
            "query": req.query,
        }

    try:
        result = run_ai_query(req.query, user["role"])
        return result
    except Exception as e:
        raise HTTPException(500, str(e))

# ─── Students (read: any, write: staff only) ──────────────────────────────────

@app.get("/students")
async def get_students(
    page: int = 1, page_size: int = 20,
    search: str = "", sort_by: str = "usn", sort_dir: str = "asc",
    user: dict = Depends(get_current_user)
):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(f"SHOW TABLES LIKE '{MAIN_TABLE}'")
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return {"data": [], "total": 0, "page": page, "page_size": page_size}

        offset = (page - 1) * page_size
        sort_dir_sql = "ASC" if sort_dir.lower() == "asc" else "DESC"

        cursor.execute(f"SHOW COLUMNS FROM `{MAIN_TABLE}`")
        valid_cols = [r[0] for r in cursor.fetchall()]
        if sort_by not in valid_cols:
            sort_by = valid_cols[0] if valid_cols else "usn"

        if search:
            # Only search columns that exist
            search_cols = [c for c in ["usn", "name", "branch", "email"] if c in valid_cols]
            if not search_cols:
                search_cols = [valid_cols[0]]
            like = f"%{search}%"
            where = " OR ".join([f"`{c}` LIKE %s" for c in search_cols])
            params = [like] * len(search_cols)
            cursor.execute(
                f"SELECT * FROM `{MAIN_TABLE}` WHERE {where} ORDER BY `{sort_by}` {sort_dir_sql} LIMIT %s OFFSET %s",
                params + [page_size, offset]
            )
            data = cursor.fetchall()
            cursor.execute(f"SELECT COUNT(*) as cnt FROM `{MAIN_TABLE}` WHERE {where}", params)
        else:
            cursor.execute(
                f"SELECT * FROM `{MAIN_TABLE}` ORDER BY `{sort_by}` {sort_dir_sql} LIMIT %s OFFSET %s",
                (page_size, offset)
            )
            data = cursor.fetchall()
            cursor.execute(f"SELECT COUNT(*) as cnt FROM `{MAIN_TABLE}`")

        total = cursor.fetchone()["cnt"]
    except Exception as e:
        cursor.close()
        conn.close()
        raise HTTPException(500, str(e))

    cursor.close()
    conn.close()
    return {"data": data, "total": total, "page": page, "page_size": page_size}

@app.get("/students/{usn}")
async def get_student(usn: str, user: dict = Depends(get_current_user)):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM `{MAIN_TABLE}` WHERE usn = %s", (usn,))
    student = cursor.fetchone()
    if not student:
        raise HTTPException(404, "Student not found")
    cursor.execute("SELECT * FROM semester_data WHERE usn = %s ORDER BY semester", (usn,))
    semesters = cursor.fetchall()
    cursor.close()
    conn.close()
    return {"student": student, "semesters": semesters}

# ─── Dashboard (any role) ─────────────────────────────────────────────────────

@app.get("/dashboard")
async def dashboard(user: dict = Depends(get_current_user)):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    stats = {}
    try:
        cursor.execute(f"SHOW TABLES LIKE '{MAIN_TABLE}'")
        if not cursor.fetchone():
            return {"total_students": 0, "avg_cgpa": 0, "graduated": 0, "low_performers": 0}

        cursor.execute(f"SELECT COUNT(*) as cnt FROM `{MAIN_TABLE}`")
        stats["total_students"] = cursor.fetchone()["cnt"]

        cursor.execute(f"SELECT AVG(cgpa) as avg FROM `{MAIN_TABLE}` WHERE cgpa IS NOT NULL")
        row = cursor.fetchone()
        stats["avg_cgpa"] = round(float(row["avg"]) if row["avg"] else 0, 2)

        cursor.execute(f"SELECT COUNT(*) as cnt FROM `{MAIN_TABLE}` WHERE status = 'GRADUATED'")
        stats["graduated"] = cursor.fetchone()["cnt"]

        cursor.execute(f"SELECT COUNT(*) as cnt FROM `{MAIN_TABLE}` WHERE cgpa < 5 AND cgpa IS NOT NULL")
        stats["low_performers"] = cursor.fetchone()["cnt"]

        cursor.execute(f"""
            SELECT branch, COUNT(*) as count FROM `{MAIN_TABLE}`
            WHERE branch IS NOT NULL AND branch != ''
            GROUP BY branch ORDER BY count DESC LIMIT 10
        """)
        stats["branch_distribution"] = cursor.fetchall()

        cursor.execute(f"""
            SELECT
                CASE
                    WHEN cgpa >= 9 THEN '9-10'
                    WHEN cgpa >= 8 THEN '8-9'
                    WHEN cgpa >= 7 THEN '7-8'
                    WHEN cgpa >= 6 THEN '6-7'
                    WHEN cgpa >= 5 THEN '5-6'
                    ELSE 'Below 5'
                END as range_label,
                COUNT(*) as count
            FROM `{MAIN_TABLE}` WHERE cgpa IS NOT NULL
            GROUP BY range_label ORDER BY range_label DESC
        """)
        stats["cgpa_distribution"] = cursor.fetchall()

        cursor.execute(f"SELECT name, usn, cgpa, branch FROM `{MAIN_TABLE}` WHERE cgpa IS NOT NULL ORDER BY cgpa DESC LIMIT 5")
        stats["top_students"] = cursor.fetchall()

        cursor.execute(f"SELECT name, usn, cgpa, branch FROM `{MAIN_TABLE}` WHERE cgpa < 5 AND cgpa IS NOT NULL ORDER BY cgpa ASC LIMIT 10")
        stats["low_performer_list"] = cursor.fetchall()

    except Exception as e:
        cursor.close()
        conn.close()
        raise HTTPException(500, str(e))

    cursor.close()
    conn.close()
    return stats

# ─── Validation (any role) ────────────────────────────────────────────────────

@app.get("/validation")
async def validation_report(user: dict = Depends(get_current_user)):
    return {"issues": get_validation_report(), "duplicates": get_duplicate_usns()}

# ─── Export (any role) ────────────────────────────────────────────────────────

@app.get("/export/csv")
async def export_csv(request: Request):
    # Accept token from header OR query param (for direct browser download)
    token = _extract_token(request)
    from auth import decode_token
    decode_token(token)  # validates
    conn = get_connection()
    try:
        df = pd.read_sql(f"SELECT * FROM `{MAIN_TABLE}`", conn)
    except Exception as e:
        conn.close()
        raise HTTPException(500, str(e))
    conn.close()
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=students.csv"},
    )

@app.get("/export/excel")
async def export_excel(request: Request):
    token = _extract_token(request)
    from auth import decode_token
    decode_token(token)
    conn = get_connection()
    try:
        df = pd.read_sql(f"SELECT * FROM `{MAIN_TABLE}`", conn)
    except Exception as e:
        conn.close()
        raise HTTPException(500, str(e))
    conn.close()
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Students")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=students.xlsx"},
    )

def _extract_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    token = request.query_params.get("token", "")
    if token:
        return token
    raise HTTPException(401, "Not authenticated")

class PDFRequest(BaseModel):
    query: str
    data: list
    sql: str

@app.post("/export/pdf")
async def export_pdf(req: PDFRequest, user: dict = Depends(get_current_user)):
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.units import cm

        filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        filepath = os.path.join(REPORTS_DIR, filename)

        doc = SimpleDocTemplate(filepath, pagesize=landscape(A4))
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph("Student Data Management System - Query Report", styles["Title"]))
        elements.append(Spacer(1, 0.5 * cm))
        elements.append(Paragraph(f"Query: {req.query}", styles["Normal"]))
        elements.append(Paragraph(f"SQL: {req.sql}", styles["Code"]))
        elements.append(Spacer(1, 0.5 * cm))
        elements.append(Paragraph(f"Generated by: {user['name']} ({user['role']}) | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles["Normal"]))
        elements.append(Spacer(1, 1 * cm))

        if req.data:
            headers = list(req.data[0].keys())
            table_data = [headers]
            for row in req.data[:200]:
                table_data.append([str(row.get(h, "")) for h in headers])

            col_width = (landscape(A4)[0] - 2 * cm) / len(headers)
            t = Table(table_data, colWidths=[col_width] * len(headers), repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a73e8")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4ff")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING", (0, 0), (-1, -1), 4),
            ]))
            elements.append(t)
        else:
            elements.append(Paragraph("No data found.", styles["Normal"]))

        doc.build(elements)
        return FileResponse(filepath, media_type="application/pdf",
                            headers={"Content-Disposition": f"attachment; filename={filename}"})
    except ImportError:
        raise HTTPException(500, "reportlab not installed.")
    except Exception as e:
        raise HTTPException(500, str(e))

# ─── Schema & Cache ───────────────────────────────────────────────────────────

@app.get("/schema")
async def get_schema(user: dict = Depends(get_current_user)):
    from schema_memory import get_full_schema
    return get_full_schema()

@app.delete("/cache")
async def delete_cache(user: dict = Depends(require_staff)):
    clear_cache()
    return {"status": "cache cleared"}

@app.get("/semester/{usn}")
async def get_semester_data(usn: str, user: dict = Depends(get_current_user)):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM semester_data WHERE usn = %s ORDER BY semester", (usn,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

# ─── API Key Settings ─────────────────────────────────────────────────────────

_api_key_store = {"key": os.getenv("OPENAI_API_KEY", "")}

class APIKeyRequest(BaseModel):
    api_key: str

@app.post("/settings/apikey")
async def set_api_key(req: APIKeyRequest, user: dict = Depends(require_staff)):
    _api_key_store["key"] = req.api_key.strip()
    os.environ["OPENAI_API_KEY"] = req.api_key.strip()
    import ai_engine
    ai_engine._client = None
    return {"status": "saved"}

@app.get("/settings/apikey-status")
async def get_api_key_status(user: dict = Depends(get_current_user)):
    key = _api_key_store.get("key", "")
    return {"configured": bool(key)}

@app.delete("/settings/apikey")
async def delete_api_key(user: dict = Depends(require_staff)):
    _api_key_store["key"] = ""
    os.environ["OPENAI_API_KEY"] = ""
    import ai_engine
    ai_engine._client = None
    return {"status": "removed"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8001, reload=True)
