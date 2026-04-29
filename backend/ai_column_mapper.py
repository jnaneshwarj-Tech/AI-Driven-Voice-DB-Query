"""
ai_column_mapper.py
Normalizes raw CSV/Excel column names to canonical DB column names.
Uses rule-based mapping first; falls back to LLM for unknown columns.
"""
import re

# ── Rule-based canonical mapping ─────────────────────────────────────────────
COLUMN_MAP = {
    # USN / Student ID
    "usn": "usn", "student_id": "usn", "roll_no": "usn",
    "roll_number": "usn", "reg_no": "usn", "registration_no": "usn",
    "enrollment_no": "usn", "id": "usn",

    # Name
    "name": "name", "student_name": "name", "full_name": "name",
    "first_name": "name", "sname": "name",

    # Semester
    "semester": "semester", "sem": "semester", "sno": "semester",
    "sl_no": "semester", "s_no": "semester",

    # SGPA
    "sgpa": "sgpa", "sem_gpa": "sgpa", "semester_gpa": "sgpa",
    "gpa": "sgpa", "grade_point": "sgpa",

    # CGPA (will be ignored for storage — computed dynamically)
    "cgpa": "cgpa", "cum_gpa": "cgpa", "cumulative_gpa": "cgpa",
    "cgpa_percent": "cgpa", "cgpa_%": "cgpa",

    # Personal
    "dob": "dob", "date_of_birth": "dob", "birth_date": "dob",
    "year_of_joining": "year_of_joining", "joining_year": "year_of_joining",
    "admission_year": "year_of_joining",
    "father_name": "father_name", "fathers_name": "father_name",
    "mother_name": "mother_name", "mothers_name": "mother_name",
    "blood_group": "blood_group", "blood": "blood_group",
    "address": "address", "addr": "address",
    "status": "status",
    "current_sem": "current_sem", "current_semester": "current_sem",
    "year": "year",
}

# Wide-format semester CGPA/SGPA pattern: "1st sem cgpa", "2nd sem sgpa", etc.
_SEM_WIDE = re.compile(
    r'(\d+)(?:st|nd|rd|th)?[_\s]*sem(?:ester)?[_\s]*(?P<metric>cgpa|sgpa|gpa)',
    re.IGNORECASE
)


def normalize_col(raw: str) -> str:
    """Lowercase + underscores."""
    return re.sub(r'[^a-z0-9]+', '_', raw.strip().lower()).strip('_')


def map_columns(raw_columns: list[str]) -> dict[str, str]:
    """
    Returns {raw_col: canonical_col}.
    Wide-format semester columns → 'sem_<N>_sgpa' / 'sem_<N>_cgpa'.
    Unknown columns are kept as-is (normalized).
    """
    mapping = {}
    for col in raw_columns:
        norm = normalize_col(col)

        # Check wide-format first
        m = _SEM_WIDE.search(norm)
        if m:
            sem_num = m.group(1)
            metric = m.group('metric').lower()
            if metric == 'gpa':
                metric = 'sgpa'
            mapping[col] = f"sem_{sem_num}_{metric}"
            continue

        # Rule-based lookup
        if norm in COLUMN_MAP:
            mapping[col] = COLUMN_MAP[norm]
            continue

        # Partial match
        matched = None
        for key, val in COLUMN_MAP.items():
            if key in norm or norm in key:
                matched = val
                break
        mapping[col] = matched if matched else norm

    return mapping


def apply_mapping(records: list[dict], mapping: dict[str, str]) -> list[dict]:
    """Rename keys in each record according to mapping."""
    result = []
    for rec in records:
        new_rec = {}
        for k, v in rec.items():
            canonical = mapping.get(k, normalize_col(k))
            new_rec[canonical] = v
        result.append(new_rec)
    return result


def extract_wide_semester_rows(records: list[dict], mapping: dict[str, str]) -> list[dict]:
    """
    If wide-format semester columns exist (sem_1_sgpa, sem_2_sgpa, ...),
    unpivot them into long-format rows: {usn, name, semester, sgpa}.
    Returns [] if no wide-format columns found.
    """
    sem_cols = {}  # canonical_col -> (semester_num, metric)
    for raw, canonical in mapping.items():
        m = re.match(r'sem_(\d+)_(sgpa|cgpa)', canonical)
        if m:
            sem_cols[canonical] = (int(m.group(1)), m.group(2))

    if not sem_cols:
        return []

    rows = []
    for rec in records:
        # Apply mapping first
        mapped = {mapping.get(k, normalize_col(k)): v for k, v in rec.items()}
        usn  = str(mapped.get('usn', '') or '').strip()
        name = str(mapped.get('name', '') or '').strip()
        if not usn and not name:
            continue

        # Group by semester
        sem_data: dict[int, dict] = {}
        for col, (sem_num, metric) in sem_cols.items():
            val = mapped.get(col)
            if val is None or str(val).strip() in ('', 'nan', 'None', '0', '0.0'):
                continue
            try:
                fval = round(float(val), 2)
            except (ValueError, TypeError):
                continue
            if sem_num not in sem_data:
                sem_data[sem_num] = {'usn': usn, 'name': name, 'semester': sem_num}
            sem_data[sem_num][metric] = fval

        for sem_num in sorted(sem_data):
            rows.append(sem_data[sem_num])

    return rows
