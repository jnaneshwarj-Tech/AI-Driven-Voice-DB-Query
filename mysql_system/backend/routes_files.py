"""
routes_files.py — File upload + AI-powered smart data merging.
Two-step: upload (pending) → update-db (parse + insert).
"""
import io
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from datetime import datetime, timezone
import pandas as pd

from auth import get_current_user
from database_connection import execute_query, execute_write
from ai_data_mapper import map_and_insert

router = APIRouter(prefix="/api/files", tags=["Files"])

# In-memory cache for pending files (keyed by filename)
_pending: dict[str, bytes] = {}

@router.post("/upload")
async def upload_file(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file.")
    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in ('csv', 'xlsx', 'xls'):
        raise HTTPException(422, "Only CSV and Excel files are supported.")

    _pending[file.filename] = content

    # Log in DB
    execute_write(
        """INSERT INTO query_history (user_role, natural_query, generated_sql, execution_time)
           VALUES (%s, %s, %s, %s)""",
        (current_user['role'], f"[FILE UPLOAD] {file.filename}", "pending", 0)
    )
    return {
        "success": True,
        "filename": file.filename,
        "size_bytes": len(content),
        "status": "pending",
        "message": "File uploaded. Click 'Update Database' to process."
    }

@router.post("/update-db/{filename}")
def update_database(filename: str, current_user: dict = Depends(get_current_user)):
    content = _pending.get(filename)
    if not content:
        raise HTTPException(404, "File not found in cache. Please re-upload.")

    ext = filename.rsplit('.', 1)[-1].lower()
    try:
        if ext == 'csv':
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(422, f"Cannot read file: {e}")

    if df.empty:
        raise HTTPException(422, "File is empty.")

    summary = map_and_insert(df, execute_write, execute_query)
    if "error" in summary:
        raise HTTPException(422, summary["error"])

    _pending.pop(filename, None)
    return {
        "success": True,
        "filename": filename,
        "summary": summary,
        "message": f"File successfully updated to database. Personal: {summary['personal']}, Academic: {summary['academic']}, GPA: {summary['gpa']}, Marks: {summary['marks']} records."
    }

@router.get("/pending")
def list_pending(current_user: dict = Depends(get_current_user)):
    return [{"filename": k, "status": "pending"} for k in _pending.keys()]
