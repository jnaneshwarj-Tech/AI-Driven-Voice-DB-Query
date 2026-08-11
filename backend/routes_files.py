"""
routes_files.py — Transaction-safe file upload, parse, MySQL upsert.

Import policy:
  - Every parsed row gets exactly one status:
      NEW / UPDATED / UNCHANGED / DUPLICATE / INVALID / REJECTED
  - NEW + UPDATED + UNCHANGED + DUPLICATE + INVALID + REJECTED = TOTAL PARSED
  - No row silently disappears
  - mapped_records is the authoritative source for row accounting
  - gpa_data / mark extraction drives marks only
  - Pre-validate → classify → prepare → single transaction → commit/rollback
  - Chunked processing for large files
"""

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from datetime import datetime
import re, os
from database import db_conn, write_audit_log
from auth import get_current_user
from file_parser import parse_file
from canonical_fields import (
    validate_mapped_rows, validate_sgpa_value, extract_marks_from_row, _is_empty,
)
from graduation_manager import parse_usn_full
from config import settings
from error_messages import safe_http_error

router = APIRouter(prefix="/api/files", tags=["File Management"])

_file_cache: dict[str, bytes] = {}

STUDENT_COLS = [
    'name', 'dob', 'year_of_joining', 'current_sem',
    'father_name', 'mother_name', 'blood_group', 'address', 'status',
    'gender', 'religion', 'caste', 'sub_caste', 'category',
    'permanent_address', 'current_address', 'phone', 'email',
    'aadhar_no', 'year_and_branch', 'source_file', 'branch', 'division', 'domain',
]

_COL_MAX = {
    'usn': 100, 'name': 100, 'father_name': 150, 'mother_name': 150,
    'blood_group': 5, 'status': 20, 'gender': 10, 'religion': 50,
    'caste': 100, 'sub_caste': 100, 'category': 20,
    'phone': 20, 'aadhar_no': 20, 'year_and_branch': 100,
    'source_file': 255, 'branch': 50, 'division': 50, 'domain': 100,
}

_USN_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9\-/]{0,98}[A-Za-z0-9]$|^[A-Za-z0-9]{2,100}$')


def _safe_int(val):
    try: return int(float(val))
    except Exception: return None

def _safe_dec(val):
    try:
        f = float(val)
        return round(f, 2) if f == f else None
    except Exception: return None

def _clean_str(val, max_len=None):
    if _is_empty(val): return None
    s = str(val).strip()
    if max_len: s = s[:max_len]
    return s

def _clean_date(val):
    if _is_empty(val): return None
    s = str(val).strip()
    try:
        import pandas as pd
        return pd.to_datetime(s).strftime('%Y-%m-%d')
    except Exception: return None

def _valid_usn(usn: str) -> bool:
    if not usn or len(usn) > 100: return False
    if ' ' in usn: return False
    return bool(_USN_RE.match(usn))

def _parse_usn(usn: str) -> dict:
    return parse_usn_full(usn) or {}

def _clear_cache(conn):
    try:
        c = conn.cursor()
        c.execute("DELETE FROM query_cache")
        c.close()
    except Exception: pass

def _get_upload_cache(filename: str):
    if filename in _file_cache:
        return _file_cache[filename]
    disk_path = os.path.join(settings.upload_dir_abs, filename)
    if os.path.exists(disk_path):
        with open(disk_path, 'rb') as f:
            content = f.read()
        _file_cache[filename] = content
        return content
    return None

def _save_upload_cache(filename: str, content: bytes):
    _file_cache[filename] = content
    disk_path = os.path.join(settings.upload_dir_abs, filename)
    with open(disk_path, 'wb') as f:
        f.write(content)

def _remove_upload_cache(filename: str):
    _file_cache.pop(filename, None)
    disk_path = os.path.join(settings.upload_dir_abs, filename)
    if os.path.exists(disk_path):
        try: os.remove(disk_path)
        except Exception: pass


def _student_payload(row: dict, name: str | None = None) -> dict:
    payload = {}
    for col in STUDENT_COLS:
        if col == 'dob':
            payload[col] = _clean_date(row.get(col))
        elif col == 'name':
            payload[col] = _clean_str(name if name is not None else row.get('name'), _COL_MAX.get('name'))
        elif col == 'current_sem':
            payload[col] = _safe_int(row.get('current_sem')) or _safe_int(row.get('semester'))
        elif col == 'year_of_joining':
            payload[col] = _safe_int(row.get('year_of_joining')) or _safe_int(row.get('admission_year'))
        else:
            payload[col] = _clean_str(row.get(col), _COL_MAX.get(col))
    payload['source_file'] = payload.get('source_file')  # may be set by caller
    return payload


