"""
canonical_fields.py — Central Canonical Field + Synonym Registry

ONE authoritative source of truth for field-name mapping across the
entire import pipeline. All other modules import from here.

Architecture (priority order):
  uploaded_column
    → normalize_header()
    → exact canonical match
    → exact synonym match
    → wide-format semester pattern
    → context-aware token rules  (whole-header, never bare "name" substring)
    → fuzzy match against registry (high threshold)
    → passthrough / ambiguous suggestion (never silent low-confidence guess)

Key rule:
  The COMPLETE header determines the field — NOT any single word inside it.
  "branch_name"  → branch       (NOT name)
  "father_name"  → father_name  (NOT name)
  "division_name"→ division     (NOT name)
  "domain_name"  → domain       (NOT name)
  "mother_name"  → mother_name  (NOT name)
"""

from __future__ import annotations

import re
from datetime import datetime
from difflib import SequenceMatcher

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: HEADER NORMALIZATION
# ─────────────────────────────────────────────────────────────────────────────

def normalize_header(raw: str) -> str:
    """
    Normalize a column header to lowercase-underscore form.
    Preserves all semantic tokens — does NOT strip context.

    Examples:
      "Branch Name"   → "branch_name"
      "STUDENT NAME"  → "student_name"
      "Father's Name" → "father_s_name"
      "  SGPA  "      → "sgpa"
    """
    s = str(raw).strip()
    s = re.sub(r'[^a-zA-Z0-9]+', '_', s)
    s = s.lower().strip('_')
    return s


def _is_empty(val) -> bool:
    if val is None:
        return True
    try:
        # pandas / numpy NaN
        if val != val:
            return True
    except Exception:
        pass
    s = str(val).strip()
    return s == '' or s.lower() in ('nan', 'none', 'null')


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: SYNONYM REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

