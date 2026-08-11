"""
file_parser.py — Parses uploaded files into structured records.
Supports: CSV, XLSX, JSON, PDF, TXT, Images

Key rules:
  - Column mapping is performed ONCE per file header, applied to all rows.
  - apply_mapping never lets empty synonym columns wipe real values.
  - Every parsed data row is retained in mapped_records.
  - gpa_data is derived mark rows (long + wide), not a replacement for students.
"""
import io, re, json
import pandas as pd
from canonical_fields import (
    normalize_header,
    map_columns,
    map_columns_detailed,
    apply_mapping,
    detect_file_format,
    extract_marks_from_row,
    _is_empty,
)

_USN_HEADERS = {
    'usn', 'student_id', 'student_usn', 'roll_no', 'roll_number',
    'reg_no', 'registration_no', 'enrollment_no', 'register_no',
    'register_number',
}
_NAME_HEADERS = {
    'name', 'student_name', 'full_name', 'first_name', 'student_full_name',
    'candidate_name',
}
_GPA_PATTERN = re.compile(r'(sgpa|cgpa|gpa|sem.*gpa|gpa.*sem)', re.IGNORECASE)


def _normalize_header_check(h) -> str:
    return re.sub(r'[^a-z0-9]+', '_', str(h).strip().lower()).strip('_')


def _is_real_header_row(row_values: list) -> bool:
    normalized = [
        _normalize_header_check(v)
        for v in row_values
        if str(v).strip() not in ('', 'nan', 'None')
    ]
    if not normalized:
        return False
    has_usn  = any(n in _USN_HEADERS  for n in normalized)
    has_name = any(n in _NAME_HEADERS for n in normalized)
    has_gpa  = any(_GPA_PATTERN.search(n) for n in normalized)
    return has_usn or has_name or has_gpa


def _find_header_row(df_raw: pd.DataFrame) -> int:
    for i in range(min(20, len(df_raw))):
        row_vals = [str(v) for v in df_raw.iloc[i].values]
        if _is_real_header_row(row_vals):
            return i
    return 0


def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(axis=1, how='all')
    df = df[[
        c for c in df.columns
        if str(c).strip().lower() not in ('nan', '', 'none', 'unnamed')
        and not str(c).startswith('Unnamed')
    ]]
    return df


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    df = _clean_df(df)
    df = df.dropna(how='all')
    header_set = {str(c).strip().lower() for c in df.columns}

    def _is_header_repeat(row):
        vals = [str(v).strip().lower() for v in row.values if str(v).strip() not in ('', 'nan')]
        return len(vals) > 0 and all(v in header_set for v in vals)

    df = df[~df.apply(_is_header_repeat, axis=1)]
    for col in df.columns:
        try:
            df[col] = pd.to_numeric(df[col])
        except Exception:
            pass
    return df.where(pd.notnull(df), None).to_dict(orient='records')


def _tabular_records_with_headers(df_raw: pd.DataFrame) -> list[dict]:
    """Read a sheet/CSV with either one header row or a semester + metric header.

    Academic exports commonly use two rows such as ``1ST SEM`` then ``SGPA``.
    Joining those cells before canonical mapping turns them into the existing
    ``1st_sem_sgpa`` wide-column format without changing normal one-row files.
    """
    header_row = _find_header_row(df_raw)
    headers = list(df_raw.iloc[header_row].values)
    data_start = header_row + 1

    if data_start < len(df_raw):
        subheaders = list(df_raw.iloc[data_start].values)
        metric_cells = sum(
            1 for value in subheaders
            if _normalize_header_check(value) in {'sgpa', 'cgpa', 'gpa'}
        )
        if metric_cells:
            combined = []
            for parent, child in zip(headers, subheaders):
                parent_text = '' if pd.isna(parent) else str(parent).strip()
                child_text = '' if pd.isna(child) else str(child).strip()
                combined.append(f'{parent_text}_{child_text}' if parent_text and child_text else parent_text or child_text)
            headers = combined
            data_start += 1

    df = df_raw.iloc[data_start:].copy()
    df.columns = headers
    return _df_to_records(df)


def parse_csv(content: bytes) -> list[dict]:
    df_raw = pd.read_csv(io.BytesIO(content), header=None)
    return _tabular_records_with_headers(df_raw)


def parse_xlsx(content: bytes) -> list[dict]:
    xl = pd.ExcelFile(io.BytesIO(content))
    all_records = []

    for sheet_name in xl.sheet_names:
        try:
            df_raw = pd.read_excel(xl, sheet_name=sheet_name, header=None)
            if df_raw.empty:
                continue
            records = _tabular_records_with_headers(df_raw)

            filtered = []
            for rec in records:
                usn_val = None
                for k, v in rec.items():
                    if _normalize_header_check(k) in _USN_HEADERS:
                        usn_val = str(v).strip() if v is not None else ''
                        break
                non_null = [
                    v for v in rec.values()
                    if v is not None and str(v).strip() not in ('', 'nan', 'None')
                ]
                if len(non_null) < 2:
                    continue
                if usn_val and len(usn_val) > 25:
                    continue
                filtered.append(rec)

            all_records.extend(filtered)
        except Exception:
            continue

    return all_records


