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
from datetime import datetime, timedelta
import re, os, uuid, json as _json
from database import db_conn, write_audit_log
from auth import get_current_user, require_roles
from file_parser import parse_file
from canonical_fields import (
    validate_mapped_rows, validate_sgpa_value, extract_marks_from_row, sanitize_row_fields, _is_empty,
    map_column,
)
from graduation_manager import parse_usn_full
from config import settings
from error_messages import safe_http_error
from address_parser import enrich_row_from_address, normalize_area_type

router = APIRouter(prefix="/api/files", tags=["File Management"])

_file_cache: dict[str, bytes] = {}

STUDENT_COLS = [
    'name', 'dob', 'year_of_joining', 'current_sem',
    'father_name', 'mother_name', 'blood_group', 'address', 'status',
    'gender', 'religion', 'caste', 'sub_caste', 'category',
    'permanent_address', 'current_address', 'phone', 'email',
    'aadhar_no', 'year_and_branch', 'source_file', 'branch', 'division', 'domain',
    'region', 'village', 'area_type', 'area',
    'emergency_contact_number', 'taluk', 'district', 'state', 'cgpa',
    # New 2024 Google Form fields
    'father_occupation', 'mother_occupation', 'parents_phone',
    'hk_status', 'quota', 'distance_from_college',
    'kannada_medium', 'physically_handicapped', 'pin_code', 'post_office',
    'backlogs', 'snq_quota',
]

# Fee columns — stored in student_fees table, not in students
_FEE_COLS = {
    'fee_vtu_1':   ('VTU',  1),
    'fee_vtu_2':   ('VTU',  2),
    'fee_vtu_3':   ('VTU',  3),
    'fee_vtu_4':   ('VTU',  4),
    'fee_pd_1':    ('PD',   1),
    'fee_pd_2':    ('PD',   2),
    'fee_pd_3':    ('PD',   3),
    'fee_pd_4':    ('PD',   4),
    'fee_idp_1':   ('IDP',  1),
    'fee_idp_2':   ('IDP',  2),
    'fee_idp_3':   ('IDP',  3),
    'fee_idp_4':   ('IDP',  4),
    'fee_tuition_paid':      ('TUITION_PAID',      0),
    'fee_tuition_remaining': ('TUITION_REMAINING', 0),
}

# 'fee_hostel_2' → ('HOSTEL', 2); 'fee_pending' → ('PENDING', 0)
_FEE_HEADING_RE = re.compile(r'^fee_(.+?)(?:_([1-8]))?$')