def _upsert_student(cur, usn: str, row: dict) -> str:
    """Insert or update student. Returns 'added'|'updated'|'unchanged'."""
    cur.execute("SELECT * FROM students WHERE usn=%s", (usn,))
    existing = cur.fetchone()
    usn_data = _parse_usn(usn)

    if existing:
        updates, params = [], []
        changed = False
        for col in STUDENT_COLS:
            if col == 'dob':
                v = _clean_date(row.get(col))
            elif col in ('current_sem', 'year_of_joining'):
                v = row.get(col)
                if v is not None and not isinstance(v, int):
                    v = _safe_int(v)
            else:
                v = _clean_str(row.get(col), _COL_MAX.get(col))
            if v is None:
                continue
            old = existing.get(col)
            old_s = '' if old is None else str(old).strip()
            new_s = str(v).strip()
            if col == 'name' or old_s == '' or old_s != new_s:
                if old_s != new_s:
                    changed = True
                updates.append(f"`{col}`=%s")
                params.append(v)
        if usn_data:
            for col, key in (
                ('admission_year', 'admission_batch'),
                ('current_year', 'current_year'),
                ('student_type', 'student_type'),
                ('estimated_semester', 'current_sem'),
            ):
                val = usn_data.get(key)
                if val is not None:
                    updates.append(f"`{col}`=%s")
                    params.append(val)
                    if str(existing.get(col) or '') != str(val):
                        changed = True
        if updates and changed:
            params.append(usn)
            cur.execute(f"UPDATE students SET {','.join(updates)} WHERE usn=%s", tuple(params))
            return 'updated'
        if updates and not changed:
            # Still apply USN-derived fills if columns were empty — already handled
            return 'unchanged'
        return 'unchanged'
    else:
        fields, vals = ['usn'], [usn]
        for col in STUDENT_COLS:
            if col == 'dob':
                v = _clean_date(row.get(col))
            elif col in ('current_sem', 'year_of_joining'):
                v = row.get(col)
                if v is not None and not isinstance(v, int):
                    v = _safe_int(v)
            else:
                v = _clean_str(row.get(col), _COL_MAX.get(col))
            if v is not None:
                fields.append(f'`{col}`')
                vals.append(v)
        if usn_data:
            fields += ['`admission_year`','`current_year`','`student_type`','`estimated_semester`']
            vals   += [usn_data.get('admission_batch'), usn_data.get('current_year'),
                       usn_data.get('student_type'), usn_data.get('current_sem')]
        # name is required by DB — enforce before insert
        if 'name' not in [f.strip('`') for f in fields] and '`name`' not in fields:
            raise ValueError(f"Cannot insert USN {usn}: required field 'name' is missing")
        ph = ','.join(['%s'] * len(fields))
        cur.execute(f"INSERT INTO students ({','.join(fields)}) VALUES ({ph})", tuple(vals))
        return 'added'


def _upsert_mark(cur, usn: str, semester: int, sgpa) -> str:
    """Insert or update mark. Returns 'added'|'updated'|'unchanged'|'skipped'|'rejected'."""
    if sgpa is None:
        return 'skipped'
    err = validate_sgpa_value(sgpa)
    if err:
        return 'rejected'
    cur.execute("SELECT id, sgpa FROM marks WHERE usn=%s AND semester=%s", (usn, semester))
    existing = cur.fetchone()
    if existing:
        old = existing.get('sgpa') if isinstance(existing, dict) else existing[1]
        try:
            old_f = None if old is None else round(float(old), 2)
            new_f = round(float(sgpa), 2)
        except (TypeError, ValueError):
            old_f, new_f = old, sgpa
        if old_f != new_f:
            cur.execute("UPDATE marks SET sgpa=%s WHERE usn=%s AND semester=%s", (sgpa, usn, semester))
            return 'updated'
        return 'unchanged'
    cur.execute("INSERT INTO marks (usn, semester, sgpa) VALUES (%s,%s,%s)", (usn, semester, sgpa))
    return 'added'


