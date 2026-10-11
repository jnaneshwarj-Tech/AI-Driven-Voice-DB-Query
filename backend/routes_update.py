"""
routes_update.py — Controlled, audited, undoable field + fee editing.

Purpose (spec: "fill any blank field", "update fee status", "every update
possibility"):
  * Any single student column (or a whole edit form at once) can be filled /
    corrected here, using the SAME value-validation the natural-language update
    pipeline already trusts, so a manual edit and an NL edit behave identically.
  * Fee status (VTU/PD/IDP year-wise, plus tuition) is Admin-only, verified
    against the canonical fee status the reports use, and stored exactly where
    the spreadsheet importer stores it (student_fees).
  * Every mutation is wrapped in a global undo snapshot (students + marks +
    fees), so any update — including a lifecycle/fee change — is reversible via
    POST /api/undo/restore/{token} within the normal undo window.

These endpoints never touch identity columns (usn), timestamps, or the
lifecycle-managed `lifecycle_status` / legacy `status` columns — those go
through the dedicated lifecycle endpoints so their event history stays correct.
"""
from typing import Optional, Any

import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from database import db_conn, write_audit_log
from auth import get_current_user, require_roles
from canonical_fields import map_column, normalize_header
from routes_query import (
    _match_student,
    _load_table_columns,
    _validate_value,
    _normalize_usn,
)
from routes_undo import create_undo_snapshot, finalize_undo_snapshot

router = APIRouter(prefix="/api/update", tags=["Field & Fee Updates"])

# Columns that must never be edited through the generic field editor.
#  * identifiers / audit columns — immutable by design
#  * lifecycle-managed columns — the lifecycle endpoints own these so every
#    change appends a proper event instead of a silent cache overwrite.
_NEVER_EDITABLE = {
    "usn", "id", "student_id", "created_at", "updated_at",
    "lifecycle_status", "status",
}

# Canonical fee_type -> allowed year values (mirrors routes_files._FEE_COLS).
_FEE_YEAR_RULES = {
    "VTU": {1, 2, 3, 4},
    "PD": {1, 2, 3, 4},
    "IDP": {1, 2, 3, 4},
    "TUITION_PAID": {0},
    "TUITION_REMAINING": {0},
}


def _student_exists(cur, usn: str) -> Optional[dict]:
    cur.execute("SELECT * FROM students WHERE usn=%s", (usn,))
    return cur.fetchone()


def _resolve_usn(raw: str) -> str:
    """Return the canonical stored USN for a (possibly messy) identifier."""
    match = _match_student(raw)
    if match.get("ambiguous"):
        picks = match["ambiguous"]
        raise HTTPException(409, {
            "error": "Multiple students match. Please provide the exact USN.",
            "suggestions": [p.get("usn") for p in picks],
        })
    return match["student"]["usn"]


def _editable_field_map(conn) -> dict:
    """Column -> friendly label for every editable students column."""
    cols = _load_table_columns(conn, "students")
    editable = {}
    for col in cols:
        if col.lower() in _NEVER_EDITABLE:
            continue
        editable[col] = col.replace("_", " ").title()
    return editable


def _resolve_column(conn, field_text: str, students_cols: dict) -> str:
    """Map a user-supplied field (friendly label or raw column) to a real,
    editable students column. Raises 400 when it can't or must not be edited."""
    candidate = (field_text or "").strip()
    if not candidate:
        raise HTTPException(400, "Field name is required.")

    # Direct column hit (case-insensitive) first — the edit form sends real
    # column names; NL/labels fall through to the synonym mapper.
    lower_map = {c.lower(): c for c in students_cols}
    col = lower_map.get(candidate.lower())
    if col is None:
        canonical, _mapping_type, _conf, _ = map_column(candidate)
        col = lower_map.get((canonical or "").lower())
    if col is None:
        norm = normalize_header(candidate)
        col = lower_map.get(norm)
    if col is None:
        raise HTTPException(400, f"Field '{field_text}' is not available for editing.")
    if col.lower() in _NEVER_EDITABLE:
        raise HTTPException(400, f"Field '{field_text}' cannot be edited here.")
    return col


class FieldUpdateRequest(BaseModel):
    usn: str
    field: str
    value: Any
    confirm: bool = False


