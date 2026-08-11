"""
routes_undo.py — Hardened Undo / Restore / Activity system (Sprint 1).

Sprint 1 improvements:
  - Full transaction wrapping for undo operations
  - Undo validation before execution
  - Audit log entries for every undo
  - Extended undo window: 30 min for bulk, 5 min for single
  - Backup/restore activity stream added to activity feed

Endpoints:
  POST /api/undo/soft-delete           — soft-delete a student (internal)
  POST /api/undo/restore/{token}       — restore a soft-deleted student
  GET  /api/undo/deleted               — list recently soft-deleted students
  GET  /api/undo/activity              — unified recent activity feed
  GET  /api/undo/history/{usn}         — change history for a student
  GET  /api/undo/validate/{token}      — validate if undo is safe (NEW)
"""
import json, uuid
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from database import db_conn, write_audit_log
from auth import get_current_user
from config import settings
from error_messages import safe_http_error

router = APIRouter(prefix="/api/undo", tags=["Undo / Restore"])

# These are the only write-operation names exposed by the activity API.  Older
# rows used INSERT/UPLOAD; normalize them at the boundary rather than deriving
# a type from a human-readable message.
def canonical_operation_type(operation_type: str) -> str:
    return {
        "INSERT": "ADD",
        "ADD": "ADD",
        "DELETE": "DELETE",
        "UPDATE": "UPDATE",
        "UPLOAD": "IMPORT",
        "IMPORT": "IMPORT",
        "RESTORE": "RESTORE",
        "UNDO": "UNDO",
        "SEMESTER_UPDATE": "UPDATE",
    }.get((operation_type or "").upper(), (operation_type or "").upper())


# ── Helpers ───────────────────────────────────────────────────────────────────

def _student_to_json(usn: str) -> tuple[str, str]:
    """Snapshot a student + their marks as JSON. Returns (student_json, marks_json)."""
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM students WHERE usn=%s", (usn,))
        student = cur.fetchone()
        cur.execute("SELECT * FROM marks WHERE usn=%s ORDER BY semester", (usn,))
        marks = cur.fetchall()
        cur.close()

    def _serial(obj):
        import decimal
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        if isinstance(obj, decimal.Decimal):
            return float(obj)
        return obj

    if not student:
        return '{}', '[]'

    student_clean = {k: _serial(v) for k, v in student.items()}
    marks_clean   = [{k: _serial(v) for k, v in m.items()} for m in marks]
    return json.dumps(student_clean), json.dumps(marks_clean)


def _is_bulk_operation(operation_type: str) -> bool:
    """Bulk operations get a longer undo window."""
    return canonical_operation_type(operation_type) == "IMPORT" or operation_type.upper() == "SEMESTER_UPDATE"


def _check_undo_window(ts, operation_type: str) -> bool:
    """Return True if still within the undo window."""
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    if _is_bulk_operation(operation_type):
        window = timedelta(minutes=settings.UNDO_WINDOW_MINUTES_BULK)
    else:
        window = timedelta(minutes=settings.UNDO_WINDOW_MINUTES_SINGLE)
    return datetime.now() - ts <= window


# ── Soft-delete (called internally by execute endpoint) ───────────────────────

