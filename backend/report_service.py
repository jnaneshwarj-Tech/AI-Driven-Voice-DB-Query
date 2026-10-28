"""
report_service.py — Single source of truth for student reports/exports.

Every export (CSV, Excel, PDF, print) is built from the SAME model produced
here, so all formats show identical fields. Values are read from the CURRENT
authorized MySQL records at generation time (not a stale frontend snapshot),
fulfilling spec sections 6, 7 and 8.

The model covers, per student:
  - personal details (students table + dynamic fee columns from dynamic_data)
  - academic performance (marks, with cumulative CGPA)
  - fee details (student_fees, with normalized payment status)
  - backlog details (student_backlogs)

Sensitive identity fields are masked consistently by role so unauthorized
users cannot export restricted personal data.
"""
import json
import re
from datetime import datetime

from database import db_conn


INSTITUTION = {
    "university": "VISVESVARAYA TECHNOLOGICAL UNIVERSITY, BELAGAVI-590018",
    "college": "GOVERNMENT ENGINEERING COLLEGE MOSALEHOSAHALLI, HASSAN",
    "department": "DEPARTMENT OF COMPUTER SCIENCE AND ENGINEERING",
}

# Ordered personal fields for the profile/report block.
PERSONAL_FIELDS = [
    ("usn", "USN"), ("name", "Name"), ("dob", "Date of Birth"),
    ("gender", "Gender"), ("blood_group", "Blood Group"),
    ("father_name", "Father's Name"), ("mother_name", "Mother's Name"),
    ("phone", "Phone"), ("email", "Email"), ("aadhar_no", "Aadhaar No"),
    ("address", "Address"), ("permanent_address", "Permanent Address"),
    ("current_address", "Current Address"),
    ("village", "Village"), ("taluk", "Taluk"), ("district", "District"),
    ("state", "State"), ("area_type", "Rural/Urban"),
    ("pin_code", "PIN Code"), ("religion", "Religion"), ("caste", "Caste"),
    ("category", "Category"), ("year_of_joining", "Year of Joining"),
    ("branch", "Branch"), ("admission_year", "Admission Year"),
    ("student_type", "Student Type"), ("hk_status", "HK/Non-HK"),
    ("quota", "Quota"), ("distance_from_college", "Distance from College"),
]

# Personal columns that are privacy-restricted when the requester is not Admin.
_SENSITIVE_FIELDS = {
    "aadhar_no", "phone", "email", "emergency_contact_number", "parents_phone",
}

# Uploaded headings and intent-resolver aliases are free-form, so the column list
# alone is not enough — a number is a number whatever the sheet called it.
_CONTACT_KEY_RE = re.compile(
    r"phone|mobile|contact|mahati|whatsapp|aadhar|aadar|aadhaar", re.I)
_IDENTITY_KEY_RE = re.compile(r"aadhar|aadar|aadhaar", re.I)

# dynamic_data JSON keys that represent fee information (workbook-imported).
_FEE_KEY_HINTS = ("fee", "fees", "tution", "tuition", "amount", "balance",
                  "remaining", "paid", "challan")


def now_str() -> str:
    return datetime.now().strftime("%d %B %Y, %I:%M %p")


def _norm_usn(raw) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(raw or "")).upper()