class BulkFieldUpdateRequest(BaseModel):
    usn: str
    fields: dict = Field(default_factory=dict)
    confirm: bool = False


class FeeRow(BaseModel):
    fee_type: str
    year: Optional[int] = None
    status: Optional[str] = None
    amount_paid: Optional[str] = None
    remaining_amount: Optional[str] = None


class FeeUpdateRequest(BaseModel):
    usn: str
    fees: list[FeeRow]
    confirm: bool = False


def _clean_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


# `students.dynamic_data` is a second, older copy of the same answers, written
# once by the spreadsheet import. report_service renders it as
# "dynamic_fee_fields" next to the authoritative fee rows, so a write that only
# updates student_fees / a students column leaves one report stating both the
# new value and the old one. These keys are kept in step with every write.
_DYNAMIC_TEXT_KEYS = {"village": "village_name_town"}


def _dynamic_fee_key(fee_type: str, year: int) -> Optional[str]:
    if fee_type in ("VTU", "PD", "IDP"):
        return f"fee_{fee_type.lower()}_{year}"
    if fee_type == "TUITION_PAID":
        return "fee_tuition_paid"
    if fee_type == "TUITION_REMAINING":
        return "fee_tuition_remaining"
    return None


def _sync_dynamic_data_keys(cur, usn: str, wanted: dict) -> None:
    """Mirror written values into the legacy dynamic_data JSON. Keys the import
    never produced are deliberately not invented — a missing key simply renders
    nothing, whereas a new one would fabricate a column in every report."""
    if not wanted:
        return
    cur.execute("SELECT dynamic_data FROM students WHERE usn=%s", (usn,))
    raw = (cur.fetchone() or {}).get("dynamic_data")
    if not raw:
        return
    try:
        blob = json.loads(raw)
    except (ValueError, TypeError):
        return
    if not isinstance(blob, dict):
        return
    changed = False
    for key, value in wanted.items():
        if key in blob and str(blob[key]) != str(value):
            blob[key] = value
            changed = True
    if changed:
        cur.execute("UPDATE students SET dynamic_data=%s WHERE usn=%s",
                    (json.dumps(blob), usn))


@router.get("/fields/{usn}")
def get_editable_fields(usn: str, current_user: dict = Depends(get_current_user)):
    """Current values + editable schema for one student (drives the Edit form)."""
    canonical = _resolve_usn(usn)
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        student = _student_exists(cur, canonical)
        schema = _editable_field_map(conn)
        cur.close()
    if not student:
        raise HTTPException(404, "Student not found.")
    return {
        "usn": canonical,
        "name": student.get("name"),
        "editable_fields": [
            {"column": col, "label": label, "value": student.get(col),
             "blank": _clean_value(student.get(col)) == ""}
            for col, label in schema.items()
        ],
    }


def _apply_field_updates(usn: str, updates: list[tuple[str, Any]],
                         actor: dict, description: str) -> dict:
    """Validate + apply (column, value) pairs to a student inside one
    transaction, snapshotting for undo and recording field history."""
    with db_conn() as conn:
        conn.autocommit = False
        conn.start_transaction()
        cur = conn.cursor(dictionary=True)
        before = _student_exists(cur, usn)
        if not before:
            conn.rollback(); cur.close()
            raise HTTPException(404, "Student not found.")

        students_cols = _load_table_columns(conn, "students")
        resolved = []
        for field_text, raw_value in updates:
            col = _resolve_column(conn, field_text, students_cols)
            value = _validate_value(col, raw_value, "students",
                                    students_cols.get(col), field_text)
            resolved.append((col, value))

        token = create_undo_snapshot("UPDATE", [usn], actor.get("username", ""),
                                     description, conn=conn)

        changed = []
        for col, value in resolved:
            old = before.get(col)
            if str(old) == str(value) and not (old is None and value is None):
                continue
            cur.execute(f"UPDATE students SET `{col}`=%s WHERE usn=%s", (value, usn))
            cur.execute(
                "INSERT INTO student_history (usn, field_name, old_value, new_value, updated_by) "
                "VALUES (%s,%s,%s,%s,%s)",
                (usn, col, None if old is None else str(old), str(value),
                 actor.get("username", "")),
            )
            changed.append({"column": col, "old_value": old, "new_value": value})

        _sync_dynamic_data_keys(cur, usn, {
            _DYNAMIC_TEXT_KEYS[c["column"]]: c["new_value"]
            for c in changed if c["column"] in _DYNAMIC_TEXT_KEYS
        })

        try:
            cur.execute("DELETE FROM query_cache")
        except Exception:
            pass

        finalize_undo_snapshot(token, [usn], conn)
        conn.commit()
        cur.close()
    return {"undo_token": token, "changed": changed}