SYNONYM_REGISTRY: dict[str, list[str]] = {

    "usn": [
        "usn", "student_usn", "student_usn_number",
        "university_seat_number", "university_seat_no",
        "register_number", "register_no",
        "registration_number", "registration_no",
        "student_registration_number",
        "roll_no", "roll_number",
        "reg_no", "reg_number",
        "enrollment_no", "enrollment_number",
        "student_id", "usno", "rno",
    ],

    "name": [
        "name", "student_name", "full_name", "student_full_name",
        "candidate_name", "first_name", "sname",
    ],

    "branch": [
        "branch", "branch_name", "department", "department_name",
        "dept", "dept_name", "stream", "stream_name",
        "program", "program_branch", "course",
        "branch_department", "programme", "engineering_branch",
    ],

    "division": [
        "division", "division_name", "section", "section_name",
        "class", "class_section", "division_section", "class_division",
    ],

    "domain": [
        "domain", "domain_name", "specialization", "specialization_name",
        "area_of_specialization", "specialization_domain",
        "elective_domain", "project_domain",
    ],

    "semester": [
        "semester", "sem", "semester_number", "semester_no",
        "sem_no", "current_semester", "current_sem",
    ],

    "sgpa": [
        "sgpa", "sem_gpa", "semester_gpa", "gpa",
        "grade_point", "grade_point_average",
        "semester_grade_point_average",
    ],

    "cgpa": [
        "cgpa", "cum_gpa", "cumulative_gpa", "cgpa_percent",
        "cumulative_grade_point_average",
    ],

    "father_name": [
        "father_name", "father", "fathers_name", "father_s_name",
        "parent_father_name",
    ],

    "mother_name": [
        "mother_name", "mother", "mothers_name", "mother_s_name",
        "parent_mother_name",
    ],

    "guardian_name": [
        "guardian_name", "guardian", "parent_name", "parent_guardian_name",
    ],

    "dob": [
        "dob", "date_of_birth", "birth_date", "birthdate",
        "date_of_birth_dob", "d_o_b",
    ],

    "year_of_joining": [
        "year_of_joining", "joining_year", "admission_year",
        "year_of_admission", "batch_year", "batch", "year_joined",
        "year_of_entry", "admission_batch",
    ],

    "blood_group": [
        "blood_group", "blood", "bloodgroup", "blood_type",
    ],

    "gender": ["gender", "sex"],

    "religion": ["religion", "faith"],

    "caste": ["caste", "caste_category", "caste_name"],

    "sub_caste": ["sub_caste", "sub_caste_category", "subcaste"],

    "category": [
        "category", "sub_category", "reservation_category",
        "social_category", "community",
    ],

    "address": [
        "address", "student_address", "residential_address",
    ],
    "permanent_address": [
        "permanent_address", "home_address", "native_address",
    ],
    "current_address": [
        "current_address", "local_address", "present_address", "hostel_address",
    ],

    "phone": [
        "phone", "phone_number", "mobile", "mobile_number", "mobile_no",
        "phone_no", "contact", "contact_number", "cell", "cell_number",
    ],

    "emergency_contact_number": [
        "emergency_contact_number", "emergency_contact", "emergency_contact_no",
        "emergency_contact_no", "emergency_phone", "emergency_phone_number",
        "emergency phone", "emergency phone number",
    ],

    "email": [
        "email", "email_id", "e_mail", "e_mail_id", "email_address",
        "student_email", "student_email_id", "student_e_mail_id",
        "mail", "mail_id",
    ],

    "aadhar_no": [
        "aadhar_no", "aadhar", "aadhaar", "aadhar_number", "aadhaar_number",
        "student_aadhar_no", "aadhar_card_no", "uid",
    ],

    "status": ["status", "student_status", "enrollment_status"],

    "current_year": [
        "current_year", "year", "academic_year", "study_year", "year_of_study",
    ],

    "year_and_branch": [
        "year_and_branch", "year_branch", "class_detail",
    ],

    "source_file": [
        "source_file", "file_name", "imported_from",
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: CONTEXT-AWARE RULES (whole-header token logic)
# Longer / more specific prefixes win. Bare "name" alone → student name.
# ─────────────────────────────────────────────────────────────────────────────

# (token_prefix_tuple, canonical) — checked against normalized header tokens
_CONTEXT_RULES: list[tuple[tuple[str, ...], str]] = [
    (('father',), 'father_name'),
    (('fathers',), 'father_name'),
    (('mother',), 'mother_name'),
    (('mothers',), 'mother_name'),
    (('guardian',), 'guardian_name'),
    (('branch',), 'branch'),
    (('department',), 'branch'),
    (('dept',), 'branch'),
    (('stream',), 'branch'),
    (('division',), 'division'),
    (('section',), 'division'),
    (('domain',), 'domain'),
    (('specialization',), 'domain'),
    (('student', 'name'), 'name'),
    (('full', 'name'), 'name'),
    (('candidate', 'name'), 'name'),
]


def _context_match(norm: str) -> str | None:
    """Match complete-header context. Never maps solely because 'name' is a substring."""
    tokens = [t for t in norm.split('_') if t]
    if not tokens:
        return None

    # Bare "name" only
    if tokens == ['name']:
        return 'name'

    # Prefer longest matching prefix rule
    best = None
    best_len = 0
    for prefix, canon in _CONTEXT_RULES:
        plen = len(prefix)
        if plen > best_len and tokens[:plen] == list(prefix):
            # "..._name" or exact prefix field
            if tokens == list(prefix) or (len(tokens) > plen and tokens[-1] == 'name') or tokens == list(prefix) + ['name']:
                best = canon
                best_len = plen
            elif tokens[:plen] == list(prefix) and plen >= 1 and prefix[0] in (
                'father', 'fathers', 'mother', 'mothers', 'guardian',
                'branch', 'department', 'dept', 'stream', 'division',
                'section', 'domain', 'specialization',
            ):
                # branch / father / etc. with any trailing tokens
                best = canon
                best_len = plen
    return best


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: REVERSE LOOKUP
# ─────────────────────────────────────────────────────────────────────────────

_REVERSE: dict[str, str] = {}
_CONFLICTS: list[str] = []
_ALL_SYNONYMS: list[tuple[str, str]] = []  # (synonym, canonical) for fuzzy

for _canon, _syns in SYNONYM_REGISTRY.items():
    # Skip ordinal aliases that are really wide-sem helpers stored as keys
    if re.match(r'^\d+(st|nd|rd|th)_sem_sgpa$', _canon):
        for _syn in _syns:
            # map to wide form via parse; store synonym → we'll resolve in map_column
            pass
        continue
    for _syn in _syns:
        if _syn in _REVERSE and _REVERSE[_syn] != _canon:
            _CONFLICTS.append(f"CONFLICT: '{_syn}' → both '{_REVERSE[_syn]}' and '{_canon}'")
        else:
            _REVERSE[_syn] = _canon
            _ALL_SYNONYMS.append((_syn, _canon))

# Ordinal semester SGPA aliases → wide canonical form (sem_N_sgpa)
for _n in range(1, 9):
    _ord = {1: '1st', 2: '2nd', 3: '3rd'}.get(_n, f'{_n}th')
    for _syn in (
        f'{_ord}_sem_sgpa', f'{_ord}_semester_sgpa',
        f'{_ord}_sem_gpa', f'semester_{_n}_sgpa',
    ):
        if _syn not in _REVERSE:
            _REVERSE[_syn] = f'sem_{_n}_sgpa'
            _ALL_SYNONYMS.append((_syn, f'sem_{_n}_sgpa'))

if _CONFLICTS:
    import warnings
    for _c in _CONFLICTS:
        warnings.warn(_c, stacklevel=2)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: WIDE-FORMAT SEMESTER PATTERN
# ─────────────────────────────────────────────────────────────────────────────

_WIDE_A = re.compile(
    r'^(\d+)(?:st|nd|rd|th)?[_\s]*sem(?:ester)?[_\s]*(?P<m>cgpa|sgpa|gpa)$',
    re.IGNORECASE,
)
_WIDE_B = re.compile(
    r'^(?P<m>cgpa|sgpa|gpa)[_\s]*sem(?:ester)?[_\s]*(\d+)$',
    re.IGNORECASE,
)
_WIDE_C = re.compile(
    r'^sem(?:ester)?[_\s]*(\d+)[_\s]*(?P<m>cgpa|sgpa|gpa)$',
    re.IGNORECASE,
)
_WIDE_D = re.compile(
    r'^sem[_\s]*(\d+)[_\s]*(?P<m>cgpa|sgpa|gpa)$',
    re.IGNORECASE,
)


def parse_wide_sem_col(norm: str):
    """Return (sem_num, metric) for wide-format columns, else None."""
    for pat in (_WIDE_A, _WIDE_B, _WIDE_C, _WIDE_D):
        m = pat.match(norm)
        if m:
            grps = m.groups()
            num = next((g for g in grps if g and g.isdigit()), None)
            metric_raw = m.group('m').lower()
            metric = 'sgpa' if metric_raw in ('sgpa', 'gpa') else 'cgpa'
            if num:
                return int(num), metric
    return None


_FUZZY_THRESHOLD = 0.88


def _fuzzy_match(norm: str) -> tuple[str | None, float, list[dict]]:
    """
    Fuzzy match against all known synonyms.
    Returns (best_canonical_or_None, confidence, alternatives).
    Only auto-accepts when uniquely above threshold.
    """
    scored: dict[str, float] = {}
    for syn, canon in _ALL_SYNONYMS:
        ratio = SequenceMatcher(None, norm, syn).ratio()
        if ratio >= _FUZZY_THRESHOLD - 0.05:
            scored[canon] = max(scored.get(canon, 0.0), ratio)

    if not scored:
        return None, 0.0, []

    ranked = sorted(scored.items(), key=lambda x: -x[1])
    alternatives = [
        {'canonical': c, 'confidence': round(s, 3), 'reason': 'fuzzy synonym match'}
        for c, s in ranked[:5]
    ]
    best_c, best_s = ranked[0]
    # Ambiguous if top two are close
    if len(ranked) > 1 and (best_s - ranked[1][1]) < 0.05 and ranked[1][1] >= _FUZZY_THRESHOLD - 0.05:
        return None, best_s, alternatives
    if best_s >= _FUZZY_THRESHOLD:
        return best_c, best_s, alternatives
    return None, best_s, alternatives


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6: PUBLIC MAPPING API
# ─────────────────────────────────────────────────────────────────────────────

def map_column(raw: str) -> tuple[str, str, float, list[dict]]:
    """
    Map one raw header → canonical field.

    Returns (canonical, mapping_type, confidence, suggestions)
    mapping_type: exact|synonym|wide_sem|context|fuzzy|passthrough|ambiguous
    """
    norm = normalize_header(raw)

    # 1. Wide-format semester pattern (before synonym so sgpa_sem3 ≠ semester)
    wide = parse_wide_sem_col(norm)
    if wide:
        sem_num, metric = wide
        return f'sem_{sem_num}_{metric}', 'wide_sem', 1.0, []

    # 2. Exact reverse lookup (canonical + synonyms)
    if norm in _REVERSE:
        return _REVERSE[norm], 'synonym', 1.0, []

    # 3. Context-aware whole-header rules
    ctx = _context_match(norm)
    if ctx:
        return ctx, 'context', 0.95, []

    # 4. Fuzzy fallback
    fuzzy_c, fuzzy_s, alts = _fuzzy_match(norm)
    if fuzzy_c:
        return fuzzy_c, 'fuzzy', fuzzy_s, alts
    if alts:
        return norm, 'ambiguous', fuzzy_s, alts

    # 5. Passthrough — do not silently guess
    return norm, 'passthrough', 0.0, []


def map_columns(raw_columns: list[str]) -> dict[str, str]:
    """Map all raw headers once. Returns {raw_col: canonical_col}."""
    return {col: map_column(col)[0] for col in raw_columns}


def map_columns_detailed(raw_columns: list[str]) -> dict:
    """
    Full mapping report for UI / confirmation flows.
    """
    mapping = {}
    details = []
    ambiguous = []
    for col in raw_columns:
        canon, mtype, conf, suggestions = map_column(col)
        mapping[col] = canon
        entry = {
            'uploaded_column': col,
            'canonical_field': canon,
            'mapping_type': mtype,
            'confidence': conf,
            'suggestions': suggestions,
        }
        details.append(entry)
        if mtype == 'ambiguous':
            ambiguous.append(entry)
    return {
        'mapping': mapping,
        'details': details,
        'ambiguous': ambiguous,
        'needs_confirmation': len(ambiguous) > 0,
    }


def apply_mapping(records: list[dict], mapping: dict[str, str]) -> list[dict]:
    """
    Rename keys to canonical fields.

    CRITICAL: when multiple source columns map to the same canonical field,
    NEVER overwrite a non-empty value with an empty/None/NaN value.
    First non-empty value wins (column order preserved).
    """
    result = []
    for rec in records:
        new_rec: dict = {}
        for k, v in rec.items():
            canonical = mapping.get(k, normalize_header(k))
            if canonical not in new_rec:
                new_rec[canonical] = v
            elif _is_empty(new_rec[canonical]) and not _is_empty(v):
                new_rec[canonical] = v
            # else keep existing non-empty
        result.append(new_rec)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7: FORMAT DETECTION + UNPIVOT
# ─────────────────────────────────────────────────────────────────────────────

def detect_file_format(col_mapping: dict[str, str]) -> str:
    canonical_values = set(col_mapping.values())
    has_long = 'semester' in canonical_values and 'sgpa' in canonical_values
    has_wide = any(re.match(r'sem_\d+_(sgpa|cgpa)$', v) for v in canonical_values)
    if has_long and has_wide:
        return 'mixed'
    if has_wide:
        return 'wide'
    return 'long'


def extract_marks_from_row(mapped_row: dict) -> list[dict]:
    """
    Extract all (semester, sgpa[, cgpa]) mark tuples from one mapped row.
    Handles long-format (semester+sgpa) and wide-format (sem_N_sgpa) together.
    """
    marks: dict[int, dict] = {}

    # Wide columns
    for k, v in mapped_row.items():
        m = re.match(r'^sem_(\d+)_(sgpa|cgpa)$', str(k))
        if not m or _is_empty(v):
            continue
        sem_num = int(m.group(1))
        metric = m.group(2)
        try:
            fval = round(float(v), 2)
            if fval != fval:  # NaN
                continue
        except (ValueError, TypeError):
            continue
        marks.setdefault(sem_num, {'semester': sem_num})[metric] = fval

    # Long-format columns
    sem = mapped_row.get('semester')
    sgpa = mapped_row.get('sgpa')
    cgpa = mapped_row.get('cgpa')
    if not _is_empty(sem):
        try:
            sem_num = int(float(sem))
        except (ValueError, TypeError):
            sem_num = None
        if sem_num is not None:
            entry = marks.setdefault(sem_num, {'semester': sem_num})
            if not _is_empty(sgpa):
                try:
                    f = round(float(sgpa), 2)
                    if f == f:
                        entry['sgpa'] = f
                except (ValueError, TypeError):
                    pass
            if not _is_empty(cgpa):
                try:
                    f = round(float(cgpa), 2)
                    if f == f:
                        entry.setdefault('cgpa', f)
                except (ValueError, TypeError):
                    pass

    return [marks[s] for s in sorted(marks) if 'sgpa' in marks[s] or 'cgpa' in marks[s]]


def extract_wide_semester_rows(
    records: list[dict], col_mapping: dict[str, str]
) -> list[dict]:
    """Unpivot wide-format semester columns into long-format mark rows."""
    mapped = apply_mapping(records, col_mapping)
    rows = []
    for rec in mapped:
        usn = str(rec.get('usn', '') or '').strip() if not _is_empty(rec.get('usn')) else ''
        name = str(rec.get('name', '') or '').strip() if not _is_empty(rec.get('name')) else ''
        if not usn and not name:
            continue
        for mark in extract_marks_from_row(rec):
            row = {'usn': usn, 'name': name, **mark}
            # carry personal fields
            for k, v in rec.items():
                if k not in row and not re.match(r'^sem_\d+_(sgpa|cgpa)$', str(k)):
                    if k not in ('semester', 'sgpa', 'cgpa'):
                        row[k] = v
            rows.append(row)
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8: VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

REQUIRED_FIELDS = {'usn', 'name'}

# The import accepts the project's alphanumeric USN forms while rejecting
# placeholders such as INVALID001 and malformed identifiers before any DB work.
_USN_VALUE_RE = re.compile(r'^[0-9][A-Za-z0-9/-]{7,99}$')
_EMAIL_VALUE_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
_VALID_BRANCHES = {
    'CSE', 'CS', 'ISE', 'IT', 'ECE', 'EC', 'EEE', 'EE', 'ME', 'MECH',
    'CIVIL', 'CE', 'AIML', 'AI', 'AIDS', 'CSD', 'CSBS', 'IOT', 'ROBOTICS',
    'CHEMICAL', 'CH', 'ARCH', 'MBA', 'MCA',
    'COMPUTER SCIENCE AND ENGINEERING', 'INFORMATION SCIENCE AND ENGINEERING',
    'ELECTRONICS AND COMMUNICATION ENGINEERING', 'ELECTRICAL AND ELECTRONICS ENGINEERING',
    'MECHANICAL ENGINEERING', 'CIVIL ENGINEERING',
    'ARTIFICIAL INTELLIGENCE AND MACHINE LEARNING',
    'ARTIFICIAL INTELLIGENCE AND DATA SCIENCE',
    'COMPUTER SCIENCE AND DESIGN', 'COMPUTER SCIENCE AND BUSINESS SYSTEMS',
}

_FIELD_LABELS = {
    'usn': 'USN (Student ID)',
    'name': 'Student Name',
}


def validate_mapped_rows(
    mapped_records: list[dict], *, allow_academic_only_usns: set[str] | None = None
) -> dict:
    """
    Per-row required-field validation. Does not mutate input.
    Invalid rows are returned with reasons — caller decides policy.
    """
    valid, invalid, errors = [], [], []
    allow_academic_only_usns = allow_academic_only_usns or set()

    for idx, row in enumerate(mapped_records, start=1):
        row_errors = []
        available_cols = list(row.keys())
        row_usn = '' if _is_empty(row.get('usn')) else str(row.get('usn')).strip()
        has_academic_data = (
            not _is_empty(row.get('sgpa'))
            or any(
                re.fullmatch(r'sem_\d+_(sgpa|cgpa)', str(field)) and not _is_empty(value)
                for field, value in row.items()
            )
        )
        for field in REQUIRED_FIELDS:
            if (
                field == 'name'
                and row_usn in allow_academic_only_usns
                and has_academic_data
            ):
                continue
            val = row.get(field)
            if _is_empty(val):
                label = _FIELD_LABELS.get(field, field)
                row_errors.append(
                    f"Row {idx}: Required field '{label}' is missing or empty. "
                    f"Available columns: {available_cols}."
                )

        usn = row.get('usn')
        if not _is_empty(usn) and not _USN_VALUE_RE.fullmatch(str(usn).strip()):
            row_errors.append(f"Row {idx}: USN {str(usn).strip()!r} is invalid.")

        email = row.get('email')
        if not _is_empty(email) and not _EMAIL_VALUE_RE.fullmatch(str(email).strip()):
            row_errors.append(f"Row {idx}: Email {str(email).strip()!r} is invalid.")

        branch = row.get('branch')
        if not _is_empty(branch) and str(branch).strip().upper() not in _VALID_BRANCHES:
            row_errors.append(f"Row {idx}: Branch {str(branch).strip()!r} is invalid.")

        for field in ('year_of_joining', 'admission_year'):
            value = row.get(field)
            if _is_empty(value):
                continue
            try:
                year = int(float(value))
                if year < 2000 or year > datetime.now().year + 1:
                    raise ValueError
            except (TypeError, ValueError):
                row_errors.append(f"Row {idx}: {field.replace('_', ' ').title()} {value!r} is invalid.")

        # A long-format SGPA always needs its semester. Wide columns carry the
        # semester in their key, so validate each populated value directly.
        semester = row.get('semester')
        sgpa = row.get('sgpa')
        if not _is_empty(sgpa) and _is_empty(semester):
            row_errors.append(f"Row {idx}: Semester is required when SGPA is provided.")
        if not _is_empty(semester):
            try:
                semester_number = int(float(semester))
                if semester_number < 1 or semester_number > 12:
                    raise ValueError
            except (TypeError, ValueError):
                row_errors.append(f"Row {idx}: Semester {semester!r} is invalid; expected 1-12.")

        if not _is_empty(sgpa):
            error = validate_sgpa_value(sgpa)
            if error:
                row_errors.append(f"Row {idx}: {error}.")
        for field, value in row.items():
            if re.fullmatch(r'sem_\d+_sgpa', str(field)) and not _is_empty(value):
                error = validate_sgpa_value(value)
                if error:
                    row_errors.append(f"Row {idx}: {field} {error}.")
        if row_errors:
            invalid.append({
                'row_index': idx,
                'row': row,
                'errors': row_errors,
                'usn': None if _is_empty(row.get('usn')) else str(row.get('usn')).strip(),
                'name': None if _is_empty(row.get('name')) else str(row.get('name')).strip(),
                'problematic_fields': [
                    f for f in REQUIRED_FIELDS if _is_empty(row.get(f))
                ],
            })
            errors.extend(row_errors)
        else:
            valid.append(row)

    return {'valid': valid, 'invalid': invalid, 'errors': errors}


def validate_sgpa_value(sgpa) -> str | None:
    """Return error message if SGPA invalid, else None."""
    if _is_empty(sgpa):
        return None
    try:
        f = float(sgpa)
        if f != f:
            return 'SGPA is not a number'
        if f < 0 or f > 10:
            return f'SGPA {f} out of range (0-10)'
    except (ValueError, TypeError):
        return f'SGPA value {sgpa!r} is not numeric'
    return None