# ── Upload endpoint ────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_file(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    """Step 1: Store file in cache. Does NOT write to DB yet."""
    if current_user["role"] != "Staff":
        raise HTTPException(403, "Only Staff can upload files.")
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file.")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in {"csv", "xlsx", "xls", "json", "pdf", "txt", "png", "jpg", "jpeg"}:
        raise HTTPException(422, f"Unsupported file type: .{ext}")
    _save_upload_cache(file.filename, content)
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM uploaded_files WHERE filename=%s", (file.filename,))
        cur.execute(
            "INSERT INTO uploaded_files (filename,content_type,file_type,size_bytes,uploaded_by,uploaded_at,db_status) "
            "VALUES (%s,%s,%s,%s,%s,%s,'pending')",
            (file.filename, file.content_type or ext, ext, len(content), current_user["username"], datetime.now())
        )
        conn.commit()
        cur.close()
    write_audit_log(action="FILE_UPLOAD", username=current_user["username"], role=current_user["role"],
                    target_table="uploaded_files", target_id=file.filename,
                    summary=f"File uploaded: {file.filename} ({len(content):,} bytes)")
    return {"success": True, "filename": file.filename, "file_type": ext,
            "size_bytes": len(content), "db_status": "pending",
            "message": "File uploaded. Click 'Update Database' to import data."}