@router.post("/field")
def update_field(req: FieldUpdateRequest,
                 current_user: dict = Depends(require_roles("Staff", "Admin"))):
    if not req.confirm:
        raise HTTPException(428, "Update requires explicit confirmation.")
    usn = _resolve_usn(req.usn)
    value = _clean_value(req.value)
    if value == "":
        raise HTTPException(400, "A value is required to fill this field.")
    result = _apply_field_updates(
        usn, [(req.field, value)], current_user, f"field edit → {req.field}")
    write_audit_log("field_update", current_user.get("username"),
                    current_user.get("role"), "students", usn,
                    f"Updated {len(result['changed'])} field(s) via edit form")
    return {"usn": usn, "undo_token": result["undo_token"],
            "changed": result["changed"],
            "message": "Field updated successfully." if result["changed"]
                       else "No change — the value already matched."}


@router.post("/bulk")
def update_bulk(req: BulkFieldUpdateRequest,
                current_user: dict = Depends(require_roles("Staff", "Admin"))):
    if not req.confirm:
        raise HTTPException(428, "Update requires explicit confirmation.")
    if not req.fields:
        raise HTTPException(400, "No fields supplied.")
    usn = _resolve_usn(req.usn)
    updates = []
    for field_text, raw_value in req.fields.items():
        cleaned = _clean_value(raw_value)
        if cleaned == "":
            continue  # an edit form sends every box; blank boxes are not writes
        updates.append((field_text, cleaned))
    if not updates:
        raise HTTPException(400, "Nothing to update — all fields were blank.")
    result = _apply_field_updates(usn, updates, current_user,
                                  f"bulk field edit → {len(updates)} field(s)")
    write_audit_log("field_update_bulk", current_user.get("username"),
                    current_user.get("role"), "students", usn,
                    f"Updated {len(result['changed'])} field(s) via edit form")
    return {"usn": usn, "undo_token": result["undo_token"],
            "changed": result["changed"],
            "message": "Student record updated successfully." if result["changed"]
                       else "No change — the values already matched."}


def _canonical_fee_type(raw: str) -> str:
    ft = (raw or "").strip().upper().replace(" ", "_").replace("-", "_")
    aliases = {
        "TUITION_PAID": "TUITION_PAID", "TUITION_REMAINING": "TUITION_REMAINING",
        "TUITION": "TUITION_REMAINING", "VTU": "VTU", "PD": "PD", "IDP": "IDP",
    }
    if ft not in aliases:
        raise HTTPException(400, f"Unknown fee type '{raw}'.")
    return aliases[ft]


@router.get("/fees/{usn}")
def get_fees(usn: str, current_user: dict = Depends(get_current_user)):
    canonical = _resolve_usn(usn)
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT fee_type, year, status, amount_paid, remaining_amount "
            "FROM student_fees WHERE usn=%s ORDER BY fee_type, year", (canonical,))
        rows = cur.fetchall()
        cur.close()
    return {"usn": canonical, "fees": rows}