def soft_delete_student(usn: str, deleted_by: str) -> str:
    """
    Snapshot student + marks, store in soft_deleted_students, return restore_token.
    Does NOT actually delete from students table — caller does that.
    """
    student_json, marks_json = _student_to_json(usn)
    token = str(uuid.uuid4())

    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO soft_deleted_students
               (usn, student_json, marks_json, deleted_by, restore_token)
               VALUES (%s, %s, %s, %s, %s)""",
            (usn, student_json, marks_json, deleted_by, token)
        )
        conn.commit()
        cur.close()

    return token


def _json_value(value):
    """Return a stable JSON-safe form for database values."""
    import decimal
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    return value


def _capture_state(cur, usns: list[str]) -> dict:
    """Capture exactly the student/marks state for the affected USNs."""
    unique_usns = list(dict.fromkeys(u for u in usns if u))
    if not unique_usns:
        return {"students": [], "marks": []}
    placeholders = ','.join(['%s'] * len(unique_usns))
    cur.execute(f"SELECT * FROM students WHERE usn IN ({placeholders}) ORDER BY usn", tuple(unique_usns))
    students = cur.fetchall()
    cur.execute(f"SELECT * FROM marks WHERE usn IN ({placeholders}) ORDER BY usn, semester", tuple(unique_usns))
    marks = cur.fetchall()
    return {
        "students": [{k: _json_value(v) for k, v in row.items()} for row in students],
        "marks": [{k: _json_value(v) for k, v in row.items()} for row in marks],
    }


def _states_match(expected: dict, actual: dict) -> bool:
    """Compare snapshots deterministically, independent of MySQL value types."""
    return json.dumps(expected, sort_keys=True, separators=(',', ':')) == json.dumps(actual, sort_keys=True, separators=(',', ':'))


def create_undo_snapshot(
    operation_type: str,
    affected_usns: list[str],
    performed_by: str,
    description: str = "",
    conn=None,
) -> str:
    """
    Creates an undo snapshot for the given USNs.
    Captures the BEFORE state of all affected students and marks.
    Returns the undo_token (empty string if no USNs).
    """
    if not affected_usns:
        return ""

    unique_usns = list(dict.fromkeys(u for u in affected_usns if u))

    owns_connection = conn is None
    if owns_connection:
        connection_context = db_conn()
        conn = connection_context.__enter__()
    snapshot_clean = {
        "affected_usns": unique_usns,
    }
    try:
        cur = conn.cursor(dictionary=True)
        before_state = _capture_state(cur, unique_usns)
        existing_usns = {s['usn'] for s in before_state['students']}
        snapshot_clean.update({
            "existing_students": before_state['students'],
            "existing_marks": before_state['marks'],
            "new_usns": [u for u in unique_usns if u not in existing_usns],
        })
        cur.close()
        token = str(uuid.uuid4())
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO global_undo_snapshots
               (undo_token, operation_type, snapshot_data, performed_by, description, committed)
               VALUES (%s, %s, %s, %s, %s, 0)""",
            (token, canonical_operation_type(operation_type), json.dumps(snapshot_clean), performed_by, description)
        )
        cur.close()
        if owns_connection:
            conn.commit()
        return token
    except Exception:
        if owns_connection:
            conn.rollback()
        raise
    finally:
        if owns_connection:
            connection_context.__exit__(None, None, None)


def finalize_undo_snapshot(token: str, affected_usns: list[str], conn) -> None:
    """Store the successful post-change state before committing the mutation."""
    cur = conn.cursor(dictionary=True)
    post_state = _capture_state(cur, affected_usns)
    cur.close()
    cur = conn.cursor()
    cur.execute(
        "UPDATE global_undo_snapshots SET post_state_data=%s, committed=1 WHERE undo_token=%s",
        (json.dumps(post_state), token),
    )
    cur.close()


def _undo_block_reason(record: dict, current_user: dict, conn=None) -> str | None:
    """Return a user-safe reason when a rollback is no longer safe."""
    if not record.get('committed') or not record.get('post_state_data'):
        return "This operation was not committed successfully and cannot be undone."
    if record.get('performed_by') != current_user.get('username'):
        return "Permission denied. You can only undo your own operation."
    timestamp = record.get('timestamp')
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp)
    if datetime.now() - timestamp > timedelta(days=settings.UNDO_RETENTION_DAYS):
        return "Undo history has expired."
    if not _check_undo_window(timestamp, record['operation_type']):
        bulk = _is_bulk_operation(record['operation_type'])
        minutes = settings.UNDO_WINDOW_MINUTES_BULK if bulk else settings.UNDO_WINDOW_MINUTES_SINGLE
        return f"Undo window expired ({minutes} minutes for {record['operation_type']} operations)."
    snapshot = json.loads(record['snapshot_data'])
    expected = json.loads(record['post_state_data'])
    owns_connection = conn is None
    if owns_connection:
        context = db_conn()
        conn = context.__enter__()
    try:
        cur = conn.cursor(dictionary=True)
        current = _capture_state(cur, snapshot.get('affected_usns', []))
        cur.close()
        if not _states_match(expected, current):
            return "Cannot undo safely. Student was changed again."
        return None
    finally:
        if owns_connection:
            context.__exit__(None, None, None)


# ── Validate undo before executing ───────────────────────────────────────────