@router.post("/update-db/{filename}")
def update_database(filename: str, current_user: dict = Depends(get_current_user)):
    """
    Transaction-safe import with full row accounting.

    Source of truth for counting = mapped_records (one per parsed file row).
    Marks come from extract_marks_from_row on each valid row.
    """
    if current_user["role"] != "Staff":
        raise HTTPException(403, "Only Staff can update the database.")

    content = _get_upload_cache(filename)
    if content is None:
        raise HTTPException(404, "File not in cache. Please re-upload.")

    # ── Phase 1: Parse (no DB) ────────────────────────────────────────────────
    try:
        parsed = parse_file(filename, content)
    except ValueError as e:
        write_audit_log(action="UPLOAD_PARSE_ERROR", username=current_user["username"],
                        role=current_user["role"], target_table="uploaded_files",
                        target_id=filename, summary=f"Parse failed: {e}", success=False, error_info=str(e))
        raise safe_http_error(422, e, "upload")

    fmt = parsed.get("format_type", "long")
    mapped_recs = parsed.get("mapped_records", [])
    total_parsed = parsed["row_count"]

    if not mapped_recs:
        raise HTTPException(422, "No data rows found in the file.")

    # ── Phase 2: Validate every mapped row (no DB yet) ────────────────────────
    # Academic-only files may omit names, but only when their USN already
    # exists.  This preserves personal data while allowing a later SGPA file
    # to merge into the same student record.
    existing_usns: set[str] = set()
    candidate_usns = sorted({
        str(row.get('usn')).strip()
        for row in mapped_recs
        if not _is_empty(row.get('usn')) and _valid_usn(str(row.get('usn')).strip())
    })
    if candidate_usns:
        try:
            with db_conn() as conn:
                cur = conn.cursor()
                placeholders = ','.join(['%s'] * len(candidate_usns))
                cur.execute(f"SELECT usn FROM students WHERE usn IN ({placeholders})", tuple(candidate_usns))
                existing_usns = {str(record[0]) for record in cur.fetchall()}
                cur.close()
        except Exception as exc:
            raise HTTPException(500, f"Could not validate existing students before import: {exc}")

    val_result = {'valid': mapped_recs, 'invalid': [], 'errors': []}
    if parsed.get("file_type") not in ("pdf", "txt", "image"):
        val_result = validate_mapped_rows(
            mapped_recs, allow_academic_only_usns=existing_usns
        )

    invalid_by_index = {iv['row_index']: iv for iv in val_result.get('invalid', [])}

    # ── Phase 3: Classify every parsed row ────────────────────────────────────
    # USN is primary key. First occurrence of a USN is the primary student row;
    # later occurrences of the same USN in the file are DUPLICATE (marks still collected).
    seen_usns: dict[str, int] = {}
    classified: list[dict] = []
    # marks keyed by (usn, semester) — last valid wins within file
    pending_marks: dict[tuple, dict] = {}
    # unique students to upsert: usn → student payload + classification ref
    pending_students: dict[str, dict] = {}
    marks_rejected_pre = 0

    for idx, row in enumerate(mapped_recs, start=1):
        raw_usn  = _clean_str(row.get('usn'))
        raw_name = _clean_str(row.get('name'), 150)

        if idx in invalid_by_index:
            iv = invalid_by_index[idx]
            classified.append({
                'row_index': idx, 'usn': iv.get('usn') or raw_usn, 'name': iv.get('name') or raw_name,
                'status': 'INVALID',
                'reason': '; '.join(iv['errors']),
                'problematic_fields': iv.get('problematic_fields', []),
                'row': row,
            })
            continue

        if raw_usn and _valid_usn(raw_usn):
            usn = raw_usn
        elif raw_name:
            usn = "AUTO_" + re.sub(r'[^A-Z0-9]', '', raw_name.upper())[:12]
        else:
            classified.append({
                'row_index': idx, 'usn': None, 'name': raw_name, 'status': 'INVALID',
                'reason': 'Missing both USN and name', 'problematic_fields': ['usn', 'name'],
                'row': row,
            })
            continue

        # Collect marks from this row (even if student is duplicate in file)
        row_marks = extract_marks_from_row(row)
        rejected_mark_reasons = []
        for mark in row_marks:
            sem = mark.get('semester')
            sgpa = mark.get('sgpa')
            if sgpa is None and mark.get('cgpa') is not None:
                # CGPA-only wide cells are not stored as semester SGPA
                continue
            err = validate_sgpa_value(sgpa)
            if err:
                rejected_mark_reasons.append(f"Semester {sem}: {err}")
                marks_rejected_pre += 1
                continue
            if sem is not None and sgpa is not None:
                pending_marks[(usn, sem)] = {
                    'usn': usn, 'semester': sem, 'sgpa': sgpa,
                    'row_index': idx, 'name': raw_name,
                }

        if usn in seen_usns:
            reason = f'Duplicate of row {seen_usns[usn]} in file (same USN)'
            if rejected_mark_reasons:
                reason += '; ' + '; '.join(rejected_mark_reasons)
            classified.append({
                'row_index': idx, 'usn': usn, 'name': raw_name, 'status': 'DUPLICATE',
                'reason': reason, 'problematic_fields': ['usn'], 'row': row,
            })
            continue

        seen_usns[usn] = idx
        status = 'PENDING'
        reason = ''
        if rejected_mark_reasons:
            # Student still importable; mark issues noted
            reason = '; '.join(rejected_mark_reasons)

        student_row = _student_payload(row, raw_name)
        student_row['source_file'] = filename
        pending_students[usn] = {
            'usn': usn, 'name': raw_name, 'row': student_row,
            'row_index': idx, 'reason': reason,
        }
        classified.append({
            'row_index': idx, 'usn': usn, 'name': raw_name, 'status': status,
            'reason': reason, 'problematic_fields': [], 'row': row,
        })

    # Critical gate: if EVERY row is invalid, do not open a transaction
    if not pending_students:
        details = [
            {
                'row_number': c['row_index'], 'usn': c.get('usn'), 'name': c.get('name'),
                'status': c['status'], 'reason': c['reason'],
                'problematic_fields': c.get('problematic_fields', []),
            }
            for c in classified[:50]
        ]
        write_audit_log(
            action="UPLOAD_VALIDATION_FAILED", username=current_user["username"],
            role=current_user["role"], target_table="students", target_id=filename,
            summary=f"No valid students to import from {filename}. All {total_parsed} rows invalid/rejected.",
            success=False, error_info=str(val_result.get('errors', [])[:3]),
        )
        raise HTTPException(422, {
            "message": (
                f"Import rejected: 0 valid students found in {total_parsed} parsed row(s). "
                f"No transaction started. No data modified."
            ),
            "rows_parsed": total_parsed,
            "invalid_rows": len([c for c in classified if c['status'] == 'INVALID']),
            "duplicate_rows": len([c for c in classified if c['status'] == 'DUPLICATE']),
            "column_mapping": parsed.get("column_mapping", {}),
            "rejected_rows": details,
            "hint": (
                "Ensure Student Name and USN columns are present and not wiped by empty "
                "alternate-header columns. Branch Name maps to branch, not name."
            ),
        })

    # ── Phase 4: Undo snapshot ────────────────────────────────────────────────
    affected_usns = list(pending_students.keys())
    undo_token = ""

    # ── Phase 5: Transaction — chunked student + mark upserts ─────────────────
    students_added = students_updated = students_unchanged = 0
    marks_added = marks_updated = marks_unchanged = 0
    marks_rejected = marks_rejected_pre
    duplicate_count = sum(1 for c in classified if c['status'] == 'DUPLICATE')
    invalid_count = sum(1 for c in classified if c['status'] == 'INVALID')
    rejected_rows = [c for c in classified if c['status'] in ('INVALID', 'REJECTED')]
    chunk_size = settings.MAX_UPLOAD_ROWS_PER_CHUNK
    usn_results: dict[str, str] = {}  # usn → NEW/UPDATED/UNCHANGED

    try:
        with db_conn() as conn:
            conn.autocommit = False
            conn.start_transaction()
            cur = conn.cursor(dictionary=True)
            try:
                if affected_usns:
                    from routes_undo import create_undo_snapshot
                    undo_token = create_undo_snapshot(
                        "UPLOAD", affected_usns, current_user["username"], f"Bulk upload: {filename}", conn=conn
                    )
                usn_list = list(pending_students.keys())
                for chunk_start in range(0, len(usn_list), chunk_size):
                    chunk_usns = usn_list[chunk_start: chunk_start + chunk_size]
                    for usn in chunk_usns:
                        item = pending_students[usn]
                        result = _upsert_student(cur, usn, item['row'])
                        if result == 'added':
                            students_added += 1
                            status = 'NEW'
                        elif result == 'updated':
                            students_updated += 1
                            status = 'UPDATED'
                        else:
                            students_unchanged += 1
                            status = 'UNCHANGED'
                        usn_results[usn] = status

                # Apply statuses back onto classified PENDING rows
                for item in classified:
                    if item['status'] == 'PENDING' and item.get('usn') in usn_results:
                        item['status'] = usn_results[item['usn']]

                # Marks — chunked
                mark_items = list(pending_marks.values())
                for chunk_start in range(0, len(mark_items), chunk_size):
                    chunk = mark_items[chunk_start: chunk_start + chunk_size]
                    for m in chunk:
                        # Only write marks for USNs we successfully have as students
                        if m['usn'] not in usn_results:
                            continue
                        mr = _upsert_mark(cur, m['usn'], m['semester'], m['sgpa'])
                        if mr == 'added':
                            marks_added += 1
                        elif mr == 'updated':
                            marks_updated += 1
                        elif mr == 'unchanged':
                            marks_unchanged += 1
                        elif mr == 'rejected':
                            marks_rejected += 1

                _clear_cache(conn)
                cur.execute(
                    "UPDATE uploaded_files SET db_status='saved', row_count=%s, "
                    "students_saved=%s, marks_saved=%s, gpa_rows=%s, uploaded_at=%s WHERE filename=%s",
                    (total_parsed, students_added + students_updated,
                     marks_added + marks_updated, marks_added + marks_updated,
                     datetime.now(), filename)
                )
                if undo_token:
                    from routes_undo import finalize_undo_snapshot
                    finalize_undo_snapshot(undo_token, affected_usns, conn)
                conn.commit()

            except Exception as db_err:
                try: conn.rollback()
                except Exception: pass
                cur.close()
                _write_upload_version(filename=filename, rows_parsed=total_parsed,
                    students_added=0, students_updated=0, students_unchanged=0,
                    marks_added=0, marks_updated=0, skipped=0,
                    status='failed', undo_token=undo_token,
                    performed_by=current_user["username"], error_message=str(db_err))
                write_audit_log(action="UPLOAD_FAILED", username=current_user["username"],
                    role=current_user["role"], target_table="students", target_id=filename,
                    summary=f"Upload ROLLED BACK: {filename}. Error: {db_err}",
                    success=False, error_info=str(db_err))
                # Keep the database exception in the audit record above, but
                # never expose driver/server details to the browser.
                raise HTTPException(500, "Import failed. All changes were rolled back.")
            cur.close()

    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, "upload")

    # ── Phase 6: Post-commit logging ──────────────────────────────────────────
    _remove_upload_cache(filename)
    skipped = invalid_count + duplicate_count
    _write_upload_version(filename=filename, rows_parsed=total_parsed,
        students_added=students_added, students_updated=students_updated,
        students_unchanged=students_unchanged, marks_added=marks_added,
        marks_updated=marks_updated, skipped=skipped,
        status='success', undo_token=undo_token,
        performed_by=current_user["username"], error_message=None)

    write_audit_log(action="UPLOAD_SUCCESS", username=current_user["username"],
        role=current_user["role"], target_table="students", target_id=filename,
        summary=(f"Upload success: {filename}. NEW={students_added}, UPDATED={students_updated}, "
                 f"UNCHANGED={students_unchanged}, DUPLICATE={duplicate_count}, "
                 f"INVALID={invalid_count}, Marks_added={marks_added}"))

    accounted = (
        students_added + students_updated + students_unchanged
        + duplicate_count + invalid_count
    )
    # Also count any leftover PENDING/REJECTED
    leftover = sum(1 for c in classified if c['status'] in ('PENDING', 'REJECTED'))
    accounted += leftover
    reconciled = (accounted == total_parsed)

    msg = (
        f"Import successful. "
        f"New: {students_added}, Updated: {students_updated}, Unchanged: {students_unchanged}, "
        f"Duplicates: {duplicate_count}, Invalid: {invalid_count}. "
        f"Marks: added {marks_added}, updated {marks_updated}."
    )
    if not reconciled:
        msg += f" [Accounting: {accounted}/{total_parsed} rows]"

    rejected_detail = [
        {
            "row_number": r["row_index"],
            "usn": r.get("usn"),
            "name": r.get("name"),
            "status": r["status"],
            "reason": r["reason"],
            "problematic_fields": r.get("problematic_fields", []),
        }
        for r in rejected_rows[:50]
    ]
    duplicate_detail = [
        {
            "row_number": r["row_index"], "usn": r.get("usn"),
            "name": r.get("name"), "reason": r["reason"],
        }
        for r in classified if r["status"] == "DUPLICATE"
    ][:50]
    new_detail = [
        {"row_number": r["row_index"], "usn": r.get("usn"), "name": r.get("name")}
        for r in classified if r["status"] == "NEW"
    ][:50]
    updated_detail = [
        {"row_number": r["row_index"], "usn": r.get("usn"), "name": r.get("name")}
        for r in classified if r["status"] == "UPDATED"
    ][:50]

    return {
        "success": True,
        "filename": filename,
        "db_status": "saved",
        "rows_parsed": total_parsed,
        "source_rows": total_parsed,
        "students_added": students_added,
        "students_updated": students_updated,
        "students_unchanged": students_unchanged,
        "students_saved": students_added + students_updated,
        "marks_added": marks_added,
        "marks_updated": marks_updated,
        "marks_unchanged": marks_unchanged,
        "marks_saved": marks_added + marks_updated,
        "marks_rejected": marks_rejected,
        "gpa_rows_saved": marks_added + marks_updated,
        "duplicate_rows": duplicate_count,
        "invalid_rows": invalid_count,
        "rejected_rows_count": len(rejected_rows),
        "skipped_rows": skipped,
        "total_accounted": accounted,
        "reconciled": reconciled,
        "column_mapping": parsed.get("column_mapping", {}),
        "mapping_details": parsed.get("mapping_details", {}),
        "format_type": fmt,
        "message": msg,
        "rejected_rows": rejected_detail,
        "duplicate_list": duplicate_detail,
        "new_records": new_detail,
        "updated_records": updated_detail,
        "operation": "UPLOAD",
        "restore_tokens": [{"token": undo_token, "name": filename}] if undo_token else [],
        "undo_available": bool(undo_token),
        "operation_details": {
            "operation_type": "UPLOAD",
            "affected_rows": students_added + students_updated,
            "tables_updated": "students, marks, uploaded_files",
            "performed_by": current_user["username"],
            "timestamp": datetime.now().strftime("%Y-%m-%d %I:%M %p"),
            "students": new_detail[:20] + updated_detail[:20],
        },
    }