_COL_MAX = {
    'usn': 100, 'name': 100, 'father_name': 150, 'mother_name': 150,
    'blood_group': 10, 'status': 20, 'gender': 10, 'religion': 50,
    'caste': 100, 'sub_caste': 100, 'category': 20,
    'phone': 20, 'aadhar_no': 20, 'year_and_branch': 100,
    'source_file': 255, 'branch': 50, 'division': 50, 'domain': 100,
    'region': 100, 'village': 100, 'area_type': 20, 'area': 100,
    'emergency_contact_number': 20, 'taluk': 100, 'district': 100, 'state': 100,
    # New fields
    'father_occupation': 100, 'mother_occupation': 100,
    'parents_phone': 20, 'hk_status': 20, 'quota': 100,
    'distance_from_college': 50, 'kannada_medium': 10,
    'physically_handicapped': 10, 'pin_code': 10, 'post_office': 100,
    'snq_quota': 10,
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


def _clean_region(val):
    value = _clean_str(val, _COL_MAX.get('region'))
    if not value:
        return None
    normalized = re.sub(r'[^a-z]+', ' ', value.lower()).strip()
    if re.search(r'\burban\b', normalized):
        return 'URBAN'
    if re.search(r'\brural\b', normalized):
        return 'RURAL'
    return value[:100]  # Keep geographic region names as-is (widened)

def _clean_area_type(val):
    """Normalize RURAL/URBAN classifier values."""
    from address_parser import normalize_area_type
    return normalize_area_type(str(val)) if not _is_empty(val) else None

def _clean_date(val):
    if _is_empty(val): return None
    s = str(val).strip()
    try:
        import pandas as pd
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            return pd.to_datetime(s, dayfirst=True).strftime('%Y-%m-%d')
    except Exception: return None


# Columns a spreadsheet holds as *text* even though Excel reads them as numbers.
_DIGIT_COLS = {'phone', 'aadhar_no', 'emergency_contact_number',
               'parents_phone', 'pin_code'}
_TRAILING_ZEROS_RE = re.compile(r'^(\d+)[.,]0+$')



def _clean_digits(val, max_len=None):
    """A phone/ID number cell keeps its identity: Excel's 9000007777.0 or
    9.000007777e+09 must not be stored as a decimal number or scientific text."""
    s = _clean_str(val, max_len)
    if s is None:
        return None
    m = _TRAILING_ZEROS_RE.match(s.replace(' ', ''))
    if m:
        return m.group(1)
    try:
        as_float = float(s)
    except (TypeError, ValueError):
        return s
    # 9.000007777E+9 is the same phone number Excel meant; beyond 15 digits a
    # float stops being exact, so that text is left as the person typed it.
    if as_float == int(as_float) and len(s) <= 15 and int(as_float) > 0:
        return str(int(as_float))
    return s


def _clean_cell(col, raw, max_len=None):
    if col in _DIGIT_COLS:
        return _clean_digits(raw, max_len)
    return _clean_str(raw, max_len)


def _valid_usn(usn: str) -> bool:

    if not usn or len(usn) > 100: return False
    if ' ' in usn: return False
    return bool(_USN_RE.match(usn))

def _parse_usn(usn: str) -> dict:
    return parse_usn_full(usn) or {}

def _clear_cache(conn):
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM query_cache")
    finally:
        cursor.close()


def _latest_active_source(cur, usn: str, field_name: str, excluding_filename: str):
    cur.execute(
        "SELECT field_value FROM student_field_sources "
        "WHERE usn=%s AND field_name=%s AND source_filename<>%s AND is_active=1 "
        "ORDER BY uploaded_at DESC, id DESC LIMIT 1",
        (usn, field_name, excluding_filename),
    )
    return cur.fetchone()


def _mark_provenance_field(semester: int) -> str:
    """Provenance key for semester SGPA in student_field_sources (not a students column)."""
    return f"mark_sem_{int(semester)}_sgpa"


def _write_provenance(cur, usn: str, field_name: str, field_value, source_filename: str, import_id=None):
    """Persist the file that owns a field value; failures abort the import transaction."""
    cur.execute(
        """
        INSERT INTO student_field_sources
            (usn, field_name, field_value, source_filename, import_id, is_active)
        VALUES (%s, %s, %s, %s, %s, 1)
        ON DUPLICATE KEY UPDATE
            field_value = VALUES(field_value),
            import_id   = VALUES(import_id),
            uploaded_at = NOW(),
            is_active   = 1
        """,
        (usn, field_name, str(field_value)[:1000] if field_value is not None else None,
         source_filename, import_id),
    )

def _upload_path(filename: str) -> str:
    """Resolve an upload filename to a path guaranteed to stay inside the upload
    directory. A client-controlled filename (`../../etc/…`, absolute paths, …)
    must never read or write outside uploads/."""
    upload_dir = os.path.realpath(settings.upload_dir_abs)
    name = os.path.basename((filename or "").replace("\\", "/"))
    if not name or name in (".", ".."):
        raise HTTPException(400, "Invalid file name.")
    resolved = os.path.realpath(os.path.join(upload_dir, name))
    if os.path.commonpath((upload_dir, resolved)) != upload_dir:
        raise HTTPException(400, "Invalid file name.")
    return resolved


def _get_upload_cache(filename: str):
    if filename in _file_cache:
        return _file_cache[filename]
    disk_path = _upload_path(filename)
    if os.path.exists(disk_path):
        with open(disk_path, 'rb') as f:
            content = f.read()
        _file_cache[filename] = content
        return content
    return None

def _save_upload_cache(filename: str, content: bytes):
    _file_cache[filename] = content
    disk_path = _upload_path(filename)
    with open(disk_path, 'wb') as f:
        f.write(content)

def _remove_upload_cache(filename: str):
    _file_cache.pop(filename, None)
    disk_path = _upload_path(filename)
    if os.path.exists(disk_path):
        try: os.remove(disk_path)
        except Exception: pass


def _trash_path_for(filename: str) -> str:
    trash_dir = os.path.join(settings.upload_dir_abs, ".trash")
    os.makedirs(trash_dir, exist_ok=True)
    return os.path.join(trash_dir, f"{uuid.uuid4().hex}_{os.path.basename(filename)}")


def _resolve_trash_path(path: str) -> str:
    upload_dir = os.path.realpath(settings.upload_dir_abs)
    resolved = os.path.realpath(os.path.join(upload_dir, path))
    if os.path.commonpath((upload_dir, resolved)) != upload_dir:
        raise HTTPException(400, "Invalid trash file path.")
    return resolved


def _purge_expired_trash(cur):
    """Hard-delete Trash entries older than 30 days. Returns those filenames so
    the caller can retire exactly the student data that file introduced."""
    cur.execute(
        "SELECT filename, trash_path FROM uploaded_files "
        "WHERE trashed_at < DATE_SUB(NOW(), INTERVAL 30 DAY)"
    )
    expired_files = cur.fetchall()
    purged = []
    for file_row in expired_files:
        try:
            if file_row.get("trash_path"):
                disk_path = _resolve_trash_path(file_row["trash_path"])
                if os.path.exists(disk_path):
                    os.remove(disk_path)
        except Exception:
            continue
        cur.execute(
            "DELETE FROM uploaded_files WHERE filename=%s "
            "AND trashed_at < DATE_SUB(NOW(), INTERVAL 30 DAY)",
            (file_row["filename"],),
        )
        if cur.rowcount:
            purged.append(file_row["filename"])
    return purged


def _reconcile_trashed_file_records(cur, conn, actor: str = "system"):
    """Remove legacy file-only student rows left behind by older soft deletes.

    This is real data loss, so it may never be silent or unrecoverable: every
    file that retires students leaves a FILE_DATA_PURGE audit row naming them and
    an undo snapshot holding their state — the trashed file's own delete token
    when it has one, otherwise a fresh DELETE snapshot.
    """
    from routes_undo import _capture_state, create_undo_snapshot, finalize_undo_snapshot

    cur.execute(
        "SELECT filename, trash_undo_token FROM uploaded_files "
        "WHERE trashed_at IS NOT NULL AND data_reconciled_at IS NULL"
    )
    trashed_files = cur.fetchall()
    changed = False

    for trashed_file in trashed_files:
        filename = trashed_file["filename"]
        cur.execute("SELECT usn FROM students WHERE source_file=%s", (filename,))
        candidate_usns = [row["usn"] for row in cur.fetchall()]
        removed_usns = []

        to_remove = []
        for usn in candidate_usns:
            cur.execute(
                "SELECT COUNT(*) AS source_count FROM student_field_sources "
                "WHERE usn=%s AND source_filename<>%s AND is_active=1",
                (usn, filename),
            )
            if cur.fetchone()["source_count"]:
                continue
            to_remove.append(usn)

        undo_token = trashed_file.get("trash_undo_token")
        delete_snapshot = None
        if undo_token:
            cur.execute(
                "SELECT snapshot_data FROM global_undo_snapshots "
                "WHERE undo_token=%s AND committed=1 AND undone=0",
                (undo_token,),
            )
            delete_snapshot = cur.fetchone()
        if to_remove and delete_snapshot is None:
            undo_token = create_undo_snapshot(
                "DELETE", to_remove, actor,
                f"Trashed file {filename} retired {len(to_remove)} student(s) it introduced alone",
                conn=conn)

        for usn in to_remove:
            cur.execute("DELETE FROM marks WHERE usn=%s", (usn,))
            cur.execute("DELETE FROM student_fees WHERE usn=%s", (usn,))
            cur.execute("DELETE FROM student_backlogs WHERE usn=%s", (usn,))
            cur.execute("DELETE FROM students WHERE usn=%s AND source_file=%s", (usn, filename))
            if cur.rowcount:
                removed_usns.append(usn)
                changed = True

        if not removed_usns:
            cur.execute(
                "UPDATE uploaded_files SET data_reconciled_at=NOW() "
                "WHERE filename=%s AND trashed_at IS NOT NULL",
                (filename,),
            )
            continue

        write_audit_log("FILE_DATA_PURGE", actor, "", "students",
                        ",".join(removed_usns[:20]),
                        f"Removed {len(removed_usns)} student(s) introduced only by "
                        f"trashed file {filename}")
        if delete_snapshot is not None:
            affected_usns = _json.loads(delete_snapshot["snapshot_data"]).get(
                "affected_usns", removed_usns)
            post_state = _capture_state(cur, affected_usns)
            cur.execute(
                "UPDATE global_undo_snapshots SET post_state_data=%s "
                "WHERE undo_token=%s AND committed=1 AND undone=0",
                (_json.dumps(post_state), trashed_file["trash_undo_token"]),
            )
        else:
            finalize_undo_snapshot(undo_token, removed_usns, conn)

        cur.execute(
            "UPDATE uploaded_files SET data_reconciled_at=NOW() "
            "WHERE filename=%s AND trashed_at IS NOT NULL",
            (filename,),
        )

    return changed


def _reconcile_orphaned_source_records(cur, filenames, actor: str = "system", conn=None):
    """Remove students introduced *only* by files that have just been purged
    from Trash. `filenames` must be the concrete purged files: a student whose
    source file is merely unrecognised (script-seeded, restored from a backup,
    or imported before upload tracking existed) is still real college data and
    must never be deleted by a guess."""
    filenames = sorted({f for f in (filenames or []) if f and f.strip()})
    if not filenames:
        return False

    placeholders = ",".join(["%s"] * len(filenames))
    cur.execute(
        f"SELECT s.usn FROM students s "
        f"WHERE s.source_file IN ({placeholders}) "
        f"AND NOT EXISTS (SELECT 1 FROM student_field_sources p "
        f"WHERE p.usn=s.usn AND p.is_active=1)",
        filenames,
    )
    orphaned_usns = [row["usn"] for row in cur.fetchall()]
    if not orphaned_usns:
        return False

    from routes_undo import create_undo_snapshot
    create_undo_snapshot("DELETE", orphaned_usns, actor,
                         f"Purged {len(orphaned_usns)} student(s) of trashed file(s)",
                         conn=conn)
    for usn in orphaned_usns:
        cur.execute("DELETE FROM marks WHERE usn=%s", (usn,))
        cur.execute("DELETE FROM student_fees WHERE usn=%s", (usn,))
        cur.execute("DELETE FROM student_backlogs WHERE usn=%s", (usn,))
        cur.execute("DELETE FROM students WHERE usn=%s", (usn,))
    write_audit_log("FILE_DATA_PURGE", actor, "", "students",
                    ",".join(orphaned_usns[:20]),
                    f"Removed {len(orphaned_usns)} student(s) from purged file(s): "
                    f"{', '.join(filenames[:5])}")
    return True


def reconcile_trashed_file_data():
    """Apply pending Trash cleanup for files the college explicitly trashed.

    Never called from a read endpoint: browsing students or analytics must not
    mutate student records.
    """
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        changed = _reconcile_trashed_file_records(cur, conn, "system")
        purged = _purge_expired_trash(cur)
        changed = _reconcile_orphaned_source_records(cur, purged, "system", conn) or changed
        if changed:
            _clear_cache(conn)
        conn.commit()
        cur.close()
    return changed


def _student_payload(row: dict, name: str | None = None) -> dict:
    # Enrich address-derived fields first
    row = enrich_row_from_address(row)
    # Include all original row fields to preserve dynamic data
    payload = dict(row)
    for col in STUDENT_COLS:
        if col == 'dob':
            payload[col] = _clean_date(row.get(col))
        elif col == 'name':
            payload[col] = _clean_str(name if name is not None else row.get('name'), _COL_MAX.get('name'))
        elif col == 'current_sem':
            payload[col] = _safe_int(row.get('current_sem')) or _safe_int(row.get('semester'))
        elif col == 'year_of_joining':
            payload[col] = _safe_int(row.get('year_of_joining')) or _safe_int(row.get('admission_year'))
        elif col == 'region':
            payload[col] = _clean_region(row.get(col))
        elif col == 'area_type':
            payload[col] = _clean_area_type(row.get(col))
        elif col == 'cgpa':
            payload[col] = _safe_dec(row.get(col))
        else:
            payload[col] = _clean_cell(col, row.get(col), _COL_MAX.get(col))
    payload['source_file'] = payload.get('source_file')  # may be set by caller
    return payload



# ── Provisional USN generation for name-only (no-USN) files ───────────────────
_FILENAME_YEAR_RE = re.compile(r'(20\d{2})')
# Human branch labels → 2-letter VTU branch slot used inside a USN.
_BRANCH_CODE_MAP = {
    'CSE': 'CS', 'CS': 'CS', 'COMPUTER SCIENCE': 'CS', 'CSC': 'CS',
    'ECE': 'EC', 'EC': 'EC', 'E&C': 'EC',
    'ME': 'ME', 'MECH': 'ME', 'MECHANICAL': 'ME', 'MSE': 'ME',
    'CE': 'CE', 'CIVIL': 'CE',
    'EE': 'EE', 'EEE': 'EE', 'ELECTRICAL': 'EE',
    'CH': 'CH', 'CHEM': 'CH', 'CHEMICAL': 'CH',
    'IM': 'IM', 'ISM': 'IM', 'IEM': 'IM', 'INSTRUMENTATION': 'IM',
}


def _batch_year_from_filename(filename: str) -> str | None:
    """Return the 2-digit VTU year slot from a '20YY' token in the filename."""
    m = _FILENAME_YEAR_RE.search(filename or '')
    return m.group(1)[-2:] if m else None


def _map_branch_code(raw) -> str | None:
    if _is_empty(raw):
        return None
    s = str(raw).strip().upper()
    if s in _BRANCH_CODE_MAP:
        return _BRANCH_CODE_MAP[s]
    for key, code in _BRANCH_CODE_MAP.items():
        if re.search(rf'\b{re.escape(key)}\b', s):
            return code
    return None


def _infer_usn_scheme(cur, rows: list[dict]) -> tuple[str, str]:
    """Pick (college prefix incl. degree digit, branch slot) for generated USNs.

    Prefers a branch evident in the file, then the dominant college prefix and
    branch already stored in students. Falls back to ('4HG', 'CS').
    """
    branch = None
    for r in rows:
        branch = _map_branch_code(r.get('branch'))
        if branch:
            break

    prefix = '4HG'
    try:
        cur.execute(
            "SELECT LEFT(usn,3) AS p, COUNT(*) AS c FROM students "
            "WHERE usn REGEXP '^[0-9][A-Z]{2}' GROUP BY p ORDER BY c DESC LIMIT 1")
        row = cur.fetchone()
        p = row.get('p') if isinstance(row, dict) else (row[0] if row else None)
        if p:
            prefix = str(p)
    except Exception:
        pass

    if not branch:
        branch = 'CS'
        try:
            cur.execute(
                "SELECT SUBSTRING(usn,6,2) AS b, COUNT(*) AS c FROM students "
                "WHERE usn REGEXP %s GROUP BY b ORDER BY c DESC LIMIT 1",
                ('^' + re.escape(prefix) + '[0-9]{2}[A-Z]{2}',))
            row = cur.fetchone()
            b = row.get('b') if isinstance(row, dict) else (row[0] if row else None)
            if b and re.fullmatch(r'[A-Z]{2}', str(b)):
                branch = str(b)
        except Exception:
            pass
    return prefix, branch


def _assign_provisional_usns(cur, rows: list[dict], filename: str) -> dict[str, str]:
    """Give name-only rows a temporary VTU-format USN ordered by student name.

    Returns {generated_usn: name}. Mutates each eligible row's 'usn' in place so
    the rest of the import pipeline (validate → classify → upsert) proceeds
    unchanged. ONLY rows with an EMPTY usn and a non-empty name are touched;
    malformed non-empty USNs are left for normal validation to reject. The batch
    year is taken from a '20YY' token in the filename; serials are allocated in
    ascending name order and skip any already used in the DB or by real USNs in
    this file, so generated USNs never collide.
    """
    eligible = [
        (i, str(r['name']).strip())
        for i, r in enumerate(rows)
        if _is_empty(r.get('usn')) and not _is_empty(r.get('name'))
    ]
    if not eligible:
        return {}

    year2 = _batch_year_from_filename(filename)
    if not year2:
        return {}

    prefix, branch = _infer_usn_scheme(cur, [rows[i] for i, _ in eligible])
    stem = f"{prefix}{year2}{branch}"

    used: set[int] = set()
    try:
        cur.execute("SELECT usn FROM students WHERE usn LIKE %s", (stem + '%',))
        for rec in cur.fetchall():
            u = str(rec.get('usn') if isinstance(rec, dict) else rec[0])
            tail = u[len(stem):]
            if tail.isdigit():
                used.add(int(tail))
    except Exception:
        pass
    for r in rows:
        u = '' if _is_empty(r.get('usn')) else str(r.get('usn')).strip()
        if u.startswith(stem) and u[len(stem):].isdigit():
            used.add(int(u[len(stem):]))

    assigned: dict[str, str] = {}
    serial = 0
    for idx, name in sorted(eligible, key=lambda t: (t[1].casefold(), t[0])):
        serial += 1
        while serial in used:
            serial += 1
        usn = f"{stem}{serial:03d}"
        if not _valid_usn(usn):
            continue
        used.add(serial)
        rows[idx]['usn'] = usn
        assigned[usn] = name
    return assigned


def _upsert_student(cur, usn: str, row: dict, source_filename: str = '',
                    import_id=None, provisional: bool = False) -> tuple[str, list]:
    """Insert or update student. Returns ('added'|'updated'|'unchanged', conflict_list)."""
    cur.execute("SELECT * FROM students WHERE usn=%s", (usn,))
    existing = cur.fetchone()
    usn_data = _parse_usn(usn)
    conflicts = []
    
    from dynamic_fields_manager import extract_dynamic_data
    dynamic_data_dict = extract_dynamic_data(row)

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
            elif col == 'region':
                v = _clean_region(row.get(col))
            elif col == 'area_type':
                v = _clean_area_type(row.get(col))
            elif col == 'cgpa':
                v = _safe_dec(row.get(col))
            else:
                v = _clean_cell(col, row.get(col), _COL_MAX.get(col))
            if v is None:
                continue

            # ALWAYS write provenance for every non-None field from this file.
            if source_filename:
                _write_provenance(cur, usn, col, v, source_filename, import_id)

            old = existing.get(col)
            old_s = '' if old is None else str(old).strip()
            new_s = str(v).strip()
            if col == 'name' or old_s == '' or old_s != new_s:
                if old_s != new_s and old_s != '':
                    conflicts.append({'usn': usn, 'field': col, 'old': old_s, 'new': new_s})
                    changed = True
                elif old_s != new_s:
                    changed = True
                updates.append(f"`{col}`=%s")
                params.append(v)
        
        if dynamic_data_dict:
            existing_dynamic = {}
            if existing.get('dynamic_data'):
                try: existing_dynamic = _json.loads(existing['dynamic_data'])
                except: pass
            
            # Check if there are actual changes
            has_new_dynamic = False
            for k, v in dynamic_data_dict.items():
                if existing_dynamic.get(k) != v:
                    has_new_dynamic = True
                    existing_dynamic[k] = v
                    
            if has_new_dynamic:
                updates.append("`dynamic_data`=%s")
                params.append(_json.dumps(existing_dynamic))
                changed = True
                
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
        if provisional and not existing.get('usn_provisional'):
            updates.append("`usn_provisional`=%s")
            params.append(1)
            changed = True
        if updates and changed:
            params.append(usn)
            cur.execute(f"UPDATE students SET {','.join(updates)} WHERE usn=%s", tuple(params))
            return 'updated', conflicts
        if updates and not changed:
            return 'unchanged', conflicts
        return 'unchanged', conflicts
    else:
        fields, vals = ['usn'], [usn]
        for col in STUDENT_COLS:
            if col == 'dob':
                v = _clean_date(row.get(col))
            elif col in ('current_sem', 'year_of_joining'):
                v = row.get(col)
                if v is not None and not isinstance(v, int):
                    v = _safe_int(v)
            elif col == 'region':
                v = _clean_region(row.get(col))
            elif col == 'area_type':
                v = _clean_area_type(row.get(col))
            elif col == 'cgpa':
                v = _safe_dec(row.get(col))
            else:
                v = _clean_cell(col, row.get(col), _COL_MAX.get(col))
            if v is not None:
                fields.append(f'`{col}`')
                vals.append(v)
                if source_filename:
                    _write_provenance(cur, usn, col, v, source_filename, import_id)
        
        if dynamic_data_dict:
            fields.append('`dynamic_data`')
            vals.append(_json.dumps(dynamic_data_dict))
            
        if usn_data:
            fields += ['`admission_year`','`current_year`','`student_type`','`estimated_semester`']
            vals   += [usn_data.get('admission_batch'), usn_data.get('current_year'),
                       usn_data.get('student_type'), usn_data.get('current_sem')]
        if 'name' not in [f.strip('`') for f in fields] and '`name`' not in fields:
            raise ValueError(f"Cannot insert USN {usn}: required field 'name' is missing")
        if provisional:
            fields.append('`usn_provisional`')
            vals.append(1)
        ph = ','.join(['%s'] * len(fields))
        cur.execute(f"INSERT INTO students ({','.join(fields)}) VALUES ({ph})", tuple(vals))
        if source_filename:
            _write_provenance(cur, usn, "__record__", source_filename, source_filename, import_id)
        return 'added', conflicts


def _fee_target(canon_col):
    """(fee_type, year) for any fee heading the mapping recognised.

    A sheet can name a fee line anything ('Fee Pending', 'Hostel Fee 2', the
    four-year VTU/PD/IDP grid). Anything that still starts with the mapped fee
    prefix describes a fee, and a fee that never reaches student_fees is
    invisible to every fee query, the fee editor and the fee reports."""
    if canon_col in _FEE_COLS:
        return _FEE_COLS[canon_col]
    m = _FEE_HEADING_RE.match(canon_col)
    if not m:
        return None
    name = m.group(1).replace('_', ' ').strip().upper()
    if not name:
        return None
    return (name, int(m.group(2)) if m.group(2) else 0)


def _upsert_fees(cur, usn: str, row: dict, problems: list | None = None) -> int:
    """
    Parse all fee columns from a mapped row and upsert into student_fees.
    Returns the number of fee rows written.
    """
    written = 0
    cols = list(_FEE_COLS) + [
        k for k in row
        if isinstance(k, str) and k.startswith('fee_') and k not in _FEE_COLS
    ]
    for canon_col in cols:
        fee_target = _fee_target(canon_col)
        if not fee_target:
            continue
        fee_type, year = fee_target
        raw_val = row.get(canon_col)
        if _is_empty(raw_val):
            continue
        val = _clean_str(raw_val, 100)
        if not val:
            continue
        # Determine status vs amount
        status_keywords = {'paid', 'not paid', 'partially paid', 'not applicable', 'na', 'yes', 'no'}
        low = val.lower().strip()
        is_status = any(kw in low for kw in status_keywords) or low in status_keywords
        status_val = val if is_status else None
        amount_val = val if not is_status else None
        try:
            cur.execute(
                """INSERT INTO student_fees (usn, fee_type, year, status, amount_paid)
                   VALUES (%s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE
                       status=COALESCE(VALUES(status), status),
                       amount_paid=COALESCE(VALUES(amount_paid), amount_paid),
                       updated_at=NOW()""",
                (usn, fee_type, year, status_val, amount_val)
            )
            written += 1
        except Exception as exc:
            # One unreadable fee cell must not abort the whole import, but it
            # must not vanish either: the caller reports what was not stored.
            if problems is not None:
                problems.append(f"{usn}: fee {fee_type}/{year} not stored ({exc})")
    return written


_NO_BACKLOG_RE = re.compile(
    r'^(?:no|none|nil|zero|na|n/?a|null|not\s+applicable|not\s+given|cleared|'
    r'-+|\.+|0+\.?0*)'
    r'(?:\s+(?:backlogs?|subjects?|papers?|arrears?|pending|exams?))?\.?$',
    re.I,
)


def _is_no_backlog(text: str) -> bool:
    return bool(_NO_BACKLOG_RE.match(str(text).strip()))


def _extract_backlog_text(row: dict):
    """
    Backlog text from a canonicalised import row: prefer the mapped 'backlogs'
    column, else any raw key that canonicalises to 'backlogs' (older files left
    the value under a long Google-Form slug in dynamic data).
    """
    if not isinstance(row, dict):
        return None
    direct = row.get('backlogs')
    if not _is_empty(direct):
        return direct
    for k, v in row.items():
        if k == 'backlogs' or _is_empty(v):
            continue
        try:
            canon = map_column(str(k).replace('_', ' '))[0]
        except Exception:
            canon = None
        if canon == 'backlogs':
            return v
    return None


def _upsert_backlogs(cur, usn: str, raw_backlog_text: str,
                    problems: list | None = None) -> int:
    """
    Parse backlog raw text and upsert into student_backlogs.
    Handles the messy real-world form values:
      - "Subject, Semester, Year" (one or several, ;/newline separated)
      - a bare positive integer = number of backlogs (subjects unspecified)
      - "No"/"None"/"0"/"Zero backlogs"/"Not applicable" = nothing to write
    Guarantees at least one row for any student who clearly reports a backlog,
    so "list students with backlogs" never misses them.
    Returns count of backlog records written.
    """
    if _is_empty(raw_backlog_text):
        return 0
    cleaned = str(raw_backlog_text).strip()
    if _is_no_backlog(cleaned):
        return 0

    def _insert(subject, semester=None, year_str=None):
        nonlocal written
        subject = str(subject)[:200]
        try:
            # student_backlogs has no unique key over (usn, subject, semester),
            # so ON DUPLICATE KEY could never fire: re-importing the same sheet
            # added a second copy of every arrears row, and a student who failed
            # one paper started showing two or three.
            cur.execute(
                "SELECT id FROM student_backlogs "
                "WHERE usn=%s AND subject=%s AND ((%s IS NULL AND semester IS NULL) "
                "OR semester=%s) LIMIT 1", (usn, subject, semester, semester))
            found = cur.fetchone()
            found_id = found["id"] if isinstance(found, dict) else (found[0] if found else None)
            if found_id is not None:
                cur.execute(
                    "UPDATE student_backlogs SET year=COALESCE(%s, year), "
                    "raw_text=%s, updated_at=NOW() WHERE id=%s",
                    (year_str, cleaned[:1000], found_id))
            else:
                cur.execute(
                    """INSERT INTO student_backlogs (usn, subject, semester, year, raw_text)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (usn, subject, semester, year_str, cleaned[:1000])
                )
            written += 1
        except Exception as exc:
            # as with fees: a single unreadable arrears row must not abort the
            # import, and it must not disappear without a trace either
            if problems is not None:
                problems.append(f"{usn}: backlog {subject!r} not stored ({exc})")

    written = 0
    # Bare integer (optionally "3.0") = a count of backlogs, subjects unspecified.
    count_m = re.fullmatch(r'(\d+)(?:\.0+)?', cleaned)
    if count_m:
        n = int(count_m.group(1))
        if n > 0:
            _insert(f"{n} backlog" + ("s" if n > 1 else "") + " (subject not specified)")
        return written

    # Descriptive entries: split on delimiters between separate backlog records.
    entries = re.split(r'[;\n]+', cleaned)
    for entry in entries:
        entry = entry.strip()
        if not entry or _is_no_backlog(entry):
            continue
        # Each entry: "Subject , semester, year" or "Subject*semester,year"
        parts = re.split(r'[,*]+', entry)
        subject = parts[0].strip() if parts else entry
        semester = None
        year_str = None
        if len(parts) >= 2:
            m = re.search(r'\d+', parts[1].strip())
            if m:
                semester = int(m.group(0))
        if len(parts) >= 3:
            year_str = parts[2].strip()
        if subject and len(subject) >= 2:
            _insert(subject, semester, year_str)
    # Fallback: text clearly describes a backlog but splitting yielded nothing.
    if written == 0 and re.search(r'[a-z]', cleaned, re.I):
        _insert(cleaned)
    return written


def _upsert_mark(
    cur, usn: str, semester: int, sgpa,
    source_filename: str = '', import_id=None,
) -> str:
    """Insert or update mark. Returns 'added'|'updated'|'unchanged'|'skipped'|'rejected'."""
    if sgpa is None:
        return 'skipped'
    err = validate_sgpa_value(sgpa)
    if err:
        return 'rejected'
    prov_field = _mark_provenance_field(semester)
    if source_filename:
        _write_provenance(cur, usn, prov_field, sgpa, source_filename, import_id)

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
async def upload_file(file: UploadFile = File(...), current_user: dict = Depends(require_roles("Staff", "Admin"))):
    """Step 1: Store file in cache. Does NOT write to DB yet."""
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file.")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in {"csv", "xlsx", "xls", "json", "pdf", "txt", "png", "jpg", "jpeg"}:
        raise HTTPException(422, f"Unsupported file type: .{ext}")
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        reconciled = _reconcile_trashed_file_records(cur, conn, current_user["username"])
        purged = _purge_expired_trash(cur)
        reconciled = _reconcile_orphaned_source_records(
            cur, purged, current_user["username"], conn) or reconciled
        if reconciled:
            _clear_cache(conn)
        cur.execute("SELECT trashed_at FROM uploaded_files WHERE filename=%s", (file.filename,))
        existing = cur.fetchone()
        if existing and existing["trashed_at"] is not None:
            cur.close()
            raise HTTPException(409, "This filename is in Trash. Restore it or use a different filename.")
        _save_upload_cache(file.filename, content)
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
def update_database(filename: str, current_user: dict = Depends(require_roles("Staff", "Admin"))):
    """
    Transaction-safe import with full row accounting.

    Source of truth for counting = mapped_records (one per parsed file row).
    Marks come from extract_marks_from_row on each valid row.
    """
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
        # Every refusal at this door is recorded, whichever guard rejects it:
        # staff must be able to see that a file was tried and why it never landed.
        write_audit_log(action="UPLOAD_NO_DATA_ROWS", username=current_user["username"],
                        role=current_user["role"], target_table="uploaded_files",
                        target_id=filename,
                        summary=f"Rejected {filename}: no data rows found "
                                f"(header-only, blank rows, or an unreadable layout)",
                        success=False, error_info="No data rows found in the file.")
        raise HTTPException(422, "No data rows found in the file.")
        
    all_keys = set()
    for row in mapped_recs:
        all_keys.update(row.keys())
        
    try:
        from dynamic_fields_manager import register_dynamic_fields
        with db_conn() as conn:
            cur = conn.cursor()
            new_fields = register_dynamic_fields(cur, list(all_keys))
            conn.commit()
        # New headings are now queryable: drop the schema snapshot the NL
        # resolver caches per-process so this upload's columns are discoverable
        # without a restart.
        import intent_fields
        intent_fields.invalidate_cache()
    except Exception as e:
        print(f"Warning: Failed to register dynamic fields: {e}")

    # ── Phase 1.5: Provisional USNs for name-only (no-USN) rows ───────────────
    # Files that carry student names but no USN column would otherwise reject
    # every row. Assign a temporary VTU-format USN derived from the batch year
    # in the filename, serials allocated in ascending name order, then let the
    # normal validate → classify → upsert pipeline run unchanged.
    provisional_map: dict[str, str] = {}
    if parsed.get("file_type") not in ("pdf", "txt", "image"):
        try:
            with db_conn() as conn:
                cur = conn.cursor(dictionary=True)
                provisional_map = _assign_provisional_usns(cur, mapped_recs, filename)
                cur.close()
        except Exception as e:
            print(f"Warning: provisional USN assignment skipped: {e}")
    provisional_usns = set(provisional_map)

    # ── Phase 2: Validate every mapped row (no DB yet) ────────────────────────
    # A row whose USN is already on file is a supplement, not a new admission:
    # the identity is stored, so the sheet may carry only what it wants to add
    # (this semester's SGPA, a phone number, a blood group) without a name.
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
            mapped_recs, known_usns=existing_usns
        )

    sanitized_rows = []
    for row in mapped_recs:
        cleaned_row, _ = sanitize_row_fields(row)
        sanitized_rows.append(cleaned_row)

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

    for idx, row in enumerate(sanitized_rows, start=1):
        raw_usn  = _clean_str(row.get('usn'))
        raw_name = _clean_str(row.get('name'), 150)

        if idx in invalid_by_index:
            iv = invalid_by_index[idx]
            student_fatal = bool(iv.get('problematic_fields')) or any(
                'required field' in e.lower() or 'is invalid' in e.lower() for e in iv.get('errors', [])
                if 'sgpa' not in e.lower() and 'semester' not in e.lower()
            )
            if student_fatal or not (raw_usn and _valid_usn(raw_usn)):
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
            is_provisional = usn in provisional_usns
        elif raw_name:
            # A name-only row reached here only because no provisional USN could
            # be generated (the filename carried no '20YY' batch token). Do not
            # invent a placeholder USN — report exactly why and skip the row.
            classified.append({
                'row_index': idx, 'usn': None, 'name': raw_name, 'status': 'INVALID',
                'reason': "Missing USN; could not generate a temporary one because the "
                          "filename has no batch year (e.g. '2026 batch.xlsx').",
                'problematic_fields': ['usn'],
                'row': row,
            })
            continue
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
            'provisional': is_provisional,
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
    all_conflicts: list[dict] = []
    child_problems: list[str] = []
    import_id: int = 0

    try:
        with db_conn() as conn:
            conn.autocommit = False
            conn.start_transaction()
            cur = conn.cursor(dictionary=True)
            try:
                if affected_usns:
                    from routes_undo import create_undo_snapshot
                    undo_token = create_undo_snapshot(
                        "UPLOAD", affected_usns, current_user["username"],
                        f"Bulk upload: {filename}", conn=conn, filename=filename
                    )
                # Get the import_id from uploaded_files for provenance
                cur.execute("SELECT id FROM uploaded_files WHERE filename=%s", (filename,))
                row_id = cur.fetchone()
                import_id = row_id.get('id', 0) if row_id else 0

                usn_list = list(pending_students.keys())
                for chunk_start in range(0, len(usn_list), chunk_size):
                    chunk_usns = usn_list[chunk_start: chunk_start + chunk_size]
                    for usn in chunk_usns:
                        item = pending_students[usn]
                        result, conflicts = _upsert_student(
                            cur, usn, item['row'],
                            source_filename=filename, import_id=import_id,
                            provisional=item.get('provisional', False),
                        )
                        all_conflicts.extend(conflicts)
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
                        mr = _upsert_mark(
                            cur, m['usn'], m['semester'], m['sgpa'],
                            source_filename=filename, import_id=import_id,
                        )
                        if mr == 'added':
                            marks_added += 1
                        elif mr == 'updated':
                            marks_updated += 1
                        elif mr == 'unchanged':
                            marks_unchanged += 1
                        elif mr == 'rejected':
                            marks_rejected += 1

                # Fees and Backlogs — write for every successfully upserted student
                for usn, item in pending_students.items():
                    if usn not in usn_results:
                        continue
                    raw_row = item['row']
                    # Fees
                    _upsert_fees(cur, usn, raw_row, child_problems)
                    # Backlogs — stored in backlogs text column AND backlogs table
                    raw_backlog = _extract_backlog_text(raw_row)
                    if not _is_empty(raw_backlog):
                        _upsert_backlogs(cur, usn, str(raw_backlog), child_problems)

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
    if child_problems:
        msg += (f" {len(child_problems)} fee/backlog row(s) could not be stored "
                f"and are listed in child_record_problems.")
    if provisional_map:
        msg += (f" {len(provisional_map)} name-only row(s) were given temporary USNs "
                f"from batch {('20' + _batch_year_from_filename(filename)) if _batch_year_from_filename(filename) else '?'} "
                f"in ascending name order; each is flagged for later replacement with the "
                f"real college USN.")

    provisional_detail = [
        {"usn": usn, "name": name}
        for usn, name in sorted(provisional_map.items())
    ]

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
        "conflicts": all_conflicts[:50],
        "conflicts_count": len(all_conflicts),
        "child_record_problems": child_problems[:50],
        "provisional_usns": provisional_detail,
        "provisional_count": len(provisional_map),
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
        cur.execute("SELECT * FROM uploaded_files WHERE trashed_at IS NULL ORDER BY uploaded_at DESC")
        docs = cur.fetchall()
        cur.close()
    for d in docs:
        if d.get("uploaded_at"): d["uploaded_at"] = str(d["uploaded_at"])
        if d.get("db_status") == "pending" and d["filename"] not in _file_cache:
            disk_path = os.path.join(settings.upload_dir_abs, d["filename"])
            if not os.path.exists(disk_path):
                d["cache_expired"] = True
    return docs


@router.get("/trash")
def list_trashed_files(current_user: dict = Depends(require_roles("Admin"))):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        data_reconciled = _reconcile_trashed_file_records(cur, conn, current_user["username"])
        purged = _purge_expired_trash(cur)
        data_reconciled = _reconcile_orphaned_source_records(
            cur, purged, current_user["username"], conn) or data_reconciled
        if data_reconciled:
            _clear_cache(conn)
        cur.execute(
            "SELECT id, filename, file_type, size_bytes, uploaded_by, uploaded_at, db_status, "
            "row_count, students_saved, marks_saved, trashed_at, "
            "DATE_ADD(trashed_at, INTERVAL 30 DAY) AS restore_expires_at "
            "FROM uploaded_files WHERE trashed_at IS NOT NULL ORDER BY trashed_at DESC"
        )
        docs = cur.fetchall()
        conn.commit()
        cur.close()
    for doc in docs:
        for field in ("uploaded_at", "trashed_at", "restore_expires_at"):
            if doc.get(field):
                doc[field] = str(doc[field])
    return docs


@router.delete("/trash/permanent/{filename}")
def permanently_delete_trashed_file(filename: str, current_user: dict = Depends(require_roles("Admin"))):
    if current_user.get("role") != "Admin":
        raise HTTPException(403, "You are not allowed to permanently delete data. Administrator permission is required.")

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM uploaded_files WHERE filename=%s AND trashed_at IS NOT NULL", (filename,))
        file_row = cur.fetchone()
        if not file_row:
            raise HTTPException(404, "File was not found in Trash.")

        trash_path = _resolve_trash_path(file_row["trash_path"]) if file_row.get("trash_path") else None
        if trash_path and os.path.exists(trash_path):
            os.remove(trash_path)

        if file_row.get("trash_undo_token"):
            cur.execute("DELETE FROM global_undo_snapshots WHERE undo_token=%s", (file_row["trash_undo_token"],))

        cur.execute("DELETE FROM file_delete_provenance_snapshots WHERE source_filename=%s", (filename,))
        cur.execute("DELETE FROM uploaded_files WHERE filename=%s", (filename,))
        conn.commit()
        cur.close()

    _file_cache.pop(filename, None)
    write_audit_log(
        action="FILE_DELETE_PERMANENT",
        username=current_user["username"],
        role=current_user["role"],
        target_table="uploaded_files",
        target_id=filename,
        summary=f"Permanently deleted file '{filename}' from Trash. Recovery snapshot removed.",
    )
    return {"success": True, "filename": filename, "message": f"'{filename}' was permanently deleted from Trash."}


@router.post("/trash/restore/{filename}")
def restore_trashed_file(filename: str, current_user: dict = Depends(require_roles("Admin"))):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM uploaded_files WHERE filename=%s AND trashed_at IS NOT NULL", (filename,))
        file_row = cur.fetchone()
        cur.close()

    if not file_row:
        raise HTTPException(404, "File was not found in Trash.")
    if datetime.now() - file_row["trashed_at"] > timedelta(days=30):
        raise HTTPException(410, "The 30-day restore period has expired.")

    original_path = os.path.join(settings.upload_dir_abs, filename)
    trash_path = _resolve_trash_path(file_row["trash_path"]) if file_row.get("trash_path") else None
    moved_back = False
    if trash_path and os.path.exists(trash_path):
        if os.path.exists(original_path):
            raise HTTPException(409, "A file with this name already exists. Move it before restoring.")
        os.replace(trash_path, original_path)
        moved_back = True

    try:
        if file_row.get("trash_undo_token"):
            from routes_undo import restore_student
            result = restore_student(file_row["trash_undo_token"], current_user)
        else:
            if file_row.get("db_status") == "saved" and trash_path and moved_back:
                result = update_database(filename, current_user)
            else:
                result = {"success": True}
            with db_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE uploaded_files SET trashed_at=NULL, trash_path=NULL, trash_undo_token=NULL "
                    "WHERE filename=%s",
                    (filename,),
                )
                conn.commit()
                cur.close()
    except Exception:
        if moved_back and os.path.exists(original_path):
            os.makedirs(os.path.dirname(trash_path), exist_ok=True)
            os.replace(original_path, trash_path)
        raise

    _file_cache.pop(filename, None)
    write_audit_log(
        action="FILE_RESTORE", username=current_user["username"], role=current_user["role"],
        target_table="uploaded_files", target_id=filename,
        summary=f"File '{filename}' restored from Trash.",
    )
    return {"success": True, "filename": filename, **result}


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
def delete_file(filename: str, current_user: dict = Depends(require_roles("Admin"))):
    """
    Provenance-aware file deletion.

    1. Snapshot all provenance rows owned by this file into
       file_delete_provenance_snapshots (for undo).
    2. Find all student fields owned ONLY by this file (no other active source).
    3. NULL out those fields in the students table.
    4. Mark all provenance rows for this file as is_active=0.
    5. Delete the uploaded_files metadata row (snapshot it first for undo).
    6. Create an undo snapshot so the operation is reversible.
    7. Invalidate query cache.
    """
    # Collect what this file owns
    nulled_fields: list[dict] = []     # fields that will be cleared
    preserved_fields: list[dict] = []  # fields kept because another source exists
    affected_usns: set[str] = set()
    deleted_usns: set[str] = set()
    deleted_marks = 0

    undo_token = ""
    trash_rel_path = None
    moved_to_trash = None
    original_path = os.path.join(settings.upload_dir_abs, filename)
    try:
        with db_conn() as conn:
            conn.autocommit = False
            conn.start_transaction()
            cur = conn.cursor(dictionary=True)
            try:
                # ── 1. Find all provenance rows owned by this file ────────────
                cur.execute(
                    "SELECT usn, field_name, field_value, import_id "
                    "FROM student_field_sources "
                    "WHERE source_filename=%s AND is_active=1",
                    (filename,)
                )
                owned_rows = cur.fetchall()

                # Snapshot the uploaded_files row for undo restoration
                cur.execute(
                    "SELECT * FROM uploaded_files WHERE filename=%s",
                    (filename,)
                )
                uploaded_file_row = cur.fetchone()
                if not uploaded_file_row:
                    raise HTTPException(404, "Uploaded file was not found.")
                if uploaded_file_row.get("trashed_at"):
                    raise HTTPException(409, "File is already in Trash.")

                # Snapshot affected USNs BEFORE changes for undo
                for row in owned_rows:
                    affected_usns.add(row['usn'])

                # Legacy imports may have source_file ownership without per-field provenance.
                cur.execute("SELECT usn FROM students WHERE source_file=%s", (filename,))
                affected_usns.update(row['usn'] for row in cur.fetchall())

                if affected_usns:
                    from routes_undo import create_undo_snapshot
                    undo_token = create_undo_snapshot(
                        "FILE_DELETE", list(affected_usns),
                        current_user["username"],
                        f"File deletion: {filename}",
                        conn=conn
                    )

                # Remove whole student records created by this file only when
                # no other uploaded file still owns any active field on them.
                record_owned_usns = {
                    row['usn'] for row in owned_rows if row['field_name'] == '__record__'
                }
                for usn in affected_usns:
                    cur.execute(
                        "SELECT COUNT(*) AS source_count FROM student_field_sources "
                        "WHERE usn=%s AND source_filename<>%s AND is_active=1",
                        (usn, filename),
                    )
                    has_other_source = cur.fetchone()['source_count'] > 0
                    cur.execute("SELECT source_file FROM students WHERE usn=%s", (usn,))
                    student_row = cur.fetchone()
                    source_file_matches = student_row and student_row.get('source_file') == filename
                    if (usn in record_owned_usns or source_file_matches) and not has_other_source:
                        cur.execute("DELETE FROM marks WHERE usn=%s", (usn,))
                        deleted_marks += cur.rowcount
                        cur.execute("DELETE FROM student_fees WHERE usn=%s", (usn,))
                        cur.execute("DELETE FROM student_backlogs WHERE usn=%s", (usn,))
                        cur.execute("DELETE FROM students WHERE usn=%s", (usn,))
                        if cur.rowcount:
                            deleted_usns.add(usn)

                # ── 2. Snapshot provenance rows into file_delete_provenance_snapshots
                if undo_token and owned_rows:
                    prov_rows = [
                        (undo_token, filename, r['usn'], r['field_name'],
                         r['field_value'], r.get('import_id'))
                        for r in owned_rows
                    ]
                    cur.executemany(
                        """INSERT INTO file_delete_provenance_snapshots
                           (undo_token, source_filename, usn, field_name, field_value, import_id)
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        prov_rows
                    )

                # ── 3. Determine which fields have NO other active source ───────
                # Allowed columns (whitelist for safety)
                _SAFE_STUDENT_COLS = set(STUDENT_COLS)
                # Identity columns are NOT NULL in the schema; nulling them would
                # abort the whole deletion transaction. Always preserve them.
                # `name` is preserved for a second reason: a row that survives
                # because another file still owns a field must stay findable, so
                # the file that named it cannot leave it as a blank shell.
                _PROTECTED_COLS = {'usn', 'student_id', 'name'}

                _MARK_PROV_RE = re.compile(r'^mark_sem_(\d+)_sgpa$')

                for row in owned_rows:
                    usn = row['usn']
                    field = row['field_name']
                    old_val = row['field_value']

                    if usn in deleted_usns:
                        continue

                    mark_m = _MARK_PROV_RE.match(field)
                    if mark_m:
                        sem_num = int(mark_m.group(1))
                        other_source = _latest_active_source(cur, usn, field, filename)
                        if other_source:
                            try:
                                cur.execute(
                                    "UPDATE marks SET sgpa=%s WHERE usn=%s AND semester=%s",
                                    (other_source['field_value'], usn, sem_num),
                                )
                            except Exception:
                                pass
                            preserved_fields.append({'usn': usn, 'field': field})
                        else:
                            try:
                                cur.execute(
                                    "DELETE FROM marks WHERE usn=%s AND semester=%s",
                                    (usn, sem_num),
                                )
                                nulled_fields.append({
                                    'usn': usn, 'field': field, 'old_value': old_val,
                                    'semester': sem_num,
                                })
                            except Exception:
                                pass
                        continue

                    if field not in _SAFE_STUDENT_COLS:
                        continue  # Never touch unlisted columns

                    # Restore the newest remaining source, not the value owned by this file.
                    other_source = _latest_active_source(cur, usn, field, filename)
                    if other_source:
                        cur.execute(
                            f"UPDATE students SET `{field}`=%s WHERE usn=%s",
                            (other_source['field_value'], usn),
                        )
                        preserved_fields.append({'usn': usn, 'field': field})
                    elif field in _PROTECTED_COLS:
                        # The column cannot be blanked: it is either NOT NULL or the
                        # identity of a row this deletion deliberately keeps.
                        preserved_fields.append({'usn': usn, 'field': field})
                    else:
                        # Remove the deleted file's value.
                        safe_col = field  # Already validated against SAFE_STUDENT_COLS
                        cur.execute(
                            f"UPDATE students SET `{safe_col}`=NULL WHERE usn=%s",
                            (usn,),
                        )
                        nulled_fields.append({
                            'usn': usn, 'field': field, 'old_value': old_val
                        })

                # ── 4. Mark provenance rows as inactive ──────────────────
                cur.execute(
                    "UPDATE student_field_sources SET is_active=0 "
                    "WHERE source_filename=%s",
                    (filename,)
                )

                # ── 5. Move the upload into durable Trash storage ─────────
                disk_path = original_path
                if os.path.exists(disk_path):
                    moved_to_trash = _trash_path_for(filename)
                    os.replace(disk_path, moved_to_trash)
                    trash_rel_path = os.path.relpath(moved_to_trash, settings.upload_dir_abs)
                elif filename in _file_cache:
                    moved_to_trash = _trash_path_for(filename)
                    with open(moved_to_trash, "wb") as trash_file:
                        trash_file.write(_file_cache[filename])
                    trash_rel_path = os.path.relpath(moved_to_trash, settings.upload_dir_abs)

                cur.execute(
                    "UPDATE uploaded_files SET trashed_at=NOW(), trash_path=%s, trash_undo_token=%s, "
                    "data_reconciled_at=NOW() "
                    "WHERE filename=%s",
                    (trash_rel_path, undo_token or None, filename),
                )

                # ── 6. Store undo metadata with full context ──────────────────
                if undo_token:
                    import json as _json
                    cur.execute(
                        "SELECT snapshot_data FROM global_undo_snapshots WHERE undo_token=%s",
                        (undo_token,)
                    )
                    snap_row = cur.fetchone()
                    if snap_row:
                        snap_data = _json.loads(snap_row['snapshot_data'])
                        snap_data['file_delete_filename'] = filename
                        snap_data['nulled_fields'] = nulled_fields
                        snap_data['operation_subtype'] = 'FILE_DELETE'
                        # Store uploaded_files metadata for restoration on undo
                        if uploaded_file_row:
                            uf_clean = {k: str(v) if hasattr(v, 'isoformat') else v
                                        for k, v in uploaded_file_row.items()}
                            snap_data['uploaded_file_row'] = uf_clean
                        cur.execute(
                            "UPDATE global_undo_snapshots "
                            "SET snapshot_data=%s, operation_type='FILE_DELETE' "
                            "WHERE undo_token=%s",
                            (_json.dumps(snap_data), undo_token)
                        )
                    from routes_undo import finalize_undo_snapshot
                    finalize_undo_snapshot(undo_token, list(affected_usns), conn)

                # ── 7. Invalidate query cache ────────────────────────
                _clear_cache(conn)

                conn.commit()
                cur.close()

            except HTTPException:
                try: conn.rollback()
                except Exception: pass
                raise
            except Exception as db_err:
                try: conn.rollback()
                except Exception: pass
                raise HTTPException(500, "File deletion failed. No database changes were committed.")

    except HTTPException:
        if moved_to_trash and os.path.exists(moved_to_trash) and not os.path.exists(original_path):
            os.replace(moved_to_trash, original_path)
        raise
    except Exception as e:
        if moved_to_trash and os.path.exists(moved_to_trash) and not os.path.exists(original_path):
            os.replace(moved_to_trash, original_path)
        raise safe_http_error(500, e, "file deletion")

    _file_cache.pop(filename, None)

    write_audit_log(
        action="FILE_DELETE",
        username=current_user["username"],
        role=current_user["role"],
        target_table="uploaded_files",
        target_id=filename,
        summary=(
            f"File '{filename}' moved to Trash for 30 days. "
            f"Fields cleared: {len(nulled_fields)}, "
            f"Fields preserved (other sources): {len(preserved_fields)}, "
            f"Students affected: {len(affected_usns)}"
        ),
    )

    return {
        "success": True,
        "message": (
            f"File '{filename}' moved to Trash for 30 days. "
            f"Deleted {len(deleted_usns)} student record(s) and {deleted_marks} mark record(s); "
            f"cleared {len(nulled_fields)} file-owned field(s)."
        ),
        "filename": filename,
        "students_affected": len(affected_usns),
        "students_deleted": len(deleted_usns),
        "marks_deleted": deleted_marks,
        "fields_cleared": len(nulled_fields),
        "fields_preserved": len(preserved_fields),
        "nulled_fields": nulled_fields[:50],
        "undo_available": bool(undo_token),
        "undo_token": undo_token or None,
        "restore_expires_at": (datetime.now() + timedelta(days=30)).isoformat(),
    }


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