@router.get("/validate/{token}")
def validate_undo(token: str, current_user: dict = Depends(get_current_user)):
    """
    Check if an undo is safe and possible.
    Returns validation status without making any changes.
    """
    # Check global undo snapshots first
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM global_undo_snapshots WHERE undo_token=%s",
            (token,)
        )
        record = cur.fetchone()
        cur.close()

    if record:
        if record['undone'] == 1:
            return {
                "valid": False,
                "reason": "This operation has already been undone.",
                "token": token,
            }
        reason = _undo_block_reason(record, current_user)
        if reason:
            return {"valid": False, "reason": reason, "token": token}
        snapshot_data = json.loads(record['snapshot_data'])
        return {
            "valid": True,
            "operation_type": record['operation_type'],
            "performed_by": record['performed_by'],
            "timestamp": str(record['timestamp']),
            "description": record['description'],
            "affected_students": len(snapshot_data.get('existing_students', [])),
            "new_usns_to_delete": len(snapshot_data.get('new_usns', [])),
            "token": token,
        }

    # Check legacy soft_deleted_students
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM soft_deleted_students WHERE restore_token=%s",
            (token,)
        )
        record = cur.fetchone()
        cur.close()

    if not record:
        return {"valid": False, "reason": "Token not found.", "token": token}

    if record['restored'] == 1:
        return {"valid": False, "reason": "Already restored.", "token": token}

    if record.get('deleted_by') != current_user.get('username'):
        return {"valid": False, "reason": "Permission denied. You can only undo your own operation.", "token": token}

    in_window = _check_undo_window(record['deleted_at'], "DELETE")
    if not in_window:
        return {
            "valid": False,
            "reason": f"Undo window expired ({settings.UNDO_WINDOW_MINUTES_SINGLE} minutes).",
            "token": token,
        }

    return {"valid": True, "operation_type": "DELETE_RESTORE", "token": token}


# ── Restore endpoint ──────────────────────────────────────────────────────────

def _restore_legacy_soft_delete(token: str, current_user: dict):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM soft_deleted_students WHERE restore_token=%s AND restored=0",
            (token,)
        )
        record = cur.fetchone()
        cur.close()

    if not record:
        raise HTTPException(404, "Restore token not found or already used.")

    if record.get('deleted_by') != current_user.get('username'):
        raise HTTPException(403, "Permission denied. You can only undo your own operation.")

    if not _check_undo_window(record['deleted_at'], "DELETE"):
        raise HTTPException(
            410,
            f"Undo window expired ({settings.UNDO_WINDOW_MINUTES_SINGLE} minutes). Cannot restore."
        )

    student_data = json.loads(record['student_json'])
    marks_data   = json.loads(record['marks_json'] or '[]')

    if not student_data or not student_data.get('usn'):
        raise HTTPException(400, "Invalid snapshot data.")

    usn = student_data['usn']

    try:
        with db_conn() as conn:
            conn.autocommit = False
            conn.start_transaction()
            cur = conn.cursor()

            try:
                cur.execute("SELECT usn FROM students WHERE usn=%s", (usn,))
                if cur.fetchone():
                    conn.rollback()
                    cur.close()
                    raise HTTPException(409, f"Student {usn} already exists in the database.")

                cols = [k for k in student_data if k not in ('created_at', 'updated_at')]
                placeholders = ', '.join(['%s'] * len(cols))
                col_names    = ', '.join([f'`{c}`' for c in cols])
                values       = [student_data[c] for c in cols]
                cur.execute(
                    f"INSERT INTO students ({col_names}) VALUES ({placeholders})",
                    values
                )

                for m in marks_data:
                    try:
                        cur.execute(
                            "INSERT IGNORE INTO marks (usn, semester, sgpa, year) VALUES (%s,%s,%s,%s)",
                            (m.get('usn'), m.get('semester'), m.get('sgpa'), m.get('year'))
                        )
                    except Exception:
                        pass

                cur.execute(
                    "UPDATE soft_deleted_students SET restored=1 WHERE restore_token=%s",
                    (token,)
                )

                conn.commit()
                cur.close()

            except HTTPException:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                cur.close()
                raise safe_http_error(500, e, "restore")

    except HTTPException:
        raise

    write_audit_log(
        action="RESTORED",
        username=current_user["username"],
        role=current_user["role"],
        target_table="students",
        target_id=usn,
        summary=f"Restored deleted student {student_data.get('name', usn)} ({usn})",
    )

    return {
        "success": True,
        "message": f"Student {student_data.get('name', usn)} restored successfully.",
        "usn": usn,
        "name": student_data.get('name', usn),
    }