def _write_upload_version(filename, rows_parsed, students_added, students_updated,
                           students_unchanged, marks_added, marks_updated, skipped,
                           status, undo_token, performed_by, error_message):
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO upload_versions
                   (filename,rows_parsed,students_added,students_updated,students_unchanged,
                    marks_added,marks_updated,skipped_rows,status,undo_token,performed_by,error_message)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (filename, rows_parsed, students_added, students_updated, students_unchanged,
                 marks_added, marks_updated, skipped, status, undo_token or None,
                 performed_by, error_message))
            conn.commit()
            cur.close()
    except Exception:
        pass


# ── Supporting endpoints ───────────────────────────────────────────────────────

@router.get("/list")
def list_files(current_user: dict = Depends(get_current_user)):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM uploaded_files ORDER BY uploaded_at DESC")
        docs = cur.fetchall()
        cur.close()
    for d in docs:
        if d.get("uploaded_at"): d["uploaded_at"] = str(d["uploaded_at"])
        if d.get("db_status") == "pending" and d["filename"] not in _file_cache:
            disk_path = os.path.join(settings.upload_dir_abs, d["filename"])
            if not os.path.exists(disk_path):
                d["cache_expired"] = True
    return docs


@router.get("/parsed/{filename}")
def get_parsed_preview(filename: str, current_user: dict = Depends(get_current_user)):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(
                "SELECT s.usn, s.name, m.semester, m.sgpa, "
                "ROUND((SELECT AVG(m2.sgpa) FROM marks m2 WHERE m2.usn=s.usn),2) AS cgpa "
                "FROM students s LEFT JOIN marks m ON s.usn=m.usn "
                "ORDER BY s.name, m.semester LIMIT 100")
            rows = cur.fetchall()
        except Exception:
            rows = []
        cur.close()
    return rows