@router.post("/fees")
def update_fees(req: FeeUpdateRequest,
                current_user: dict = Depends(require_roles("Admin"))):
    """Admin-only fee status/amount updates, verified against the canonical
    status the reports use. Undoable via /api/undo/restore/{token}."""
    if not req.confirm:
        raise HTTPException(428, "Fee update requires explicit confirmation.")
    if not req.fees:
        raise HTTPException(400, "No fee rows supplied.")

    import report_service
    canonical = _resolve_usn(req.usn)

    prepared = []
    for row in req.fees:
        fee_type = _canonical_fee_type(row.fee_type)
        year = row.year
        if year is None:
            year = 0 if fee_type.startswith("TUITION") else None
        if year is None:
            raise HTTPException(400, f"{fee_type} requires a year (1-4).")
        if int(year) not in _FEE_YEAR_RULES[fee_type]:
            raise HTTPException(400,
                               f"{fee_type} is not valid for year {year}.")
        status = _clean_value(row.status)
        canon, label = report_service.normalize_fee_status(status) if status else ("unknown", "Not Recorded")
        if status and canon == "unknown":
            raise HTTPException(400,
                                f"Could not verify fee status '{status}'.")
        prepared.append({
            "fee_type": fee_type, "year": int(year),
            "status": status or None,
            "amount_paid": _clean_value(row.amount_paid) or None,
            "remaining_amount": _clean_value(row.remaining_amount) or None,
            "canonical": canon, "label": label,
        })

    with db_conn() as conn:
        conn.autocommit = False
        conn.start_transaction()
        cur = conn.cursor(dictionary=True)
        if not _student_exists(cur, canonical):
            conn.rollback(); cur.close()
            raise HTTPException(404, "Student not found.")

        token = create_undo_snapshot("UPDATE", [canonical],
                                     current_user.get("username", ""),
                                     f"fee update → {len(prepared)} row(s)", conn=conn)
        cur.execute("SELECT fee_type, year, status, amount_paid, remaining_amount "
                    "FROM student_fees WHERE usn=%s", (canonical,))
        before = {(r["fee_type"], r["year"]): r for r in cur.fetchall()}

        results = []
        for p in prepared:
            key = (p["fee_type"], p["year"])
            cur.execute(
                """INSERT INTO student_fees (usn, fee_type, year, status, amount_paid, remaining_amount)
                   VALUES (%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE
                       status=COALESCE(VALUES(status), status),
                       amount_paid=COALESCE(VALUES(amount_paid), amount_paid),
                       remaining_amount=COALESCE(VALUES(remaining_amount), remaining_amount),
                       updated_at=NOW()""",
                (canonical, p["fee_type"], p["year"], p["status"],
                 p["amount_paid"], p["remaining_amount"]))
            results.append({
                "fee_type": p["fee_type"], "year": p["year"],
                "old_status": (before.get(key) or {}).get("status"),
                "new_status": p["status"], "verified_label": p["label"],
            })

        wanted = {}
        for p in prepared:
            key = _dynamic_fee_key(p["fee_type"], p["year"])
            value = ((p["amount_paid"] or p["remaining_amount"])
                     if p["fee_type"].startswith("TUITION") else p["status"])
            if key and value:
                wanted[key] = value
        _sync_dynamic_data_keys(cur, canonical, wanted)

        try:
            cur.execute("DELETE FROM query_cache")
        except Exception:
            pass
        finalize_undo_snapshot(token, [canonical], conn)
        conn.commit()
        cur.close()

    write_audit_log("fee_update", current_user.get("username"),                    current_user.get("role"), "student_fees", canonical,
                    f"Updated {len(prepared)} fee row(s)")
    return {"usn": canonical, "undo_token": token, "results": results,
            "message": "Fees updated successfully."}


# ── Natural-language fee update (main search bar) ─────────────────────────────
# Conservative: only fires for an explicit update imperative + a recognisable
# fee type + a recognisable target status, so reads ("students whose fees are
# pending") are never captured.
_FEE_COMMAND_RE = re.compile(
    r'\b(?:update|mark|set|change|record)\b.*\b(?:fee|fees)\b', re.I)
_FEE_TYPE_RE = re.compile(r'\b(vtu|pd|idp|tuition)\b', re.I)
_TUITION_PAID_RE = re.compile(r'tuition\s*(?:fee\s*)?(?:paid|amount\s*paid)\b', re.I)
_TUITION_REMAINING_RE = re.compile(r'tuition\s*(?:fee\s*)?(?:remaining|balance|due|pending)\b', re.I)
_FEE_YEAR_RE = re.compile(r'(?:year|yr|std|class)\s*(?:[:=\-]?\s*)?([1-4])\b'
                          r'|\b([1-4])(?:st|nd|rd|th)\s*(?:year|sem)', re.I)
_STATUS_TO_RE = re.compile(r'\b(?:to|as|status\s*(?:[:=\-]?)?)\s+'
                           r'(paid|not\s+paid|partially\s+paid|unpaid|pending|'
                           r'not\s+applicable|na|yes|no|due|balance)\b', re.I)