@router.post("/restore/{token}")
def restore_student(token: str, current_user: dict = Depends(get_current_user)):
    """
    Unified restore endpoint.
    Handles global undo snapshots (DELETE, INSERT, UPDATE, UPLOAD, SEMESTER_UPDATE)
    and falls back to legacy soft_deleted_students table.
    Full transaction wrapping — undo either fully succeeds or fully rolls back.
    """
    # Check global undo snapshots first
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM global_undo_snapshots WHERE undo_token=%s AND undone=0",
            (token,)
        )
        record = cur.fetchone()
        cur.close()

    if not record:
        return _restore_legacy_soft_delete(token, current_user)

    # Check undo window
    ts = record['timestamp']
    if record.get('performed_by') != current_user.get('username'):
        raise HTTPException(403, "Permission denied. You can only undo your own operation.")

    snapshot_data = json.loads(record['snapshot_data'])
    existing_students = snapshot_data.get('existing_students', [])
    existing_marks = snapshot_data.get('existing_marks', [])
    new_usns = snapshot_data.get('new_usns', [])

    reverted_adds = 0
    reverted_updates = 0

    try:
        with db_conn() as conn:
            conn.autocommit = False
            conn.start_transaction()
            cur = conn.cursor()

            try:
                reason = _undo_block_reason(record, current_user, conn)
                if reason:
                    status = 403 if reason.startswith("Permission") else 409
                    raise HTTPException(status, reason)
                # 1. Delete rows that were INSERTED during the operation (new_usns)
                if new_usns:
                    format_strings = ','.join(['%s'] * len(new_usns))
                    cur.execute(
                        f"DELETE FROM marks WHERE usn IN ({format_strings})",
                        tuple(new_usns)
                    )
                    cur.execute(
                        f"DELETE FROM students WHERE usn IN ({format_strings})",
                        tuple(new_usns)
                    )
                    reverted_adds = len(new_usns)

                # 2. Revert updated/deleted students to their previous state
                for s in existing_students:
                    usn = s['usn']
                    # Delete current state
                    cur.execute("DELETE FROM marks WHERE usn=%s", (usn,))
                    cur.execute("DELETE FROM students WHERE usn=%s", (usn,))

                    # Re-insert previous state
                    cols = [k for k in s if k not in ('created_at', 'updated_at')]
                    placeholders = ', '.join(['%s'] * len(cols))
                    col_names    = ', '.join([f'`{c}`' for c in cols])
                    values       = [s[c] for c in cols]
                    cur.execute(
                        f"INSERT INTO students ({col_names}) VALUES ({placeholders})",
                        values
                    )
                    reverted_updates += 1

                # 3. Re-insert previous marks
                for m in existing_marks:
                    cols = [k for k in m if k != 'id']
                    placeholders = ', '.join(['%s'] * len(cols))
                    col_names    = ', '.join([f'`{c}`' for c in cols])
                    values       = [m[c] for c in cols]
                    try:
                        cur.execute(
                            f"INSERT IGNORE INTO marks ({col_names}) VALUES ({placeholders})",
                            values
                        )
                    except Exception:
                        pass

                # 4. Mark as undone
                cur.execute(
                    "UPDATE global_undo_snapshots SET undone=1, undone_by=%s, undone_at=NOW() WHERE undo_token=%s",
                    (current_user["username"], token)
                )
                if record['operation_type'] == 'DELETE':
                    cur.execute(
                        "UPDATE deletion_logs SET restored=1 WHERE restore_token=%s",
                        (token,)
                    )

                conn.commit()
                cur.close()

            except HTTPException:
                try:
                    conn.rollback()
                except Exception:
                    pass
                cur.close()
                raise
            except Exception as e:
                # Undo failed — rollback the undo itself
                try:
                    conn.rollback()
                except Exception:
                    pass
                cur.close()

                write_audit_log(
                    action="UNDO_FAILED",
                    username=current_user["username"],
                    role=current_user["role"],
                    target_table="global_undo_snapshots",
                    target_id=token,
                    summary=f"Undo of {record['operation_type']} FAILED and was rolled back: {e}",
                    success=False,
                    error_info=str(e),
                )

                raise safe_http_error(500, e, "restore")

    except HTTPException:
        raise

    write_audit_log(
        action="RESTORED" if canonical_operation_type(record['operation_type']) == 'DELETE' else "UNDO_SUCCESS",
        username=current_user["username"],
        role=current_user["role"],
        target_table="global_undo_snapshots",
        target_id=token,
        summary=(
            f"Undo of {record['operation_type']} succeeded. "
            f"Reverted {reverted_adds} new insert(s), {reverted_updates} update(s). "
            f"Performed by: {current_user['username']}"
        ),
    )

    return {
        "success": True,
        "message": {
            "ADD": "Student addition undone.",
            "DELETE": "Student deletion undone.",
            "UPDATE": "Student update undone.",
            "IMPORT": "Import undone.",
        }.get(canonical_operation_type(record['operation_type']), "Operation undone."),
        "operation_type": canonical_operation_type(record['operation_type']),
        "reverted_inserts": reverted_adds,
        "reverted_updates": reverted_updates,
    }


