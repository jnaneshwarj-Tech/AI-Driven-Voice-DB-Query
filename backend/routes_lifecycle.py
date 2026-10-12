"""
routes_lifecycle.py — Student Lifecycle Management (discontinuation, dropout,
readmission, rejoining, VTU-aligned academic lifecycle).

Integration notes:
  * Uses the existing auth model (require_roles) and the existing undo system
    (create_undo_snapshot / finalize_undo_snapshot) and audit_log writer.
  * Every status change is an APPEND to student_lifecycle_events (authoritative
    history) plus a derived update to student_lifecycle_status and
    students.lifecycle_status. Nothing here deletes or alters academic,
    personal, fee, semester or backlog records.
  * Readmission decisions and eligibility are advisory only; the software never
    auto-approves — an authorized Admin records the human decision.
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user, require_roles
from database import db_conn, write_audit_log
from routes_undo import create_undo_snapshot, finalize_undo_snapshot
import lifecycle as LC

router = APIRouter(prefix="/api/lifecycle", tags=["Student Lifecycle"])


class StatusChangeRequest(BaseModel):
    to_status: str
    event_type: Optional[str] = None
    effective_date: Optional[str] = None
    last_enrolled_semester: Optional[int] = None
    last_enrolled_academic_year: Optional[str] = None
    reason: Optional[str] = None
    reason_category: Optional[str] = None
    document_ref: Optional[str] = None
    scheme: Optional[str] = None
    academic_year: Optional[str] = None
    remarks: Optional[str] = None


class NlRecordRequest(BaseModel):
    natural_query: str
    language: Optional[str] = None
    # Optional explicit USN when the user selected one from an ambiguous list.
    usn: Optional[str] = None


class NlConfirmRequest(BaseModel):
    payload: dict
    confirmation_token: str


class ReadmissionRequestModel(BaseModel):
    requested_semester: Optional[int] = None
    request_date: Optional[str] = None
    scheme: Optional[str] = None
    remarks: Optional[str] = None


class ReadmissionDecisionModel(BaseModel):
    decision: str  # approve | reject
    approved_semester: Optional[int] = None
    approval_date: Optional[str] = None
    approval_ref: Optional[str] = None
    rejoin: bool = False
    rejoin_date: Optional[str] = None
    remarks: Optional[str] = None


class IdentityLinkRequest(BaseModel):
    related_usn: str
    relation_type: str
    note: Optional[str] = None


# Controlled, whitelisted identity-relation types (spec §3). A link is ONLY a
# recorded relationship — it never merges, moves or deletes any academic,
# personal, fee or backlog record. The two USNs remain fully independent rows.
ALLOWED_RELATION_TYPES = {
    "READMISSION_NEW_USN", "READMISSION_OLD_USN", "SCHEME_CHANGE",
    "BRANCH_CHANGE", "NAME_CORRECTION", "DUPLICATE_REGISTER",
}


class VerifiedPassClearModel(BaseModel):
    result_ref: Optional[str] = None      # official VTU result / pass reference
    cleared_date: Optional[str] = None
    remarks: Optional[str] = None


# ── internal helpers ─────────────────────────────────────────────────────────
def _student_exists(cur, usn: str) -> dict | None:
    cur.execute("SELECT usn, name, lifecycle_status FROM students WHERE usn=%s", (usn,))
    return cur.fetchone()


def _current_status(cur, usn: str) -> str:
    cur.execute("SELECT current_status FROM student_lifecycle_status WHERE usn=%s", (usn,))
    row = cur.fetchone()
    if row and row.get("current_status"):
        return row["current_status"]
    cur.execute("SELECT lifecycle_status FROM students WHERE usn=%s", (usn,))
    s = cur.fetchone()
    return (s or {}).get("lifecycle_status") or LC.STATUS_ACTIVE


_EVENT_FIELDS = (
    "effective_date", "last_enrolled_semester", "last_enrolled_academic_year",
    "requested_semester", "approved_semester", "request_date", "approval_date",
    "rejoin_date", "scheme", "academic_year", "reason", "reason_category",
    "document_ref", "approval_ref", "remarks",
)


def _append_event(cur, usn, event_type, from_status, to_status, fields, actor):
    cols = ["usn", "event_type", "from_status", "to_status",
            "actor_username", "actor_role"] + list(fields.keys())
    vals = [usn, event_type, from_status, to_status,
            actor.get("username"), actor.get("role")] + list(fields.values())
    placeholders = ",".join(["%s"] * len(vals))
    cur.execute(
        f"INSERT INTO student_lifecycle_events ({','.join('`'+c+'`' for c in cols)}) "
        f"VALUES ({placeholders})", vals)


def _set_current(cur, usn, to_status, fields, actor):
    cur.execute(
        """INSERT INTO student_lifecycle_status
               (usn, current_status, effective_date, last_enrolled_semester,
                last_enrolled_academic_year, scheme, reason, reason_category,
                document_ref, updated_by)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON DUPLICATE KEY UPDATE
               current_status=VALUES(current_status),
               effective_date=COALESCE(VALUES(effective_date), effective_date),
               last_enrolled_semester=COALESCE(VALUES(last_enrolled_semester), last_enrolled_semester),
               last_enrolled_academic_year=COALESCE(VALUES(last_enrolled_academic_year), last_enrolled_academic_year),
               scheme=COALESCE(VALUES(scheme), scheme),
               reason=COALESCE(VALUES(reason), reason),
               reason_category=COALESCE(VALUES(reason_category), reason_category),
               document_ref=COALESCE(VALUES(document_ref), document_ref),
               updated_by=VALUES(updated_by)""",
        (usn, to_status, fields.get("effective_date"),
         fields.get("last_enrolled_semester"), fields.get("last_enrolled_academic_year"),
         fields.get("scheme"), fields.get("reason"), fields.get("reason_category"),
         fields.get("document_ref"), actor.get("username")))
    cur.execute("UPDATE students SET lifecycle_status=%s WHERE usn=%s", (to_status, usn))


def _pick_fields(req: dict) -> dict:
    return {k: req.get(k) for k in _EVENT_FIELDS if req.get(k) is not None}


def _resolve_category(fields: dict) -> dict:
    """Store a reason category the register can actually filter on: an explicit
    one is validated against the controlled vocabulary (an off-vocabulary value
    would be invisible to the dropdown, the exports and every NL 'due to …'
    question, so it is refused), and a dialog that only typed a reason gets a
    category derived from it instead of loose text nobody can query."""
    try:
        fields["reason_category"] = LC.resolve_reason_category(
            fields.get("reason_category"), fields.get("reason"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return fields


def _apply_status_change(cur, conn, usn, to_status, fields, event_type, actor,
                         description):
    """Shared, transactional commit used by the explicit status endpoint and the
    natural-language confirm endpoint. Creates an undo snapshot, APPENDS an
    event, updates the derived cache, and finalizes — all within the caller's
    transaction. Raises on failure so the caller rolls back.

    The repeated-record guard lives here, not in the callers, so that neither
    write path can forget it: a staff member who submits the same status, date
    and reason twice gets one event, whichever button they used."""
    from_status = _current_status(cur, usn)
    if LC.is_duplicate_lifecycle_event(cur, usn, to_status,
                                       fields.get("effective_date"),
                                       fields.get("reason_category")):
        return from_status, None, True
    token = create_undo_snapshot("UPDATE", [usn], actor.get("username", ""),
                                 description, conn=conn)
    _append_event(cur, usn, event_type, from_status, to_status, fields, actor)
    _set_current(cur, usn, to_status, fields, actor)
    finalize_undo_snapshot(token, [usn], conn)
    return from_status, token, False


# ── read endpoints ────────────────────────────────────────────────────────────
@router.get("/options")
def get_options(current_user: dict = Depends(get_current_user)):
    return {
        "statuses": LC.LIFECYCLE_STATUSES,
        "active_statuses": sorted(LC.ACTIVE_STATUSES),
        "discontinued_statuses": sorted(LC.DISCONTINUED_STATUSES),
        "reason_categories": LC.REASON_CATEGORIES,
        "transitions": {s: LC.next_actions(s) for s in LC.LIFECYCLE_STATUSES},
        "event_types": [LC.EV_STATUS_CHANGE, LC.EV_DISCONTINUE,
                        LC.EV_READMISSION_REQUEST, LC.EV_READMISSION_DECISION,
                        LC.EV_REJOIN, LC.EV_CORRECTION],
    }


@router.get("/students/{usn}")
def get_student_lifecycle(usn: str, current_user: dict = Depends(get_current_user)):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        student = _student_exists(cur, usn)
        if not student:
            raise HTTPException(status_code=404, detail="Student not found.")
        cur.execute(
            "SELECT * FROM student_lifecycle_status WHERE usn=%s", (usn,))
        status_row = cur.fetchone()
        cur.execute(
            "SELECT * FROM student_lifecycle_events WHERE usn=%s "
            "ORDER BY created_at ASC, id ASC", (usn,))
        events = cur.fetchall()
        cur.execute(
            "SELECT * FROM readmission_requests WHERE usn=%s ORDER BY id ASC", (usn,))
        requests = cur.fetchall()
        cur.execute(
            "SELECT usn, related_usn, relation_type, note, created_by, created_at "
            "FROM student_identity_links WHERE usn=%s OR related_usn=%s", (usn, usn))
        links = cur.fetchall()
        cur.close()
    return {
        "usn": usn, "name": student["name"],
        "current_status": (status_row or {}).get("current_status")
                          or student.get("lifecycle_status") or LC.STATUS_ACTIVE,
        "status": status_row, "history": events,
        "readmission_requests": requests, "identity_links": links,
    }


@router.get("/list")
def list_lifecycle(
    status: Optional[str] = None, scheme: Optional[str] = None,
    admission_year: Optional[int] = None, branch: Optional[str] = None,
    last_semester: Optional[int] = None,
    reason_category: Optional[str] = None,
    date_from: Optional[str] = None, date_to: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: Optional[str] = None, sort_dir: Optional[str] = None,
    limit: Optional[int] = None, offset: int = 0,
    current_user: dict = Depends(require_roles("Staff", "Admin")),
):
    where, params = [], []
    if status:
        norm = LC.normalize_status(status)
        if not norm:
            raise HTTPException(status_code=400, detail="Unknown lifecycle status.")
        where.append("COALESCE(ls.current_status, s.lifecycle_status)=%s")
        params.append(norm)
    if scheme:
        where.append("ls.scheme=%s"); params.append(scheme)
    if admission_year:
        where.append("s.admission_year=%s"); params.append(admission_year)
    if branch:
        where.append("LOWER(s.branch) LIKE %s"); params.append(f"%{branch.lower()}%")
    if last_semester:
        where.append("ls.last_enrolled_semester=%s"); params.append(last_semester)
    if reason_category:
        rc = (reason_category or "").strip().lower()
        if rc and rc not in LC.REASON_CATEGORIES:
            raise HTTPException(status_code=400, detail="Unknown reason category.")
        if rc:
            where.append("ls.reason_category=%s"); params.append(rc)
    if date_from:
        where.append("ls.effective_date >= %s"); params.append(date_from)
    if date_to:
        where.append("ls.effective_date <= %s"); params.append(date_to)
    if search:
        term = f"%{(search or '').strip()}%"
        where.append("(s.usn LIKE %s OR s.name LIKE %s OR ls.reason LIKE %s)")
        params.extend([term, term, term])

    # Whitelisted sort keys only — never interpolate an untrusted identifier.
    sort_col = {
        "usn": "s.usn", "name": "s.name", "branch": "s.branch",
        "admission_year": "s.admission_year", "effective_date": "ls.effective_date",
        "current_status": "current_status", "last_enrolled_semester": "ls.last_enrolled_semester",
    }.get((sort_by or "").strip()) or "s.usn"
    order = "DESC" if (sort_dir or "").strip().lower() == "desc" else "ASC"

    sql = (
        "SELECT s.usn, s.name, s.branch, s.admission_year, s.student_type, "
        "COALESCE(ls.current_status, s.lifecycle_status, 'Active') AS current_status, "
        "ls.effective_date, ls.last_enrolled_semester, ls.scheme, "
        "ls.reason, ls.reason_category "
        "FROM students s LEFT JOIN student_lifecycle_status ls ON ls.usn=s.usn"
    )
    count_sql = (
        "SELECT COUNT(*) AS total FROM students s "
        "LEFT JOIN student_lifecycle_status ls ON ls.usn=s.usn"
    )
    if where:
        clause = " WHERE " + " AND ".join(where)
        sql += clause
        count_sql += clause
    sql += f" ORDER BY {sort_col} {order}"
    if limit is not None and limit > 0:
        sql += " LIMIT %s OFFSET %s"
        page_params = params + [limit, max(0, offset)]
    else:
        page_params = params

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(count_sql, params)
        total = (cur.fetchone() or {}).get("total", 0)
        cur.execute(sql, page_params)
        rows = cur.fetchall()
        # Attach latest event description per row (cheap, bounded by page size).
        usns = [r["usn"] for r in rows]
        latest = {}
        if usns:
            placeholders = ",".join(["%s"] * len(usns))
            cur.execute(
                f"SELECT usn, event_type, to_status, created_at FROM student_lifecycle_events "
                f"WHERE usn IN ({placeholders}) ORDER BY created_at ASC, id ASC", usns)
            for ev in cur.fetchall():
                latest[ev["usn"]] = ev  # last write wins = latest event
        cur.close()
    for r in rows:
        ev = latest.get(r["usn"])
        r["latest_event_type"] = (ev or {}).get("event_type")
        r["latest_event_at"] = (ev or {}).get("created_at")
    return {"total_count": total, "count": len(rows), "offset": offset,
            "data": rows}


@router.get("/export")
def export_lifecycle(
    fmt: str = "csv",
    status: Optional[str] = None, scheme: Optional[str] = None,
    admission_year: Optional[int] = None, branch: Optional[str] = None,
    last_semester: Optional[int] = None,
    reason_category: Optional[str] = None,
    date_from: Optional[str] = None, date_to: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: Optional[str] = None, sort_dir: Optional[str] = None,
    current_user: dict = Depends(require_roles("Staff", "Admin")),
):
    """Export the CURRENTLY FILTERED lifecycle list as a flat table
    (csv|xlsx|pdf). Reuses the same low-level reporting primitives (branding,
    table style, export audit log) as the student exports, but renders ONE list
    of the §3 columns instead of a full profile per student. The columns are all
    non-sensitive lifecycle facts, so no PII masking is bypassed."""
    fmt = (fmt or "csv").strip().lower()
    if fmt not in {"csv", "xlsx", "pdf"}:
        raise HTTPException(status_code=400, detail="fmt must be csv, xlsx or pdf.")
    result = list_lifecycle(
        status=status, scheme=scheme, admission_year=admission_year, branch=branch,
        last_semester=last_semester, reason_category=reason_category,
        date_from=date_from, date_to=date_to, search=search,
        sort_by=sort_by, sort_dir=sort_dir, limit=None, offset=0,
        current_user=current_user)
    rows = result["data"]
    if not rows:
        raise HTTPException(status_code=400, detail="No lifecycle records to export.")

    columns = [
        ("usn", "USN"), ("name", "Name"), ("branch", "Branch"),
        ("admission_year", "Batch"), ("last_enrolled_semester", "Last Semester"),
        ("effective_date", "Status Effective Date"), ("reason", "Reason"),
        ("reason_category", "Reason Category"), ("current_status", "Status"),
        ("latest_event_type", "Latest Event"), ("latest_event_at", "Latest Event At"),
    ]
    import routes_export as EX
    EX._log_export(f"lifecycle_{fmt}", len(rows), current_user.get("username", ""))
    title = "Student Lifecycle Register"
    return _render_lifecycle_table(fmt, title, columns, rows)


def _render_lifecycle_table(fmt: str, title: str, columns, rows):
    import tempfile, os, csv as _csv
    from fastapi.responses import FileResponse
    headers = [lbl for _, lbl in columns]

    def cell(v):
        return "—" if v in (None, "") else str(v)

    fd, path = tempfile.mkstemp(suffix="." + fmt)
    os.close(fd)

    if fmt == "csv":
        with open(path, "w", encoding="utf-8", newline="") as fh:
            w = _csv.writer(fh)
            w.writerow([title])
            w.writerow(headers)
            for r in rows:
                w.writerow([cell(r.get(k)) for k, _ in columns])
        return FileResponse(path, filename="lifecycle_register.csv",
                            media_type="text/csv; charset=utf-8")

    if fmt == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        wb = Workbook(); ws = wb.active; ws.title = "Lifecycle"
        ws.append([title]); ws.cell(row=1, column=1).font = Font(bold=True, size=13)
        ws.append([])
        ws.append(headers)
        hr = ws.max_row
        for c in range(1, len(headers) + 1):
            ws.cell(row=hr, column=c).font = Font(bold=True, color="FFFFFF")
            ws.cell(row=hr, column=c).fill = PatternFill("solid", fgColor="1e3a5f")
        for r in rows:
            ws.append([cell(r.get(k)) for k, _ in columns])
        for col in ws.columns:
            letter = col[0].column_letter
            width = max((len(str(c.value)) for c in col if c.value is not None), default=10)
            ws.column_dimensions[letter].width = min(width + 2, 42)
        wb.save(path)
        return FileResponse(path, filename="lifecycle_register.xlsx",
                            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # pdf
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.platypus import SimpleDocTemplate, Spacer, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet
    doc = SimpleDocTemplate(path, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Spacer(1, 8)]
    data = [headers] + [[Paragraph(cell(r.get(k)), styles["BodyText"]) for k, _ in columns]
                        for r in rows]
    story.append(_lifecycle_pdf_table(data))
    doc.build(story)
    return FileResponse(path, filename="lifecycle_register.pdf", media_type="application/pdf")


def _lifecycle_pdf_table(data):
    from reportlab.platypus import Table, TableStyle
    from reportlab.lib import colors
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


@router.get("/eligibility/{usn}")
def eligibility(
    usn: str, requested_semester: Optional[int] = None, scheme: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        if not _student_exists(cur, usn):
            raise HTTPException(status_code=404, detail="Student not found.")
        result = LC.evaluate_eligibility(cur, usn, requested_semester, scheme)
        cur.close()
    return result


# ── write endpoints (audited, transactional, undoable) ────────────────────────
@router.post("/students/{usn}/status")
def change_status(
    usn: str, req: StatusChangeRequest,
    current_user: dict = Depends(require_roles("Admin")),
):
    to_status = LC.normalize_status(req.to_status)
    if not to_status:
        raise HTTPException(status_code=400, detail="Invalid lifecycle status.")
    fields = _resolve_category(_pick_fields(req.model_dump()))
    event_type = req.event_type or LC.EV_STATUS_CHANGE
    with db_conn() as conn:
        conn.autocommit = False
        conn.start_transaction()
        cur = conn.cursor(dictionary=True)
        if not _student_exists(cur, usn):
            conn.rollback(); cur.close()
            raise HTTPException(status_code=404, detail="Student not found.")
        try:
            from_status, token, dedup = _apply_status_change(
                cur, conn, usn, to_status, fields, event_type, current_user,
                f"lifecycle status → {to_status}")
            conn.commit()
        except Exception as e:
            conn.rollback(); cur.close()
            write_audit_log("lifecycle_status_change", current_user.get("username"),
                            current_user.get("role"), "student_lifecycle_events", usn,
                            f"status→{to_status}", success=False, error_info=str(e)[:500])
            raise HTTPException(status_code=400, detail="Status change failed.")
        cur.close()
    if dedup:
        write_audit_log("lifecycle_status_change", current_user.get("username"),
                        current_user.get("role"), "student_lifecycle_events", usn,
                        f"duplicate suppressed → {to_status}")
        return {"usn": usn, "from_status": from_status, "to_status": to_status,
                "deduplicated": True, "undo_token": None,
                "message": "This lifecycle event is already recorded; no duplicate created."}
    write_audit_log("lifecycle_status_change", current_user.get("username"),
                    current_user.get("role"), "student_lifecycle_events", usn,
                    f"{from_status} → {to_status} ({event_type})")
    return {"usn": usn, "from_status": from_status, "to_status": to_status,
            "deduplicated": False, "undo_token": token}


# ── §1 natural-language recording (preview → authorized confirm) ──────────────
def _event_type_for_status(to_status: str) -> str:
    if to_status in LC.DISCONTINUED_STATUSES:
        return LC.EV_DISCONTINUE
    if to_status == LC.STATUS_REJOINED:
        return LC.EV_REJOIN
    return LC.EV_STATUS_CHANGE


def _prepare_lifecycle_payload(nq_raw: str, language: Optional[str],
                               explicit_usn: Optional[str], username: str):
    """Parse a natural-language lifecycle command, resolve the student against
    MySQL, and build (but do NOT save) a confirmation preview + token.

    Returns a dict shaped for the frontend:
      {'action_required': 'confirm', 'payload': {...}, 'confirmation_token': ...}
      {'action_required': 'select_student', 'suggestions': [...], 'message': ...}
      {'action_required': 'clarify', 'message': ...}
      {'action_required': 'no_record', 'message': ...}
    Raises nothing on missing/ambiguous identity — those are data responses,
    never 404s, because §1 requires: unidentified → do NOT create a record."""
    nq = (nq_raw or "").strip()
    if not nq:
        return {"action_required": "clarify",
                "message": "Please describe the lifecycle action, e.g. "
                           "'USN 4HG23CS032 discontinued due to financial problems'."}

    # Reuse the SAME multilingual pipeline as the query engine (never a second
    # language system). Translate Kannada/mixed to English, then normalize.
    translated = nq
    if language in ("kannada", "mixed"):
        try:
            from translation_service import translate_query_if_needed
            translated, _ = translate_query_if_needed(nq, language)
        except Exception:
            pass
    try:
        from kannada_processor import normalize_query as kn_normalize_query
        normalized, _ = kn_normalize_query(translated)
    except Exception:
        normalized = translated

    parsed = LC.parse_lifecycle_command(normalized)
    to_status = LC.normalize_status(parsed.get("target_status") or "")

    if not to_status:
        # Not a recognised lifecycle verb — do not guess or create anything.
        return {"action_required": "clarify",
                "message": "I could not identify a lifecycle status (discontinued / "
                           "dropout / readmission / rejoined / graduated / transferred). "
                           "Please restate which status to record."}

    # Resolve identity against MySQL through the existing resolver — never raw SQL.
    from routes_query import _match_student
    target = (explicit_usn or parsed.get("usn") or parsed.get("target_text") or "").strip()
    if not target:
        return {"action_required": "clarify",
                "message": "Which student? Please give a USN or name."}

    if explicit_usn or parsed.get("usn"):
        # USN path: verify existence; unknown USN → no record (never create).
        try:
            match = _match_student(target)
        except HTTPException as e:
            if e.status_code == 404:
                return {"action_required": "no_record",
                        "message": f"No student found for '{target}'. "
                                   "No record was created."}
            raise
    else:
        try:
            match = _match_student(target)
        except HTTPException as e:
            if e.status_code == 404:
                return {"action_required": "no_record",
                        "message": f"I couldn't confidently match '{target}' to a student, "
                                   "so no record was created. Please provide the USN."}
            raise

    if match.get("ambiguous"):
        picks = [{"usn": s.get("usn"), "name": s.get("name"),
                  "branch": s.get("branch"), "score": s.get("score")}
                 for s in match["ambiguous"]]
        return {"action_required": "select_student", "suggestions": picks,
                "message": "Multiple students match. Please select the correct USN "
                           "before recording the status."}

    student = match.get("student") or {}
    usn = student.get("usn")
    if not usn:
        return {"action_required": "no_record",
                "message": "Student could not be resolved. No record was created."}

    payload = {
        "usn": usn,
        "name": student.get("name"),
        "to_status": to_status,
        "event_type": _event_type_for_status(to_status),
        "effective_date": parsed.get("effective_date"),
        "last_enrolled_semester": parsed.get("last_enrolled_semester"),
        "last_enrolled_academic_year": parsed.get("academic_year"),
        "reason": parsed.get("reason_text"),
        "reason_category": parsed.get("reason_category"),
        "document_ref": parsed.get("document_ref"),
        "original_query": nq,
    }
    from query_security_validator import create_confirmation_token
    token = create_confirmation_token(payload, username)
    return {"action_required": "confirm", "payload": payload,
            "confirmation_token": token,
            "message": f"Confirm: mark {student.get('name')} ({usn}) as "
                       f"'{to_status}'?"}


@router.post("/nl/record")
def nl_record(
    req: NlRecordRequest,
    current_user: dict = Depends(require_roles("Staff", "Admin")),
):
    """Parse + preview only. Saves nothing — §1: record after authorized confirm."""
    result = _prepare_lifecycle_payload(
        req.natural_query, req.language, req.usn,
        current_user.get("username", ""))
    return result


@router.post("/nl/confirm")
def nl_confirm(
    req: NlConfirmRequest,
    current_user: dict = Depends(require_roles("Admin")),
):
    """Authorized commit of a previewed lifecycle record (Admin only). Verifies
    ownership + integrity of the confirmation token, re-checks the student exists,
    guards against duplicate events, then appends the event transactionally."""
    from query_security_validator import verify_confirmation_token
    payload = req.payload or {}
    usn = str(payload.get("usn") or "").strip()
    to_status = LC.normalize_status(payload.get("to_status") or "")
    if not usn or not to_status:
        raise HTTPException(status_code=400, detail="Invalid confirmation payload.")
    if not verify_confirmation_token(req.confirmation_token, payload,
                                     current_user.get("username", "")):
        raise HTTPException(status_code=403,
                            detail="Confirmation expired or does not match this user/query.")

    fields = _resolve_category(
        {k: payload.get(k) for k in _EVENT_FIELDS if payload.get(k) is not None})
    event_type = payload.get("event_type") or _event_type_for_status(to_status)

    with db_conn() as conn:
        conn.autocommit = False
        conn.start_transaction()
        cur = conn.cursor(dictionary=True)
        if not _student_exists(cur, usn):
            conn.rollback(); cur.close()
            raise HTTPException(status_code=404, detail="Student not found.")
        try:
            from_status, token, dedup = _apply_status_change(
                cur, conn, usn, to_status, fields, event_type, current_user,
                f"NL lifecycle record → {to_status}")
            conn.commit()
        except Exception as e:
            conn.rollback(); cur.close()
            write_audit_log("lifecycle_nl_confirm", current_user.get("username"),
                            current_user.get("role"), "student_lifecycle_events", usn,
                            f"status→{to_status}", success=False, error_info=str(e)[:500])
            raise HTTPException(status_code=400, detail="Could not record lifecycle status.")
        cur.close()
    if dedup:
        write_audit_log("lifecycle_nl_confirm", current_user.get("username"),
                        current_user.get("role"), "student_lifecycle_events", usn,
                        f"duplicate suppressed → {to_status}")
        return {"usn": usn, "from_status": from_status, "to_status": to_status,
                "deduplicated": True, "undo_token": None,
                "message": "This lifecycle event is already recorded; no duplicate created."}
    write_audit_log("lifecycle_nl_confirm", current_user.get("username"),
                    current_user.get("role"), "student_lifecycle_events", usn,
                    f"{from_status} → {to_status} ({event_type})")
    return {"usn": usn, "from_status": from_status, "to_status": to_status,
            "event_type": event_type, "deduplicated": False, "undo_token": token}


@router.post("/students/{usn}/readmission/request")
def create_readmission_request(
    usn: str, req: ReadmissionRequestModel,
    current_user: dict = Depends(require_roles("Staff", "Admin")),
):
    fields = {"requested_semester": req.requested_semester,
              "request_date": req.request_date, "scheme": req.scheme,
              "remarks": req.remarks, "effective_date": req.request_date}
    with db_conn() as conn:
        conn.autocommit = False
        conn.start_transaction()
        cur = conn.cursor(dictionary=True)
        if not _student_exists(cur, usn):
            conn.rollback(); cur.close()
            raise HTTPException(status_code=404, detail="Student not found.")
        token = create_undo_snapshot(
            "UPDATE", [usn], current_user.get("username", ""),
            "readmission request", conn=conn)
        from_status = _current_status(cur, usn)
        elig = LC.evaluate_eligibility(cur, usn, req.requested_semester, req.scheme)
        try:
            cur.execute(
                "INSERT INTO readmission_requests (usn, requested_semester, request_date, "
                "scheme, eligibility_outcome, eligibility_flags, status) "
                "VALUES (%s,%s,%s,%s,%s,%s,'Requested')",
                (usn, req.requested_semester, req.request_date, req.scheme,
                 elig["outcome"], json.dumps(elig)))
            req_id = cur.lastrowid
            _append_event(cur, usn, LC.EV_READMISSION_REQUEST, from_status,
                          LC.STATUS_READMISSION_REQUESTED, fields, current_user)
            _set_current(cur, usn, LC.STATUS_READMISSION_REQUESTED, fields, current_user)
            finalize_undo_snapshot(token, [usn], conn)
            conn.commit()
        except Exception as e:
            conn.rollback(); cur.close()
            write_audit_log("readmission_request", current_user.get("username"),
                            current_user.get("role"), "readmission_requests", usn,
                            success=False, error_info=str(e)[:500])
            raise HTTPException(status_code=400, detail="Readmission request failed.")
        cur.close()
    write_audit_log("readmission_request", current_user.get("username"),
                    current_user.get("role"), "readmission_requests", usn,
                    f"requested sem {req.requested_semester}; outcome={elig['outcome']}")
    return {"usn": usn, "request_id": req_id, "eligibility": elig,
            "to_status": LC.STATUS_READMISSION_REQUESTED, "undo_token": token}


@router.post("/students/{usn}/readmission/decision")
def decide_readmission(
    usn: str, req: ReadmissionDecisionModel,
    current_user: dict = Depends(require_roles("Admin")),
):
    decision = (req.decision or "").strip().lower()
    if decision not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="decision must be approve or reject.")
    with db_conn() as conn:
        conn.autocommit = False
        conn.start_transaction()
        cur = conn.cursor(dictionary=True)
        if not _student_exists(cur, usn):
            conn.rollback(); cur.close()
            raise HTTPException(status_code=404, detail="Student not found.")
        cur.execute("SELECT id, status FROM readmission_requests WHERE usn=%s "
                    "ORDER BY id DESC LIMIT 1", (usn,))
        rr = cur.fetchone()
        if not rr:
            conn.rollback(); cur.close()
            raise HTTPException(status_code=400, detail="No readmission request on file.")
        token = create_undo_snapshot(
            "UPDATE", [usn], current_user.get("username", ""),
            f"readmission {decision}", conn=conn)
        from_status = _current_status(cur, usn)
        if decision == "approve":
            to_status = LC.STATUS_REJOINED if req.rejoin else LC.STATUS_READMISSION_APPROVED
        else:
            to_status = LC.STATUS_DISCONTINUED_REVIEW
        fields = {"approved_semester": req.approved_semester,
                  "approval_date": req.approval_date, "approval_ref": req.approval_ref,
                  "rejoin_date": req.rejoin_date if req.rejoin else None,
                  "remarks": req.remarks, "effective_date": req.approval_date}
        try:
            new_rr_status = ("Joined" if (decision == "approve" and req.rejoin)
                             else "Approved" if decision == "approve" else "Rejected")
            cur.execute(
                "UPDATE readmission_requests SET status=%s, approved_semester=%s, "
                "approval_date=%s, approval_ref=%s, rejoin_date=%s, decided_by=%s, remarks=%s "
                "WHERE id=%s",
                (new_rr_status, req.approved_semester, req.approval_date,
                 req.approval_ref, req.rejoin_date if req.rejoin else None,
                 current_user.get("username"), req.remarks, rr["id"]))
            _append_event(cur, usn, LC.EV_READMISSION_DECISION, from_status,
                          to_status, fields, current_user)
            _set_current(cur, usn, to_status, fields, current_user)
            finalize_undo_snapshot(token, [usn], conn)
            conn.commit()
        except Exception as e:
            conn.rollback(); cur.close()
            write_audit_log("readmission_decision", current_user.get("username"),
                            current_user.get("role"), "readmission_requests", usn,
                            success=False, error_info=str(e)[:500])
            raise HTTPException(status_code=400, detail="Readmission decision failed.")
        cur.close()
    write_audit_log("readmission_decision", current_user.get("username"),
                    current_user.get("role"), "readmission_requests", usn,
                    f"{decision}{' + rejoin' if req.rejoin else ''} → {to_status}")
    return {"usn": usn, "decision": decision, "from_status": from_status,
            "to_status": to_status, "undo_token": token}


# ── §3 controlled identity links (recorded relationships, never a merge) ──────
@router.get("/students/{usn}/identity-links")
def list_identity_links(usn: str, current_user: dict = Depends(get_current_user)):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        if not _student_exists(cur, usn):
            cur.close()
            raise HTTPException(status_code=404, detail="Student not found.")
        cur.execute(
            "SELECT usn, related_usn, relation_type, note, created_by, created_at "
            "FROM student_identity_links WHERE usn=%s OR related_usn=%s "
            "ORDER BY created_at ASC, id ASC", (usn, usn))
        links = cur.fetchall()
        cur.close()
    return {"usn": usn, "links": links}


@router.post("/students/{usn}/identity-links")
def create_identity_link(
    usn: str, req: IdentityLinkRequest,
    current_user: dict = Depends(require_roles("Admin")),
):
    relation = (req.relation_type or "").strip().upper()
    if relation not in ALLOWED_RELATION_TYPES:
        raise HTTPException(status_code=400, detail="Unknown identity relation type.")
    related = (req.related_usn or "").strip().upper()
    if not related or related == usn.strip().upper():
        raise HTTPException(status_code=400, detail="related_usn must differ from usn.")
    with db_conn() as conn:
        conn.autocommit = False
        conn.start_transaction()
        cur = conn.cursor(dictionary=True)
        if not _student_exists(cur, usn):
            conn.rollback(); cur.close()
            raise HTTPException(status_code=404, detail="Student not found.")
        try:
            cur.execute(
                "INSERT INTO student_identity_links "
                "(usn, related_usn, relation_type, note, created_by) "
                "VALUES (%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE note=VALUES(note), created_by=VALUES(created_by)",
                (usn, related, relation, req.note, current_user.get("username")))
            conn.commit()
        except Exception as e:
            conn.rollback(); cur.close()
            write_audit_log("identity_link_create", current_user.get("username"),
                            current_user.get("role"), "student_identity_links", usn,
                            success=False, error_info=str(e)[:500])
            raise HTTPException(status_code=400, detail="Could not create identity link.")
        cur.close()
    write_audit_log("identity_link_create", current_user.get("username"),
                    current_user.get("role"), "student_identity_links", usn,
                    f"{usn} <-> {related} ({relation}) — record only, no merge")
    return {"usn": usn, "related_usn": related, "relation_type": relation,
            "merged": False, "note": req.note}


@router.delete("/students/{usn}/identity-links/{link_id}")
def delete_identity_link(
    usn: str, link_id: int,
    current_user: dict = Depends(require_roles("Admin")),
):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("DELETE FROM student_identity_links WHERE id=%s AND (usn=%s OR related_usn=%s)",
                    (link_id, usn, usn))
        removed = cur.rowcount
        conn.commit()
        cur.close()
    if not removed:
        raise HTTPException(status_code=404, detail="Identity link not found.")
    write_audit_log("identity_link_delete", current_user.get("username"),
                    current_user.get("role"), "student_identity_links", usn,
                    f"removed link #{link_id}")
    return {"usn": usn, "link_id": link_id, "deleted": True}


# ── §7 clear a backlog on a VERIFIED pass (never rewrites marks/SGPA/CGPA) ─────
@router.post("/students/{usn}/backlogs/{backlog_id}/clear")
def clear_backlog_verified_pass(
    usn: str, backlog_id: int, req: VerifiedPassClearModel,
    current_user: dict = Depends(require_roles("Admin")),
):
    """
    Mark ONE backlog subject cleared after an authorized Admin confirms an
    official VTU pass. This flips only student_backlogs.cleared and APPENDS a
    lifecycle event for the audit trail. It never edits marks, SGPA or CGPA and
    never deletes the attempt — recomputation of scheme grade remains a
    review-flagged, human decision (conservative policy).
    """
    with db_conn() as conn:
        conn.autocommit = False
        conn.start_transaction()
        cur = conn.cursor(dictionary=True)
        if not _student_exists(cur, usn):
            conn.rollback(); cur.close()
            raise HTTPException(status_code=404, detail="Student not found.")
        cur.execute("SELECT * FROM student_backlogs WHERE id=%s AND usn=%s",
                    (backlog_id, usn))
        bl = cur.fetchone()
        if not bl:
            conn.rollback(); cur.close()
            raise HTTPException(status_code=404, detail="Backlog not found for this student.")
        token = create_undo_snapshot("UPDATE", [usn], current_user.get("username", ""),
                                     f"clear backlog #{backlog_id} (verified pass)", conn=conn)
        from_status = _current_status(cur, usn)
        fields = {"reason": f"Backlog cleared on verified pass: {bl.get('subject')}",
                  "document_ref": req.result_ref, "effective_date": req.cleared_date,
                  "remarks": req.remarks}
        try:
            cur.execute("UPDATE student_backlogs SET cleared=1 WHERE id=%s", (backlog_id,))
            _append_event(cur, usn, LC.EV_CORRECTION, from_status, from_status, fields, current_user)
            finalize_undo_snapshot(token, [usn], conn)
            conn.commit()
        except Exception as e:
            conn.rollback(); cur.close()
            write_audit_log("backlog_clear", current_user.get("username"),
                            current_user.get("role"), "student_backlogs", usn,
                            success=False, error_info=str(e)[:500])
            raise HTTPException(status_code=400, detail="Could not clear backlog.")
        cur.close()
    write_audit_log("backlog_clear", current_user.get("username"),
                    current_user.get("role"), "student_backlogs", usn,
                    f"cleared backlog '{bl.get('subject')}' (result_ref={req.result_ref})")
    return {"usn": usn, "backlog_id": backlog_id, "subject": bl.get("subject"),
            "cleared": True, "grade_recomputed": False,
            "note": "Marks/SGPA/CGPA unchanged; scheme recompute is review-flagged.",
            "undo_token": token}