def _as_str(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_fee_status(raw: str) -> tuple[str, str]:
    """Map free-text fee status to (canonical, human_label).

    Blank values stay 'unknown' — a blank status must never be treated as
    unpaid (spec section 7). Amounts are never inferred from status.
    """
    text = _as_str(raw).lower()
    if text in ("", "none", "null", "n a", "na"):
        return "unknown", "Not Recorded"
    # Explicitly-not-applicable first (before the generic 'no' rule).
    if "not applicable" in text or "not required" in text or text in ("n/a", "na"):
        return "na", "Not Applicable"
    # 'No balance / no remaining / no dues' means settled (paid).
    if re.search(r"no\s+(balance|remaining|due|payable)", text) or "no remainder" in text:
        return "paid", "Paid"
    if "partial" in text:
        return "partial", "Partially Paid"
    if re.search(r"\bnot\b[^.]*\bpaid\b", text) or "unpaid" in text or "not paid" in text \
            or text in ("no", "pending", "due") or "balance" in text or "remaining" in text:
        return "unpaid", "Not Paid"
    if "paid" in text or text in ("yes", "done", "clear", "cleared") or "fully" in text \
            or "complet" in text:
        return "paid", "Paid"
    return "unknown", _as_str(raw)


def _mask(value: str, keep: int) -> str:
    value = _as_str(value)
    if not value:
        return value
    if len(value) <= keep:
        return "*" * len(value)
    return "*" * (len(value) - keep) + value[-keep:]


def _sensitive_keys(row: dict) -> set:
    """Every key of this row that carries contact or identity data."""
    keys = set(_SENSITIVE_FIELDS).intersection(row)
    keys |= {k for k in row if _CONTACT_KEY_RE.search(str(k))}
    return keys


def _identity_keys(keys: set) -> set:
    return {k for k in keys if _IDENTITY_KEY_RE.search(str(k))}


def mask_for_role(row: dict, role: str, edit_context: bool = False) -> dict:
    """Role policy for personal data leaving the server.

    Admin is the only role that sees these values in full, so a screen, an answer
    and an exported file can never disagree about the same student.

    `edit_context` is the one deliberate exception: the clerk who has to correct a
    mistyped phone number must be able to read it, so Staff editing a contact
    field sees the contact numbers — while the Aadhaar, which no one at the
    counter has any reason to retype, stays hidden from every non-Admin.
    """
    role_norm = str(role or "").strip().lower()
    if role_norm == "admin":
        return dict(row)
    masked = dict(row)
    keys = _sensitive_keys(masked)
    if edit_context and role_norm == "staff":
        # Keep only the identity numbers masked: the mask set is the set of keys
        # to hide, so subtracting the Aadhaar here would have done the opposite of
        # what the clerk exception intends.
        keys = _identity_keys(keys)
    for field in keys:
        if _as_str(masked[field]):
            if field == "email":
                local, _, domain = str(masked[field]).partition("@")
                masked[field] = (_mask(local, 1) + "@" + domain
                                 if domain else _mask(masked[field], 2))
            else:
                masked[field] = _mask(masked[field], 4)
    return masked


def mask_rows_for_role(rows, role: str, edit_context: bool = False):
    """`mask_for_role` over a list of result rows (non-dicts pass through)."""
    if isinstance(rows, dict):
        return mask_for_role(rows, role, edit_context)
    return [mask_for_role(r, role, edit_context) if isinstance(r, dict) else r
            for r in (rows or [])]


def is_sensitive_field(field: str) -> bool:
    return bool(_CONTACT_KEY_RE.search(str(field))
                or str(field) in _SENSITIVE_FIELDS)


def mask_value_for_role(field: str, value, role: str):
    """One field's value under the same policy that covers whole rows, so a
    change-history entry cannot show more of a phone number than the
    profile screen does."""
    if not is_sensitive_field(field):
        return value
    return mask_for_role({field: value}, role).get(field, value)


def _is_fee_key(key: str) -> bool:
    lowered = key.lower()
    return any(hint in lowered for hint in _FEE_KEY_HINTS)


def _friendly_fee_label(key: str) -> str:
    clean = re.sub(r"[_\-]+", " ", key).strip()
    clean = re.sub(r"\b(fee|fees|paid|remaining|amount|balance)\b", lambda m: m.group(0).title(), clean, flags=re.I)
    return clean.title()


def _norm_sql_expr(col: str) -> str:
    return f"UPPER(REPLACE(REPLACE(REPLACE(COALESCE({col},''),' ',''),'-',''),'.',''))"


def build_report_model(data: list[dict], user: dict) -> dict:
    """
    Assemble the shared report model.

    `data` is the displayed result rows (used to learn which students and which
    columns the user is looking at). Personal, academic, fee and backlog values
    are re-read from MySQL here so exports never present stale data.
    """
    role = user.get("role", "Staff")
    username = user.get("username", "Unknown")

    # Discover the students referenced by the current result.
    result_usns: list[str] = []
    seen: set[str] = set()
    for row in data:
        norm = _norm_usn(row.get("usn"))
        if norm and norm not in seen:
            seen.add(norm)
            result_usns.append(norm)

    students: dict[str, dict] = {}
    academic_map: dict[str, list] = {}
    fees_map: dict[str, list] = {}
    backlogs_map: dict[str, list] = {}
    lifecycle_map: dict[str, dict] = {}

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        placeholders = ",".join(["%s"] * len(result_usns)) if result_usns else ""
        if result_usns:
            cur.execute(
                f"SELECT * FROM students WHERE {_norm_sql_expr('usn')} IN ({placeholders})",
                list(result_usns),
            )
            for row in cur.fetchall():
                students[_norm_usn(row.get("usn"))] = row

            cur.execute(
                "SELECT usn, semester, sgpa, "
                "ROUND(AVG(sgpa) OVER (PARTITION BY usn ORDER BY semester "
                "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS cgpa "
                f"FROM marks WHERE {_norm_sql_expr('usn')} IN ({placeholders}) "
                "AND sgpa IS NOT NULL ORDER BY usn, semester ASC",
                list(result_usns),
            )
            for row in cur.fetchall():
                academic_map.setdefault(_norm_usn(row["usn"]), []).append({
                    "semester": row["semester"],
                    "sgpa": _num(row["sgpa"]),
                    "cgpa": _num(row["cgpa"]),
                })

            cur.execute(
                f"SELECT usn, fee_type, year, status, amount_paid, remaining_amount, updated_at "
                f"FROM student_fees WHERE {_norm_sql_expr('usn')} IN ({placeholders}) "
                "ORDER BY usn, fee_type, year",
                list(result_usns),
            )
            for row in cur.fetchall():
                canonical, label = normalize_fee_status(row.get("status"))
                fees_map.setdefault(_norm_usn(row["usn"]), []).append({
                    "fee_type": _as_str(row.get("fee_type")),
                    "year": row.get("year"),
                    "status_raw": _as_str(row.get("status")),
                    "status": canonical,
                    "status_label": label,
                    "amount_paid": _clean_amount(row.get("amount_paid")),
                    "remaining_amount": _clean_amount(row.get("remaining_amount")),
                })

            cur.execute(
                f"SELECT usn, subject, semester, year, cleared FROM student_backlogs "
                f"WHERE {_norm_sql_expr('usn')} IN ({placeholders}) AND cleared=0 "
                "ORDER BY usn, semester, subject",
                list(result_usns),
            )
            for row in cur.fetchall():
                backlogs_map.setdefault(_norm_usn(row["usn"]), []).append({
                    "subject": _as_str(row.get("subject")),
                    "semester": row.get("semester"),
                    "year": _as_str(row.get("year")),
                    "cleared": bool(row.get("cleared")),
                })

            # Lifecycle snapshot (current status) + audited status history, only
            # when the tables exist (they are created idempotently at startup).
            try:
                cur.execute(
                    f"SELECT usn, current_status, effective_date, last_enrolled_semester, "
                    f"last_enrolled_academic_year, scheme, reason, reason_category, document_ref, updated_by "
                    f"FROM student_lifecycle_status WHERE {_norm_sql_expr('usn')} IN ({placeholders})",
                    list(result_usns),
                )
                for row in cur.fetchall():
                    lifecycle_map[_norm_usn(row["usn"])] = {
                        "current_status": _as_str(row.get("current_status")),
                        "effective_date": _as_str(row.get("effective_date")),
                        "last_enrolled_semester": row.get("last_enrolled_semester"),
                        "last_enrolled_academic_year": _as_str(row.get("last_enrolled_academic_year")),
                        "scheme": _as_str(row.get("scheme")),
                        "reason": _as_str(row.get("reason")),
                        "reason_category": _as_str(row.get("reason_category")),
                        "document_ref": _as_str(row.get("document_ref")),
                        "updated_by": _as_str(row.get("updated_by")),
                        "history": [],
                    }
                cur.execute(
                    f"SELECT usn, event_type, from_status, to_status, effective_date, "
                    f"requested_semester, approved_semester, rejoin_date, scheme, reason, "
                    f"approval_ref, remarks, actor_username, created_at "
                    f"FROM student_lifecycle_events WHERE {_norm_sql_expr('usn')} IN ({placeholders}) "
                    f"ORDER BY created_at ASC, id ASC",
                    list(result_usns),
                )
                for row in cur.fetchall():
                    entry = lifecycle_map.setdefault(_norm_usn(row["usn"]), {"history": []})
                    entry.setdefault("history", []).append(_serialize(row))
            except Exception:
                # Lifecycle tables may be absent in a fresh DB — reports stay intact.
                pass
        cur.close()

    # Build the per-student report entries in result order.
    student_reports = []
    for norm in result_usns:
        srow = students.get(norm)
        if not srow:
            # Student not in DB (deleted) — fall back to whatever the result row has.
            srow = {k: v for k, v in next((r for r in data if _norm_usn(r.get("usn")) == norm), {}).items()}
        personal = _serialize(mask_for_role(srow, role))
        dynamic_fees = _dynamic_fee_fields(srow.get("dynamic_data"))
        lifecycle = lifecycle_map.get(norm) or {
            "current_status": _as_str(srow.get("lifecycle_status")) or "Active",
            "effective_date": "", "last_enrolled_semester": None,
            "last_enrolled_academic_year": "", "scheme": "", "reason": "",
            "reason_category": "", "document_ref": "", "updated_by": "", "history": [],
        }
        student_reports.append({
            "usn": _as_str(srow.get("usn")) or norm,
            "name": _as_str(srow.get("name")),
            "personal": personal,
            "academic": academic_map.get(norm, []),
            "fees": fees_map.get(norm, []),
            "backlogs": [] if _text_is_no_backlog(srow.get("backlogs"))
                        else backlogs_map.get(norm, []),
            "lifecycle": lifecycle,
            "dynamic_fee_fields": dynamic_fees,
        })

    # Refresh the displayed result table from current DB where the same column
    # exists on `students`, so exported list rows match current records.
    table_headers = _result_headers(data)
    refreshed_rows = []
    for row in data:
        norm = _norm_usn(row.get("usn"))
        merged = dict(row)
        srow = students.get(norm)
        if srow:
            masked = mask_for_role(srow, role)
            for header in table_headers:
                if header in masked and masked[header] is not None:
                    merged[header] = masked[header]
        # `data` arrives from the caller, so overwriting the known columns is not
        # enough: a sheet can name a phone column anything, and a row whose USN is
        # not in the table would otherwise be exported verbatim and unmasked.
        refreshed_rows.append(_serialize(mask_for_role(merged, role)))

    return {
        "institution": INSTITUTION,
        "generated_by": {"role": role, "username": username, "timestamp": now_str()},
        "is_single_student": len(student_reports) == 1,
        "students": student_reports,
        "table_headers": table_headers,
        "table_rows": refreshed_rows,
        "refreshed_from_db": bool(students),
    }


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_amount(value):
    text = _as_str(value)
    if text.lower() in ("", "none", "null", "na", "n/a"):
        return ""
    return text


_NO_BACKLOG_TEXT_RE = re.compile(
    r'^(?:no|none|nil|zero|na|n/?a|null|not\s+applicable|not\s+given|cleared|'
    r'-+|\.+|0+\.?0*)'
    r'(?:\s+(?:backlogs?|subjects?|papers?|arrears?|pending|exams?))?\.?$',
    re.I,
)


def _text_is_no_backlog(value) -> bool:
    """True when the free-text `students.backlogs` column states there is no
    pending backlog (cleared/none/0/…), so the structured backlog table should
    not surface rows even if it is momentarily out of sync."""
    return bool(_NO_BACKLOG_TEXT_RE.match(_as_str(value).strip()))


def _dynamic_fee_fields(dynamic_data):
    if not dynamic_data:
        return []
    try:
        parsed = json.loads(dynamic_data) if isinstance(dynamic_data, str) else dynamic_data
    except (ValueError, TypeError):
        return []
    if not isinstance(parsed, dict):
        return []
    out = []
    for key, value in parsed.items():
        if key == "timestamp" or not _is_fee_key(key):
            continue
        text = _as_str(value)
        if text.lower() in ("", "none", "null"):
            continue
        out.append({"label": _friendly_fee_label(key), "value": text})
    return out


def _serialize(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if k in ("dynamic_data",):
            continue
        if isinstance(v, datetime):
            out[k] = v.strftime("%Y-%m-%d")
        elif v is None:
            out[k] = None
        elif hasattr(v, "isoformat"):
            out[k] = str(v)
        else:
            try:
                import decimal
                if isinstance(v, decimal.Decimal):
                    out[k] = float(v)
                    continue
            except Exception:
                pass
            out[k] = v
    return out


def _result_headers(rows: list[dict]) -> list[str]:
    if not rows:
        return []
    headers = list(rows[0].keys())
    for row in rows[1:]:
        for key in row:
            if key not in headers:
                headers.append(key)
    return [h for h in headers if h != "dynamic_data"]


# ── Category-scoped table reports ─────────────────────────────────────────────
#
# A dashboard search already knows WHICH students and columns the staff are
# looking at. Category reports build ONLY the columns for the chosen category
# — a Student List never drags in fees/backlogs/personal data, a Fees report
# never drags in marks, etc. Values are still refreshed from current MySQL and
# masked by role, so exports are scoped, accurate and permission-respecting.

REPORT_CATEGORIES = (
    "student_list", "academic", "personal", "fees", "discontinued", "individual",
)

CATEGORY_TITLES = {
    "student_list": "Student List Report",
    "academic": "Academic Report",
    "personal": "Personal Details Report",
    "fees": "Fees Report",
    "discontinued": "Discontinued Students Report",
    "individual": "Individual Student Report",
}

# A merged student_list cell lists at most this many distinct values before it
# truncates to "+N more", so one wide column cannot swallow a whole PDF page.
_LIST_CELL_VALUE_CAP = 12

FIELD_LABELS = {
    "usn": "USN", "name": "Name", "branch": "Branch", "current_sem": "Semester",
    "semester": "Semester", "sgpa": "SGPA", "cgpa": "CGPA", "year": "Year",
    "dob": "Date of Birth", "gender": "Gender", "blood_group": "Blood Group",
    "father_name": "Father's Name", "mother_name": "Mother's Name",
    "phone": "Phone", "email": "Email", "aadhar_no": "Aadhaar No",
    "address": "Address", "permanent_address": "Permanent Address",
    "current_address": "Current Address", "village": "Village", "taluk": "Taluk",
    "district": "District", "state": "State", "pin_code": "PIN Code",
    "religion": "Religion", "caste": "Caste", "category": "Category",
    "student_type": "Student Type", "quota": "Quota",
    "year_of_joining": "Year of Joining", "admission_year": "Admission Year",
    "hk_status": "HK/Non-HK", "area_type": "Rural/Urban",
    "distance_from_college": "Distance from College", "status": "Status",
    "total_paid": "Total Paid (Rs)", "total_pending": "Total Pending (Rs)",
    "fee_records": "Fee Records", "payment_status": "Payment Status",
    "lifecycle_status": "Status", "effective_date": "Discontinuation Date",
    "reason": "Reason", "reason_category": "Reason Category",
    "last_enrolled_semester": "Last Enrolled Semester",
    "document_ref": "Document Reference", "updated_by": "Last Updated By",
}

# Fixed column set for the Personal Details category (role-masked below).
_PERSONAL_REPORT_KEYS = [
    "usn", "name", "dob", "gender", "blood_group", "father_name", "mother_name",
    "phone", "email", "aadhar_no", "address", "permanent_address",
    "current_address", "village", "taluk", "district", "state", "pin_code",
    "religion", "caste", "category", "student_type",
]


def field_label(key: str) -> str:
    return FIELD_LABELS.get(key, key.replace("_", " ").title())


def _to_number(value):
    text = _as_str(value)
    for token in ("Rs", "rs", ",", "₹"):
        text = text.replace(token, "")
    try:
        return float(text.strip())
    except ValueError:
        return None


def _fmt_num(value):
    if value is None:
        return ""
    number = _to_number(value)
    if number is None:
        return _as_str(value)
    return int(number) if float(number).is_integer() else round(number, 2)


def _display_cell(value):
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return _fmt_num(value)
    return _as_str(value)


def _fetch_students_by_rows(cur, rows):
    """Load the students referenced by the displayed rows (order preserved)."""
    result_usns, seen = [], set()
    for row in rows:
        norm = _norm_usn(row.get("usn"))
        if norm and norm not in seen:
            seen.add(norm)
            result_usns.append(norm)
    students: dict[str, dict] = {}
    if result_usns:
        placeholders = ",".join(["%s"] * len(result_usns))
        cur.execute(
            f"SELECT * FROM students WHERE {_norm_sql_expr('usn')} IN ({placeholders})",
            list(result_usns),
        )
        for row in cur.fetchall():
            students[_norm_usn(row.get("usn"))] = row
    return result_usns, students


def _reg_or_posted(srow: dict | None, row: dict, key: str, role: str) -> str:
    """One field of one student, taken from the register when it holds them.

    The submitted dashboard row is a fallback only for a USN the database has
    never seen: a report is an official document, so a browser must not be able
    to write values into it by posting them.
    """
    return _as_str((srow if srow else mask_for_role(row, role)).get(key))


def _unique_student_rows(rows):
    """Collapse the displayed rows to one entry per student, preserving
    first-seen order.

    The dashboard feeds reports the raw result rows, and a query that joins
    per-semester marks or per-record fees returns the SAME student once per
    joined row. Student-scoped categories (personal, fees, academic,
    discontinued) summarize a student, so iterating the raw rows would repeat
    that student's block once per join row. Rows without a resolvable USN are
    kept as-is (they cannot be de-duplicated safely).
    """
    unique, seen = [], set()
    for row in rows:
        norm = _norm_usn(row.get("usn"))
        if not norm:
            unique.append(row)
            continue
        if norm in seen:
            continue
        seen.add(norm)
        unique.append(row)
    return unique


def build_table_report_model(rows: list[dict], user: dict, category: str) -> dict:
    """Build a category-scoped, table-shaped report model.

    `rows` are exactly the records shown/selected on the dashboard, in the
    dashboard's filter+sort order. Nothing beyond the category's columns is
    ever fetched or included; missing data stays blank (never invented).
    """
    if category not in REPORT_CATEGORIES or category == "individual":
        raise ValueError(f"Unsupported table report category: {category}")

    role = user.get("role", "Staff")
    username = user.get("username", "Unknown")
    notes: list[str] = []
    columns: list[tuple[str, str]] = []
    records: list[dict] = []

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        result_usns, students = _fetch_students_by_rows(cur, rows)
        # Student-scoped categories summarize one row per student; collapse the
        # duplicated join rows the dashboard hands us so nothing repeats.
        student_rows = _unique_student_rows(rows)

        if category == "student_list":
            # The displayed rows are the source of truth for a list report —
            # the query engine computed them live (including derived values like
            # the current semester), and re-reading the flat cache columns here
            # would show stale values the staff never saw on screen. They arrive
            # from the caller over HTTP though, so they are NOT already masked:
            # whatever the browser holds, this is the door that decides what the
            # printed file may contain for this role.
            # A list is a roster, so one student is printed once. A join (marks
            # per semester, fees per record) hands the same student back on
            # several rows; each student's rows are merged into a single line.
            # A column holding one value across those rows keeps it; a column
            # that genuinely varies lists its values in row order, so merging
            # neither invents a value nor throws a per-record detail away.
            headers = _result_headers(rows)
            columns = [(h, field_label(h)) for h in headers]
            groups: list[list[dict]] = []
            group_of: dict[str, int] = {}
            for row in rows:
                clean = _serialize(mask_for_role(
                    {k: v for k, v in row.items() if k != "dynamic_data"}, role))
                cells = {h: _display_cell(clean.get(h)) for h in headers}
                norm = _norm_usn(clean.get("usn"))
                # Exact duplicates in every displayed column collapse to one line.
                # Rows that differ in any displayed column are all kept so no data is lost.
                key = (norm or "") + "|" + "|".join(_as_str(cells[h]) for h in headers)
                if key in group_of:
                    groups[group_of[key]].append(cells)
                    continue
                group_of[key] = len(groups)
                groups.append([cells])

            merged_students = 0
            for group in groups:
                if len(group) > 1:
                    merged_students += 1
                record = {}
                for h in headers:
                    vals = [cells[h] for cells in group]
                    if len(dict.fromkeys(vals)) == 1:
                        record[h] = vals[0]
                        continue
                    shown = vals[:_LIST_CELL_VALUE_CAP]
                    text = ", ".join(_as_str(v) for v in shown)
                    if len(vals) > len(shown):
                        text += f", +{len(vals) - len(shown)} more"
                    record[h] = text
                records.append(record)
            collapsed = sum(len(g) for g in groups) - len(groups)
            if collapsed:
                notes.append(f"{collapsed} duplicate result row(s) were collapsed and merged so each student "
                             f"appears on one line; columns that differ between a student's "
                             f"rows list all of their values in order. Use the Academic report "
                             f"for one row per semester.")

        elif category == "academic":
            academic_map: dict[str, list] = {}
            if result_usns:
                placeholders = ",".join(["%s"] * len(result_usns))
                cur.execute(
                    "SELECT usn, semester, sgpa, "
                    "ROUND(AVG(sgpa) OVER (PARTITION BY usn ORDER BY semester "
                    "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS cgpa "
                    f"FROM marks WHERE {_norm_sql_expr('usn')} IN ({placeholders}) "
                    "AND sgpa IS NOT NULL ORDER BY usn, semester ASC",
                    list(result_usns),
                )
                for m in cur.fetchall():
                    academic_map.setdefault(_norm_usn(m["usn"]), []).append(m)
            columns = [("usn", "USN"), ("name", "Name"), ("branch", "Branch"),
                       ("semester", "Semester"), ("sgpa", "SGPA"),
                       ("cgpa", "Cumulative CGPA")]
            missing = 0
            for row in student_rows:
                norm = _norm_usn(row.get("usn"))
                srow = students.get(norm) or {}
                name = _reg_or_posted(srow, row, "name", role)
                branch = _reg_or_posted(srow, row, "branch", role)
                sems = academic_map.get(norm, [])
                if not sems:
                    missing += 1
                    records.append({"usn": row.get("usn") or norm, "name": name,
                                    "branch": branch, "semester": "", "sgpa": "", "cgpa": ""})
                    continue
                for m in sems:
                    records.append({"usn": srow.get("usn") or row.get("usn") or norm,
                                    "name": name, "branch": branch,
                                    "semester": _fmt_num(m.get("semester")),
                                    "sgpa": _fmt_num(m.get("sgpa")),
                                    "cgpa": _fmt_num(m.get("cgpa"))})
            if missing:
                notes.append(f"{missing} student(s) have no recorded marks; their cells are left blank.")

        elif category == "personal":
            columns = [(k, field_label(k)) for k in _PERSONAL_REPORT_KEYS]
            unverified = 0
            for row in student_rows:
                norm = _norm_usn(row.get("usn"))
                srow = students.get(norm)
                # The register answers for a student it holds. A value MySQL does
                # not have must not be printed as the college's record just
                # because the browser posted one — a report is an official
                # document, and the college is responsible for what it says.
                # Only a USN the register has never seen uses the submitted row,
                # and then only through the same role mask.
                source = srow if srow else dict(row)
                unverified += 0 if srow else 1
                source = mask_for_role(source, role)
                source = _serialize({k: v for k, v in source.items() if k != "dynamic_data"})
                records.append({k: _display_cell(source.get(k)) for k, _ in columns})
            if unverified:
                notes.append(f"{unverified} USN(s) are not in the register; their cells come "
                             f"from the submitted rows rather than from the database.")

        elif category == "fees":
            fees_map: dict[str, list] = {}
            if result_usns:
                placeholders = ",".join(["%s"] * len(result_usns))
                cur.execute(
                    f"SELECT usn, fee_type, year, status, amount_paid, remaining_amount "
                    f"FROM student_fees WHERE {_norm_sql_expr('usn')} IN ({placeholders}) "
                    "ORDER BY usn, fee_type, year",
                    list(result_usns),
                )
                for f in cur.fetchall():
                    fees_map.setdefault(_norm_usn(f["usn"]), []).append(f)
            columns = [("usn", "USN"), ("name", "Name"), ("fee_records", "Fee Records"),
                       ("total_paid", "Total Paid (Rs)"), ("total_pending", "Total Pending (Rs)"),
                       ("payment_status", "Payment Status")]
            no_fee = 0
            for row in student_rows:
                norm = _norm_usn(row.get("usn"))
                srow = students.get(norm) or {}
                name = _reg_or_posted(srow, row, "name", role)
                frows = fees_map.get(norm, [])
                paid_vals = [_to_number(f.get("amount_paid")) for f in frows]
                pend_vals = [_to_number(f.get("remaining_amount")) for f in frows]
                paid_known = any(v is not None for v in paid_vals)
                pend_known = any(v is not None for v in pend_vals)
                total_paid = sum(v for v in paid_vals if v is not None) if paid_known else None
                total_pending = sum(v for v in pend_vals if v is not None) if pend_known else None
                statuses = {normalize_fee_status(f.get("status"))[0] for f in frows}
                if not frows:
                    overall = "Not Recorded"
                    no_fee += 1
                elif total_paid and total_pending and total_pending > 0:
                    overall = "Partially Paid"
                elif total_pending and total_pending > 0:
                    overall = "Not Paid"
                elif total_paid and total_paid > 0:
                    overall = "Paid"
                elif statuses == {"paid"}:
                    overall = "Paid"
                elif statuses and statuses <= {"na", "unknown"}:
                    overall = "Not Recorded"
                else:
                    overall = "Partially Paid" if "paid" in statuses else "Not Paid"
                records.append({
                    "usn": srow.get("usn") or row.get("usn") or norm,
                    "name": name,
                    "fee_records": len(frows),
                    "total_paid": _fmt_num(total_paid),
                    "total_pending": _fmt_num(total_pending),
                    "payment_status": overall,
                })
            if no_fee:
                notes.append(f"{no_fee} student(s) have no fee records; amounts are left blank, not zero.")

        elif category == "discontinued":
            import lifecycle as LC
            lifecycle_map: dict[str, dict] = {}
            if result_usns:
                placeholders = ",".join(["%s"] * len(result_usns))
                try:
                    cur.execute(
                        f"SELECT usn, current_status, effective_date, last_enrolled_semester, "
                        f"reason, reason_category, document_ref, updated_by "
                        f"FROM student_lifecycle_status WHERE {_norm_sql_expr('usn')} IN ({placeholders})",
                        list(result_usns),
                    )
                    for lc_row in cur.fetchall():
                        lifecycle_map[_norm_usn(lc_row["usn"])] = lc_row
                except Exception:
                    pass  # table may be absent in a fresh DB; fall back below
            columns = [("usn", "USN"), ("name", "Name"), ("branch", "Branch"),
                       ("lifecycle_status", "Status"),
                       ("effective_date", "Discontinuation Date"),
                       ("reason", "Reason"), ("reason_category", "Reason Category"),
                       ("last_enrolled_semester", "Last Enrolled Semester"),
                       ("document_ref", "Document Reference"),
                       ("updated_by", "Last Updated By")]
            excluded = 0
            for row in student_rows:
                norm = _norm_usn(row.get("usn"))
                srow = students.get(norm) or {}
                lc_row = lifecycle_map.get(norm) or {}
                status = (_as_str(lc_row.get("current_status"))
                          or _as_str(srow.get("lifecycle_status"))
                          or (_reg_or_posted({}, row, "lifecycle_status", role) if not srow else "")
                          or "Active")
                if status not in LC.DISCONTINUED_STATUSES:
                    excluded += 1
                    continue
                records.append({
                    "usn": srow.get("usn") or row.get("usn") or norm,
                    "name": _reg_or_posted(srow, row, "name", role),
                    "branch": _as_str(srow.get("branch")),
                    "lifecycle_status": status,
                    "effective_date": _display_cell(lc_row.get("effective_date")),
                    "reason": _as_str(lc_row.get("reason")),
                    "reason_category": _as_str(lc_row.get("reason_category")),
                    "last_enrolled_semester": _fmt_num(lc_row.get("last_enrolled_semester")),
                    "document_ref": _as_str(lc_row.get("document_ref")),
                    "updated_by": _as_str(lc_row.get("updated_by")),
                })
            if excluded:
                notes.append(f"{excluded} student(s) in the selected records are not discontinued "
                             "and were excluded from this report.")
            if not records:
                notes.append("None of the selected students carry a discontinuation/dropout status.")
        cur.close()

    return {
        "institution": INSTITUTION,
        "generated_by": {"role": role, "username": username, "timestamp": now_str()},
        "category": category,
        "title": CATEGORY_TITLES[category],
        "columns": [{"key": k, "label": lbl} for k, lbl in columns],
        "records": records,
        "record_count": len(records),
        "input_count": len(rows),
        "notes": notes,
    }