# ── Unified 6-section activity logs ───────────────────────────────────────────

@router.get("/activity")
def get_activity(current_user: dict = Depends(get_current_user)):
    """Unified recent activity across all sections including backups."""
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)

        # Searches
        cur.execute(
            "SELECT id, natural_query, user_role AS actor, timestamp "
            "FROM query_history ORDER BY timestamp DESC LIMIT 10"
        )
        searches = cur.fetchall()

        # Global Undo Snapshots (CRUD edits)
        cur.execute(
            "SELECT id, undo_token, operation_type, snapshot_data, performed_by AS actor, "
            "timestamp, description, undone, undone_at, committed, post_state_data "
            "FROM global_undo_snapshots WHERE committed=1 ORDER BY timestamp DESC LIMIT 30"
        )
        snapshots = cur.fetchall()

        # Recent Exports
        cur.execute(
            "SELECT id, format, record_count, exported_by AS actor, timestamp "
            "FROM export_logs ORDER BY timestamp DESC LIMIT 10"
        )
        exports = cur.fetchall()

        # Backups (Sprint 1)
        cur.execute(
            "SELECT id, backup_name, backup_type, size_bytes, status, verified, "
            "created_by AS actor, created_at AS timestamp, error_message "
            "FROM db_backups ORDER BY created_at DESC LIMIT 20"
        )
        backups_raw = cur.fetchall()

        # Audit log (recent important events)
        cur.execute(
            "SELECT id, usn, student_name, added_by, timestamp "
            "FROM addition_logs ORDER BY timestamp DESC LIMIT 10"
        )
        addition_rows = cur.fetchall()

        cur.execute(
            "SELECT id, usn, student_name, deleted_by, restore_token, timestamp "
            "FROM deletion_logs WHERE COALESCE(restored, 0)=0 ORDER BY timestamp DESC LIMIT 10"
        )
        deletion_rows = cur.fetchall()

        cur.execute(
            "SELECT id, username AS actor, role, action, target_table, summary, "
            "success, created_at AS timestamp "
            "FROM audit_log "
            "WHERE action IN ('ADDED','UPDATED','DELETED','RESTORED','UPLOAD_SUCCESS','UPLOAD_FAILED',"
            "'RESTORE_SUCCESS','RESTORE_FAILED','UNDO_SUCCESS','UNDO_FAILED','BACKUP_SUCCESS','BACKUP_FAILED',"
            "'LOGIN_SUCCESS','LOGIN_FAILED','LOGOUT') "
            "ORDER BY created_at DESC LIMIT 30"
        )
        audit_events = cur.fetchall()

        cur.close()

    # Every reversible database write is presented from the single persistent
    # snapshot stream.  Do not synthesize undo buttons from activity-only logs.
    additions = []
    deletions = []
    updates = []
    uploads = []
    semester_updates = []
    undo_operations = []

    for s in snapshots:
        try:
            data = json.loads(s["snapshot_data"])
        except Exception:
            data = {}

        post_state = json.loads(s["post_state_data"] or "{}") if s.get("post_state_data") else {}
        post_students_by_usn = {row.get("usn"): row for row in post_state.get("students", [])}
        affected_students = []
        for u in data.get("new_usns", []):
            # ADD snapshots have no student in their before-state.  Use the
            # committed post-state so Recent Added never renders blank cards.
            created = post_students_by_usn.get(u, {})
            affected_students.append({"usn": u, "name": created.get("name") or u, "table": "students table"})
        for est in data.get("existing_students", []):
            affected_students.append({
                "usn": est.get("usn"),
                "name": est.get("name") or est.get("usn"),
                "table": "students table",
            })

        card = {
            "id": s["id"],
            "operation_id": s["undo_token"],
            "undo_token": s["undo_token"],
            "operation_type": canonical_operation_type(s["operation_type"]),
            "actor": s["actor"],
            "timestamp": str(s["timestamp"]),
            "description": s["description"],
            "undone": s["undone"],
            "affected_students": affected_students,
        }
        primary = affected_students[0] if affected_students else {}
        card["usn"] = primary.get("usn")
        card["student_name"] = primary.get("name") or primary.get("usn")
        raw_operation_type = (s["operation_type"] or "").upper()
        operation_type = canonical_operation_type(raw_operation_type)
        if operation_type == "ADD":
            card["added_by"] = s["actor"]
        elif operation_type == "DELETE":
            card["deleted_by"] = s["actor"]
            card["restore_token"] = s["undo_token"]

        if s["undone"]:
            card["status"] = "UNDONE"
            card["can_undo"] = False
            undo_operations.append({
                **card,
                "operation_id": f"undo:{s['undo_token']}",
                "operation_type": "UNDO",
                "timestamp": str(s.get("undone_at") or s["timestamp"]),
                "description": f"Undo {canonical_operation_type(s['operation_type'])}: {s['description']}",
                "undo_token": None,
                "can_undo": False,
            })
        else:
            reason = _undo_block_reason(s, current_user)
            # The operation itself succeeded even when its undo window later
            # expires. Keep machine-readable operation status separate from
            # undo availability so a valid DELETE is never labelled as failed.
            card["status"] = "SUCCESS"
            card["can_undo"] = not bool(reason)
            if reason:
                card["undo_unavailable_reason"] = reason

        op = operation_type
        if op == "ADD":
            additions.append(card)
        elif op == "DELETE":
            deletions.append(card)
        elif op == "UPDATE":
            updates.append(card)
        elif op == "IMPORT":
            uploads.append(card)
        if raw_operation_type == "SEMESTER_UPDATE":
            semester_updates.append(card)

    # Process backups for activity stream
    backups = []
    for b in backups_raw:
        if b.get("timestamp"):
            b["timestamp"] = str(b["timestamp"])
        backups.append({
            "id": b["id"],
            "backup_name": b["backup_name"],
            "backup_type": b["backup_type"],
            "size_bytes": b["size_bytes"],
            "status": b["status"],
            "verified": b["verified"],
            "actor": b["actor"],
            "timestamp": b["timestamp"],
            "error_message": b.get("error_message"),
        })

    # Format dates
    for r in searches:
        if r.get("timestamp"):
            r["timestamp"] = str(r["timestamp"])
    for r in exports:
        if r.get("timestamp"):
            r["timestamp"] = str(r["timestamp"])
    for r in audit_events:
        if r.get("timestamp"):
            r["timestamp"] = str(r["timestamp"])

    return {
        "searches": searches,
        "additions": additions[:10],
        "deletions": deletions[:10],
        "updates": updates[:10],
        "uploads": uploads[:10],
        "exports": exports,
        "semester_updates": semester_updates[:10],
        "undo_operations": undo_operations[:10],
        "backups": backups[:10],
        "audit_events": audit_events[:20],
        "recent_operations": sorted(
            additions + deletions + updates + uploads + semester_updates + undo_operations,
            key=lambda item: item.get("timestamp", ""), reverse=True
        )[:10],
    }


# ── Student change history ────────────────────────────────────────────────────

@router.get("/history/{usn}")
def get_student_history(usn: str, current_user: dict = Depends(get_current_user)):
    """Returns field-level change history for a student."""
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM student_history WHERE usn=%s ORDER BY updated_at DESC LIMIT 50",
            (usn,)
        )
        rows = cur.fetchall()
        cur.close()

    for r in rows:
        if r.get('updated_at'):
            r['updated_at'] = str(r['updated_at'])

    return rows