def _extract_usn_token(text: str) -> Optional[str]:
    """Pull a USN-shaped token (starts with a digit, >=2 letters, has a digit) out
    of free text. Generic enough for synthetic test USNs and real college codes;
    a wrong guess simply fails the existence check and writes nothing."""
    for tok in re.findall(r'\b\d[A-Za-z0-9]{5,}\b', text or ""):
        if sum(c.isalpha() for c in tok) >= 2 and any(c.isdigit() for c in tok):
            return tok
    return None


def is_fee_command(nq: str) -> bool:
    """True when the text clearly asks to change a fee (imperative + 'fee' +
    a recognisable fee type). Narrower than a general 'update' so genuine
    students-column edits aren't captured, but broad enough to claim fee phrasing
    that merely omitted a year (so it gets a friendly clarify instead of leaking
    into the students-column update path)."""
    text = (nq or "").strip()
    return bool(_FEE_COMMAND_RE.search(text) and _FEE_TYPE_RE.search(text))


def parse_fee_command(nq: str) -> Optional[dict]:
    """Return {target_text, usn, fee_type, year, status} or None."""
    text = (nq or "").strip()
    if not text or not _FEE_COMMAND_RE.search(text):
        return None
    type_m = _FEE_TYPE_RE.search(text)
    if not type_m:
        return None
    raw_type = type_m.group(1).upper()
    if raw_type == "TUITION":
        if _TUITION_PAID_RE.search(text):
            fee_type = "TUITION_PAID"
        else:
            fee_type = "TUITION_REMAINING"
        year = 0
    else:
        fee_type = raw_type  # VTU / PD / IDP
        ym = _FEE_YEAR_RE.search(text)
        year = None
        if ym:
            year = int(ym.group(1) or ym.group(2))
        if year is None:
            return None  # non-tuition fee needs a year; ask rather than guess

    sm = _STATUS_TO_RE.search(text)
    if not sm:
        return None
    status = re.sub(r'\s+', ' ', sm.group(1)).strip().title()

    usn_m = _extract_usn_token(text)
    return {
        "usn": usn_m,
        "fee_type": fee_type, "year": year, "status": status,
    }


def prepare_fee_preview(nq: str, username: str) -> dict:
    """Resolve a natural-language fee command into a confirm payload. Never
    writes; the caller commits via POST /api/update/fees (Admin only)."""
    parsed = parse_fee_command(nq)
    if not parsed:
        return {"action_required": "clarify",
                "message": "I couldn't identify the fee to update. Try: "
                           "'update VTU fee of 4HG23CS032 year 1 to Paid'."}
    try:
        canonical = _resolve_usn(parsed["usn"] or nq)
    except HTTPException as e:
        if isinstance(e.detail, dict):
            return {"action_required": "select_student",
                    "suggestions": e.detail.get("suggestions", []),
                    "message": "Multiple students match. Select the USN."}
        if e.status_code == 404:
            return {"action_required": "no_record",
                    "message": "No student matched that reference. "
                               "Provide the USN."}
        raise
    import report_service
    canon, label = report_service.normalize_fee_status(parsed["status"])
    if canon == "unknown":
        return {"action_required": "clarify",
                "message": f"I couldn't verify the fee status '{parsed['status']}'."}
    payload = {
        "usn": canonical,
        "fees": [{
            "fee_type": parsed["fee_type"], "year": parsed["year"],
            "status": parsed["status"],
        }],
    }
    return {
        "action_required": "confirm",
        "action_type": "FEE_UPDATE",
        "confirm_endpoint": "/api/update/fees",
        "payload": payload,
        "role_restricted": "Admin",
        "message": f"Confirm: set {parsed['fee_type']}"
                   f"{' year ' + str(parsed['year']) if parsed['year'] else ''}"
                   f" fee of {canonical} to '{label}'?",
    }


@router.post("/fees/preview")
def fees_preview(req: dict,
                 current_user: dict = Depends(require_roles("Staff", "Admin"))):
    """Preview a natural-language fee command (Staff may preview; Admin commits)."""
    return prepare_fee_preview(str(req.get("natural_query") or ""),
                               current_user.get("username", ""))