@router.get("/gpa")
def get_gpa_data(current_user: dict = Depends(get_current_user)):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(
                "SELECT s.usn, s.name, m.semester, m.sgpa, "
                "ROUND((SELECT AVG(m2.sgpa) FROM marks m2 WHERE m2.usn=s.usn),2) AS cgpa "
                "FROM students s JOIN marks m ON s.usn=m.usn ORDER BY s.name, m.semester")
            rows = cur.fetchall()
        except Exception:
            rows = []
        cur.close()
    return rows


@router.delete("/delete/{filename}")
def delete_file(filename: str, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "Staff":
        raise HTTPException(403, "Only Staff can delete files.")
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM uploaded_files WHERE filename=%s", (filename,))
        conn.commit()
        cur.close()
    _remove_upload_cache(filename)
    return {"success": True, "message": f"Deleted '{filename}'."}


@router.get("/validation")
def validation_dashboard(current_user: dict = Depends(get_current_user)):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        issues = []
        cur.execute("SELECT usn FROM students WHERE name IS NULL OR name='' LIMIT 100")
        for r in cur.fetchall():
            issues.append({"type": "missing_name", "usn": r["usn"], "detail": "Student has no name"})
        cur.execute("SELECT usn, semester, sgpa FROM marks WHERE sgpa < 0 OR sgpa > 10 LIMIT 100")
        for r in cur.fetchall():
            issues.append({"type": "invalid_sgpa", "usn": r["usn"], "semester": r["semester"],
                           "detail": f"SGPA {r['sgpa']} out of range (0-10)"})
        cur.execute("SELECT usn, semester FROM marks WHERE semester < 1 OR semester > 12 LIMIT 100")
        for r in cur.fetchall():
            issues.append({"type": "invalid_semester", "usn": r["usn"], "semester": r["semester"],
                           "detail": "Semester out of valid range (1-12)"})
        cur.execute("SELECT usn, COUNT(*) AS cnt FROM marks GROUP BY usn HAVING cnt > 8 LIMIT 50")
        for r in cur.fetchall():
            issues.append({"type": "too_many_semesters", "usn": r["usn"],
                           "detail": f"Has {r['cnt']} semester records (max 8)"})
        cur.execute("SELECT COUNT(*) AS total FROM students")
        ts = cur.fetchone()["total"]
        cur.execute("SELECT COUNT(*) AS total FROM marks")
        tm = cur.fetchone()["total"]
        cur.close()
    return {"total_students": ts, "total_marks": tm, "issues": issues, "issue_count": len(issues)}


@router.get("/duplicates")
def detect_duplicates(current_user: dict = Depends(get_current_user)):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT name, COUNT(*) AS cnt, GROUP_CONCAT(usn) AS usns "
            "FROM students GROUP BY name HAVING cnt > 1 LIMIT 100")
        rows = cur.fetchall()
        cur.close()
    return rows