def parse_json_file(content: bytes) -> list[dict]:
    data = json.loads(content.decode('utf-8', errors='ignore'))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


def parse_pdf(content: bytes) -> list[dict]:
    try:
        import fitz
        doc = fitz.open(stream=content, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        return [{"type": "text", "content": text.strip()}]
    except Exception as e:
        raise ValueError(f"PDF parse error: {e}")


def parse_txt(content: bytes) -> list[dict]:
    text = content.decode("utf-8", errors="ignore").strip()
    return [{"type": "text", "content": text}]


def parse_image(content: bytes) -> list[dict]:
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(io.BytesIO(content))
        text = pytesseract.image_to_string(img).strip()
        return [{"type": "ocr_text", "content": text}]
    except Exception as e:
        return [{"type": "ocr_text", "content": f"OCR unavailable: {e}"}]


def _build_gpa_data(mapped_records: list[dict]) -> list[dict]:
    """
    Build long-format mark rows from EVERY mapped student row.
    Uses both semester+sgpa and wide sem_N_sgpa columns.
    """
    rows = []
    for rec in mapped_records:
        usn = '' if _is_empty(rec.get('usn')) else str(rec.get('usn')).strip()
        name = '' if _is_empty(rec.get('name')) else str(rec.get('name')).strip()
        if not usn and not name:
            continue
        for mark in extract_marks_from_row(rec):
            row = {'usn': usn, 'name': name, **mark}
            for k, v in rec.items():
                if k in row:
                    continue
                if k in ('semester', 'sgpa', 'cgpa') or re.match(r'^sem_\d+_(sgpa|cgpa)$', str(k)):
                    continue
                row[k] = v
            rows.append(row)
    return rows


def parse_file(filename: str, content: bytes) -> dict:
    """
    Main entry point.

    mapped_records — ONE entry per parsed source row (authoritative for import accounting)
    gpa_data       — expanded mark rows derived from mapped_records
    students       — unique students by USN/name from mapped_records
    """
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

    if ext == 'csv':
        records = parse_csv(content)
        file_type = 'csv'
    elif ext in ('xlsx', 'xls'):
        records = parse_xlsx(content)
        file_type = 'xlsx'
    elif ext == 'json':
        records = parse_json_file(content)
        file_type = 'json'
    elif ext == 'pdf':
        records = parse_pdf(content)
        file_type = 'pdf'
    elif ext == 'txt':
        records = parse_txt(content)
        file_type = 'txt'
    elif ext in ('png', 'jpg', 'jpeg', 'bmp', 'tiff', 'webp'):
        records = parse_image(content)
        file_type = 'image'
    else:
        raise ValueError(f"Unsupported file type: .{ext}")

    if not records:
        return {
            "records": [], "mapped_records": [], "gpa_data": [],
            "students": [], "column_mapping": {}, "mapping_details": {},
            "file_type": file_type, "row_count": 0, "format_type": "unknown",
        }

    if file_type in ('pdf', 'txt', 'image'):
        return {
            "records": records, "mapped_records": records, "gpa_data": [],
            "students": [], "column_mapping": {}, "mapping_details": {},
            "file_type": file_type, "row_count": len(records), "format_type": "text",
        }

    # Column mapping — ONCE for the entire file
    raw_cols = list(records[0].keys())
    mapping_report = map_columns_detailed(raw_cols)
    col_mapping = mapping_report['mapping']
    mapped_records = apply_mapping(records, col_mapping)

    fmt = detect_file_format(col_mapping)
    gpa_data = _build_gpa_data(mapped_records)
    if not gpa_data and fmt != 'wide':
        # May still be personal-data-only
        has_any_marks_cols = any(
            v in ('semester', 'sgpa', 'cgpa') or re.match(r'^sem_\d+_(sgpa|cgpa)$', v)
            for v in col_mapping.values()
        )
        if not has_any_marks_cols:
            fmt = 'personal_only'

    # Unique students from mapped_records (not from gpa_data)
    seen_students: dict[str, dict] = {}
    for row in mapped_records:
        usn  = '' if _is_empty(row.get('usn')) else str(row.get('usn')).strip()
        name = '' if _is_empty(row.get('name')) else str(row.get('name')).strip()
        key  = usn if usn else name
        if not key:
            continue
        if key not in seen_students:
            seen_students[key] = {
                k: v for k, v in row.items()
                if k not in ('semester', 'sgpa', 'cgpa')
                and not re.match(r'^sem_\d+_(sgpa|cgpa)$', str(k))
            }

    return {
        "records":         records,
        "mapped_records":  mapped_records,
        "gpa_data":        gpa_data,
        "students":        list(seen_students.values()),
        "column_mapping":  col_mapping,
        "mapping_details": mapping_report,
        "file_type":       file_type,
        "row_count":       len(records),
        "format_type":     fmt,
    }
