"""
file_parser.py — Parses uploaded files into structured records.
Supports: CSV, XLSX, JSON, PDF, TXT, Images
Uses ai_column_mapper for column normalization.
"""
import io, re, json
import pandas as pd
from ai_column_mapper import map_columns, apply_mapping, extract_wide_semester_rows


def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(axis=1, how='all')
    df = df[[c for c in df.columns if str(c).strip().lower() not in ('nan', '', 'none')]]
    return df


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    df = _clean_df(df)
    for col in df.columns:
        try:
            df[col] = pd.to_numeric(df[col])
        except Exception:
            pass
    return df.where(pd.notnull(df), None).to_dict(orient='records')


def parse_csv(content: bytes) -> list[dict]:
    df = pd.read_csv(io.BytesIO(content))
    return _df_to_records(df)


def parse_xlsx(content: bytes) -> list[dict]:
    df = pd.read_excel(io.BytesIO(content))
    return _df_to_records(df)


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


def parse_file(filename: str, content: bytes) -> dict:
    """
    Main entry point.
    Returns:
    {
        "records": [...],       raw parsed rows (original columns)
        "mapped_records": [...] rows with canonical column names
        "gpa_data": [...],      long-format {usn, name, semester, sgpa, cgpa?}
        "students": [...],      unique student info rows
        "column_mapping": {},   raw→canonical mapping used
        "file_type": str,
        "row_count": int
    }
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
        return {"records": [], "mapped_records": [], "gpa_data": [],
                "students": [], "column_mapping": {}, "file_type": file_type, "row_count": 0}

    # Non-tabular files — return as-is
    if file_type in ('pdf', 'txt', 'image'):
        return {"records": records, "mapped_records": records, "gpa_data": [],
                "students": [], "column_mapping": {}, "file_type": file_type, "row_count": len(records)}

    # ── AI column mapping ────────────────────────────────────────────────────
    raw_cols = list(records[0].keys())
    col_mapping = map_columns(raw_cols)
    mapped_records = apply_mapping(records, col_mapping)

    # ── Try wide-format unpivot ──────────────────────────────────────────────
    gpa_data = extract_wide_semester_rows(records, col_mapping)

    if not gpa_data:
        # Try long-format: rows already have semester + sgpa columns
        gpa_data = _extract_long_format_gpa(mapped_records)

    # ── Build unique students list ───────────────────────────────────────────
    seen = {}
    for row in (gpa_data if gpa_data else mapped_records):
        usn  = str(row.get('usn', '') or '').strip()
        name = str(row.get('name', '') or '').strip()
        key  = usn or name
        if key and key not in seen:
            seen[key] = {k: v for k, v in row.items()
                         if k not in ('semester', 'sgpa', 'cgpa', 'year')}
    students = list(seen.values())

    return {
        "records": records,
        "mapped_records": mapped_records,
        "gpa_data": gpa_data,
        "students": students,
        "column_mapping": col_mapping,
        "file_type": file_type,
        "row_count": len(records),
    }


def _extract_long_format_gpa(mapped_records: list[dict]) -> list[dict]:
    """Extract rows that already have semester + sgpa in long format."""
    rows = []
    for rec in mapped_records:
        sem  = rec.get('semester')
        sgpa = rec.get('sgpa')
        usn  = str(rec.get('usn', '') or '').strip()
        name = str(rec.get('name', '') or '').strip()
        if not (usn or name):
            continue
        if sem is None or sgpa is None:
            continue
        try:
            row = {'usn': usn, 'name': name, 'semester': int(float(sem)),
                   'sgpa': round(float(sgpa), 2)}
            if rec.get('cgpa') is not None:
                row['cgpa'] = round(float(rec['cgpa']), 2)
            rows.append(row)
        except (ValueError, TypeError):
            continue
    return rows
