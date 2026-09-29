"""
routes_query.py — AI query engine.
Features:
  - Query cache, cumulative CGPA, NLP synonyms, fuzzy search fallback.
  - Conditional extraction: "personal" → personal only, "academic" → marks only.
  - Multiple same-name students → ambiguity selection, never auto-merge.
"""
import json, time, re, logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from database import db_conn, write_audit_log
from auth import get_current_user
from rag_sql_generator import generate_sql_query
from query_security_validator import validate_sql_query
from fuzzy_search import smart_fallback, get_student_data, get_student_profile, extract_search_term, fuzzy_search_students
from error_messages import safe_http_error
from canonical_fields import map_column, normalize_header, parse_wide_sem_col
from kannada_processor import (
    normalize_query as kn_normalize_query,
    is_complete_profile_intent,
    detect_language as kn_detect_language,
    get_response_labels,
)

router = APIRouter(prefix="/api/query", tags=["Query Engine"])
logger = logging.getLogger(__name__)
_CACHE_VERSION = "selected-columns-v5-address-location-current-sem:"

def _normalize_usn(raw: str) -> str:
    return re.sub(r'[^A-Za-z0-9]', '', str(raw) or '').upper()


def _is_probable_usn(raw: str) -> bool:
    normalized = _normalize_usn(raw)
    return bool(re.fullmatch(r'[A-Z0-9]{4,}', normalized)) and any(ch.isdigit() for ch in normalized)


def _load_table_columns(conn, table: str) -> dict[str, str]:
    cur = conn.cursor(dictionary=True)
    cur.execute(f"SHOW COLUMNS FROM `{table}`")
    rows = cur.fetchall()
    cur.close()
    return {row['Field']: row['Type'] for row in rows}


def _create_column_if_missing(cur, conn, table: str, column: str, data_type: str) -> None:
    cur.execute(f"SHOW COLUMNS FROM `{table}` LIKE %s", (column,))
    if cur.fetchone():
        return
    cur.execute(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {data_type}")
    cur.execute(
        "INSERT IGNORE INTO schema_metadata (table_name, column_name, data_type) VALUES (%s,%s,%s)",
        (table, column, data_type),
    )
    print(f"UPDATE PIPELINE: created column {table}.{column} {data_type}")


def _safe_column_name(raw_field: str) -> str:
    candidate = normalize_header(raw_field)
    if not candidate:
        raise ValueError("Field not found.")
    if not re.fullmatch(r'[a-z_][a-z0-9_]*', candidate):
        candidate = re.sub(r'[^a-z0-9_]', '_', candidate)
        if not candidate[0].isalpha():
            candidate = f'fld_{candidate}'
    reserved = {
        'select', 'insert', 'update', 'delete', 'from', 'where', 'and', 'or',
        'join', 'table', 'schema', 'index', 'order', 'group', 'by', 'into',
        'values', 'set', 'column', 'columns', 'limit', 'offset', 'desc',
        'asc', 'union', 'drop', 'create', 'alter', 'primary', 'key', 'foreign',
        'constraint', 'references', 'database', 'procedure', 'function'
    }
    if candidate in reserved:
        candidate = f'fld_{candidate}'
    return candidate


def _split_value_and_rest(text: str) -> tuple[str, str | None]:
    text = text.strip()
    idx = 0
    while True:
        match = re.search(r'\s+and\s+', text[idx:], re.I)
        if not match:
            return text.strip(), None
        start = idx + match.start()
        suffix = text[start + match.end() - match.start():]
        if re.search(r'\bto\b', suffix, re.I):
            return text[:start].strip(), suffix.strip()
        idx = start + 1


def _extract_target_and_field(left: str) -> tuple[str, str]:
    words = left.strip().split()
    if not words or len(words) < 2:
        raise HTTPException(400, "Please specify the information to update.")

    best_match = None
    for count in range(1, len(words)):
        candidate_field = ' '.join(words[-count:]).strip()
        target_text = ' '.join(words[:-count]).strip()
        if not target_text:
            continue

        canonical, _, confidence, _ = map_column(candidate_field)
        if not canonical:
            continue

        if confidence >= 0.8 or confidence == 0.0:
            score = (confidence, count)
            if best_match is None or score > best_match[0]:
                best_match = (score, target_text, candidate_field)

    if best_match:
        return best_match[1], best_match[2]

    raise HTTPException(400, "Field not found.")


def _match_update_field_prefix(text: str) -> tuple[str, str] | None:
    """Recognize a field at the start of a subsequent update segment."""
    candidate_text = re.sub(r'^\s*to\s+', '', text.strip(), flags=re.I)
    words = candidate_text.split()
    best_match = None
    for count in range(1, len(words) + 1):
        if words[count - 1].lower() == 'to':
            break
        field_text = ' '.join(words[:count])
        canonical, _, confidence, _ = map_column(field_text)
        if not canonical or normalize_header(field_text) == 'all_information':
            continue
        if confidence >= 0.8 or confidence == 0.0:
            value_start = count
            if value_start < len(words) and words[value_start].lower() == 'to':
                value_start += 1
            candidate = (
                confidence,
                count,
                field_text,
                ' '.join(words[value_start:]).strip(),
            )
            if best_match is None or candidate[:2] > best_match[:2]:
                best_match = candidate
    if best_match:
        return best_match[2], best_match[3]
    return None


def _split_next_update_boundary(text: str) -> tuple[str, str, str] | None:
    """Split value text when comma/and is followed by another known field."""
    quote = None
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if quote:
            if char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char in {'"', "'"}:
            quote = char
            index += 1
            continue

        separator = re.match(r',|\s+and\s+', text[index:], re.I)
        if not separator:
            index += 1
            continue

        field_match = _match_update_field_prefix(text[index + separator.end():])
        if field_match:
            field_text, field_value = field_match
            return text[:index].strip(), field_text, field_value
        index += separator.end()
    return None


def _strip_update_value_quotes(value: str, field: str) -> str:
    value = value.strip()
    if value.startswith(('"', "'")):
        quote = value[0]
        if len(value) < 2 or value[-1] != quote:
            raise HTTPException(400, f"Unclosed quoted value for {field}.")
        value = value[1:-1]
        value = re.sub(r'\\([\\"\'])', r'\1', value)
    return value


def _parse_update_assignments(natural_query: str) -> dict:
    match = re.match(r'^\s*update\s+(.+)$', natural_query, re.I)
    if not match:
        return None
    payload = match.group(1).strip()
    first_to = re.search(r'\bto\b', payload, re.I)
    if not first_to:
        raise HTTPException(400, "Please specify the information to update.")

    left = payload[:first_to.start()].strip()
    remainder = payload[first_to.end():].strip()

    target, first_field = _extract_target_and_field(left)
    if normalize_header(first_field) == 'all_information':
        raise HTTPException(400, "Please specify the information to update.")

    assignments = []
    current_value_text = remainder
    current_field = first_field
    while True:
        boundary = _split_next_update_boundary(current_value_text)
        if boundary:
            value, next_field, next_value_text = boundary
            if not value:
                raise HTTPException(400, f"Invalid value for {current_field}.")
            assignments.append({
                'field_text': current_field,
                'value_text': _strip_update_value_quotes(value, current_field),
            })
            current_field = next_field
            current_value_text = next_value_text
            continue

        value = current_value_text.strip()
        if not value:
            raise HTTPException(400, f"Invalid value for {current_field}.")
        assignments.append({
            'field_text': current_field,
            'value_text': _strip_update_value_quotes(value, current_field),
        })
        break

    return {
        'target_text': target,
        'assignments': assignments,
    }


def _match_student(target_text: str) -> dict:
    normalized_target = target_text.strip()
    if not normalized_target:
        raise HTTPException(400, "Please specify the student to update.")

    if _is_probable_usn(normalized_target):
        normalized_usn = _normalize_usn(normalized_target)
        with db_conn() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT * FROM students WHERE UPPER(REPLACE(REPLACE(REPLACE(usn,' ',''),'-',''),'.',''))=%s",
                (normalized_usn,),
            )
            student = cur.fetchone()
            cur.close()
        if not student:
            raise HTTPException(404, f"No student found for USN {normalized_usn}.")
        return {'type': 'USN', 'student': student}

    normalized_name = re.sub(r'[^A-Za-z0-9]', '', normalized_target).lower()
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM students WHERE LOWER(REPLACE(REPLACE(REPLACE(name,' ',''),'-',''),'.',''))=%s",
            (normalized_name,),
        )
        exact_matches = cur.fetchall()
        cur.close()

    if len(exact_matches) == 1:
        return {'type': 'NAME', 'student': exact_matches[0]}
    if len(exact_matches) > 1:
        suggestions = [{
            'usn': s['usn'],
            'name': s['name'],
            'score': 1.0,
        } for s in exact_matches]
        return {'type': 'NAME', 'ambiguous': suggestions}

    fuzzy_matches = fuzzy_search_students(normalized_target, limit=8, min_score=0.70)
    if not fuzzy_matches:
        raise HTTPException(404, "No student found.")
    if len(fuzzy_matches) == 1:
        return {'type': 'NAME', 'student': fuzzy_matches[0]}

    top_score = fuzzy_matches[0]['score']
    if top_score >= 0.90 and len(fuzzy_matches) >= 1 and fuzzy_matches[0]['score'] - fuzzy_matches[1]['score'] >= 0.15:
        return {'type': 'NAME', 'student': fuzzy_matches[0]}

    suggestions = fuzzy_matches
    return {'type': 'NAME', 'ambiguous': suggestions}


def _resolve_assignment(conn, student: dict, assignment: dict) -> dict:
    raw_field = assignment['field_text']
    raw_value = assignment['value_text']
    canonical, mapping_type, confidence, _ = map_column(raw_field)
    canonical_norm = normalize_header(raw_field)
    if canonical == 'usn':
        raise HTTPException(400, "Field not found.")

    table_columns = {
        'students': _load_table_columns(conn, 'students'),
        'marks': _load_table_columns(conn, 'marks'),
    }

    def _choose_table() -> str:
        if canonical.startswith('sem_') or canonical in {'sgpa', 'cgpa'}:
            return 'marks'
        if 'mark' in canonical_norm or 'marks' in canonical_norm:
            return 'marks'
        if canonical in table_columns['marks']:
            return 'marks'
        if canonical in table_columns['students']:
            return 'students'
        if mapping_type == 'synonym' and canonical in {'year', 'semester'}:
            return 'marks'
        return 'students'

    table = _choose_table()
    if table == 'marks' and canonical.startswith('sem_'):
        sem_match = parse_wide_sem_col(canonical)
        if not sem_match:
            raise HTTPException(400, f"Invalid academic field: {raw_field}.")
        semester, metric = sem_match
        column = metric
    else:
        column = canonical

    if column not in table_columns[table]:
        raise HTTPException(400, f"Field '{raw_field}' is not available in the database.")

    if column in {'usn', 'student_id'} and table == 'students':
        raise HTTPException(400, "Field not found.")

    current_semester = None
    if table == 'marks':
        sem = None
        if canonical.startswith('sem_'):
            sem_match = parse_wide_sem_col(canonical)
            sem = sem_match[0] if sem_match else None
        else:
            if student.get('current_sem') is not None:
                sem = student['current_sem']
            else:
                with conn.cursor(dictionary=True) as cur:
                    cur.execute("SELECT semester FROM marks WHERE usn=%s ORDER BY semester DESC LIMIT 1", (student['usn'],))
                    row = cur.fetchone()
                sem = row['semester'] if row else 1
        current_semester = int(sem or 1)

    validated_value = _validate_value(
        column, raw_value, table, table_columns[table].get(column), raw_field
    )
    return {
        'table': table,
        'column': column,
        'value': validated_value,
        'raw_field': raw_field,
        'canonical_field': column,
        'semester': current_semester,
        'create_if_missing': False,
        'data_type': _choose_data_type(column, raw_field, validated_value, table),
    }


def _choose_data_type(column: str, raw_field: str, value, table: str) -> str:
    if column == 'blood_group' or 'blood' in raw_field.lower():
        return 'VARCHAR(5)'
    if column == 'email' or 'email' in raw_field.lower():
        return 'VARCHAR(255)'
    if column in {'phone', 'mobile', 'contact_number'} or 'phone' in raw_field.lower() or 'mobile' in raw_field.lower():
        return 'VARCHAR(30)'
    if 'address' in raw_field.lower() or column.endswith('_address'):
        return 'TEXT'
    if column == 'dob' or 'date_of_birth' in raw_field.lower() or 'dob' in raw_field.lower():
        return 'DATE'
    if column in {'admission_year', 'current_year', 'year_of_joining', 'year'} or 'year' in raw_field.lower():
        return 'INT'
    if 'sgpa' in column or 'cgpa' in column or column.endswith('_sgpa') or column.endswith('_cgpa'):
        return 'DECIMAL(4,2)'
    if 'mark' in raw_field.lower() or column.endswith('_marks'):
        if isinstance(value, float) and not float(value).is_integer():
            return 'DECIMAL(5,2)'
        return 'INT'
    if table == 'marks' and isinstance(value, (int, float)):
        return 'DECIMAL(6,2)' if isinstance(value, float) else 'INT'
    return 'VARCHAR(255)'


def _validate_value(
    column: str,
    raw_value: str,
    table: str,
    existing_type: str | None,
    raw_field: str = '',
):
    value_text = str(raw_value).strip()
    if not value_text:
        raise HTTPException(400, f"Invalid value for {column}.")
    if column == 'blood_group':
        normalized = value_text.upper().replace(' ', '')
        if not re.fullmatch(r'^(A|B|AB|O)[+-]$', normalized):
            raise HTTPException(400, f"Invalid value for blood group.")
        return normalized
    if column == 'email':
        if not re.fullmatch(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', value_text):
            raise HTTPException(400, "Invalid value for email.")
        return value_text
    if column == 'phone' or 'phone' in column or 'mobile' in column or 'contact' in column:
        digits = re.sub(r'[^0-9]', '', value_text)
        if len(digits) < 7 or len(digits) > 20:
            raise HTTPException(400, "Invalid value for phone number.")
        return value_text
    if column in {'admission_year', 'current_year', 'year_of_joining', 'year'} or re.search(r'\byear\b', column):
        try:
            y = int(float(value_text))
        except Exception:
            raise HTTPException(400, f"Invalid value for {column}.")
        if y < 1900 or y > 2099:
            raise HTTPException(400, f"Invalid value for {column}.")
        return y
    if 'sgpa' in column or 'cgpa' in column or column.endswith('_sgpa') or column.endswith('_cgpa'):
        try:
            value = float(value_text)
        except Exception:
            raise HTTPException(400, f"Invalid value for {column}.")
        if value < 0 or value > 10:
            raise HTTPException(400, f"Invalid value for {column}.")
        return round(value, 2)
    if 'mark' in column or 'marks' in column or re.search(r'\bmarks?\b', raw_field, re.I):
        try:
            value = float(value_text)
        except Exception:
            raise HTTPException(400, f"Invalid value for {column}.")
        if value < 0 or value > 100:
            raise HTTPException(400, f"Invalid value for {column}.")
        if value.is_integer():
            return int(value)
        return round(value, 2)
    if column == 'dob' or 'date_of_birth' in column or 'dob' in column:
        for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d'):
            try:
                return datetime.strptime(value_text, fmt).date().isoformat()
            except Exception:
                pass
        raise HTTPException(400, "Invalid date format for dob. Use YYYY-MM-DD or DD-MM-YYYY.")
    if existing_type:
        if existing_type.startswith('int'):
            try:
                return int(float(value_text))
            except Exception:
                raise HTTPException(400, f"Invalid value for {column}.")
        if existing_type.startswith('decimal'):
            try:
                return round(float(value_text), 2)
            except Exception:
                raise HTTPException(400, f"Invalid value for {column}.")
        if existing_type.startswith('date'):
            for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d'):
                try:
                    return datetime.strptime(value_text, fmt).date().isoformat()
                except Exception:
                    pass
            raise HTTPException(400, "Invalid date format.")
    return value_text


def _build_update_request(nq: str) -> dict | None:
    parsed = _parse_update_assignments(nq)
    if not parsed:
        return None

    student_match = _match_student(parsed['target_text'])
    if student_match.get('ambiguous'):
        return {
            'action_required': 'select_student',
            'suggestions': student_match['ambiguous'],
            'message': 'Multiple students found.',
        }

    student = student_match['student']
    with db_conn() as conn:
        executions = []
        column_creations = []
        grouped = {}
        for assignment in parsed['assignments']:
            resolved = _resolve_assignment(conn, student, assignment)
            table = resolved['table']
            sem = resolved.get('semester')
            key = (table, sem) if table == 'marks' else (table, None)
            grouped.setdefault(key, []).append(resolved)
            if resolved['create_if_missing']:
                column_creations.append({
                    'table': table,
                    'column': resolved['column'],
                    'data_type': resolved['data_type'],
                })

        for (table, sem), resolved_items in grouped.items():
            if table == 'students':
                cols = [r['column'] for r in resolved_items]
                placeholders = ', '.join([f'`{c}`=%s' for c in cols])
                params = [r['value'] for r in resolved_items] + [student['usn']]
                executions.append({
                    'sql': f"UPDATE students SET {placeholders} WHERE usn=%s",
                    'params': params,
                })
            else:
                cols = [r['column'] for r in resolved_items]
                place_holders = ', '.join(['%s'] * (2 + len(cols)))
                updates = ', '.join([f'`{c}`=%s' for c in cols])
                params = [student['usn'], sem] + [r['value'] for r in resolved_items] + [r['value'] for r in resolved_items]
                executions.append({
                    'sql': f"INSERT INTO marks (usn, semester, {', '.join('`'+c+'`' for c in cols)}) VALUES ({place_holders}) "
                           f"ON DUPLICATE KEY UPDATE {updates}",
                    'params': params,
                })

    logger.debug("Prepared student update with %d field(s).", len(parsed['assignments']))

    return {
        'operation': 'update',
        'executions': executions,
        'column_creations': column_creations,
        'affected_usns': [student['usn']],
        'student_usn': student['usn'],
        'student_name': student.get('name'),
        'original_query': nq,
    }


class QueryRequest(BaseModel):
    natural_query: str
    language: str = 'english'  # 'english', 'kannada', or 'mixed'
    response_language: str = 'english'  # Response language preference

class ExecuteRequest(BaseModel):
    query_dict: dict
    original_query: str


def _validate_structured_update(query_dict: dict) -> str | None:
    affected_usns = query_dict.get('affected_usns')
    if not isinstance(affected_usns, list) or len(affected_usns) != 1:
        return "Update must target exactly one student."
    usn = affected_usns[0]
    if not isinstance(usn, str) or not usn.strip() or len(usn) > 100:
        return "Update target is invalid."

    executions = query_dict.get('executions')
    if not isinstance(executions, list) or not executions or len(executions) > 2:
        return "Update statements are invalid."

    for execution in executions:
        if not isinstance(execution, dict):
            return "Update statement is invalid."
        sql = execution.get('sql')
        params = execution.get('params')
        if not isinstance(sql, str) or not isinstance(params, (list, tuple)):
            return "Update statement is invalid."

        student_match = re.fullmatch(
            r"UPDATE students SET ((?:`[a-z][a-z0-9_]*`=%s)(?:, `?[a-z][a-z0-9_]*`?=%s)*) WHERE usn=%s",
            sql,
            re.I,
        )
        if student_match:
            columns = re.findall(r"`?([a-z][a-z0-9_]*)`?=%s", student_match.group(1), re.I)
            if len(params) != len(columns) + 1 or params[-1] != usn:
                return "Update values do not match the selected student."
            if any(column.lower() in {'usn', 'student_id'} for column in columns):
                return "Student identifiers cannot be changed."
            table = 'students'
        else:
            marks_match = re.fullmatch(
                r"INSERT INTO marks \(usn, semester, (`[a-z][a-z0-9_]*`(?:, `[a-z][a-z0-9_]*`)*)\) "
                r"VALUES \(%s(?:, %s)+\) ON DUPLICATE KEY UPDATE "
                r"(`[a-z][a-z0-9_]*`=%s(?:, `[a-z][a-z0-9_]*`=%s)*)",
                sql,
                re.I,
            )
            if not marks_match:
                return "Update statement is invalid."
            columns = re.findall(r"`([a-z][a-z0-9_]*)`", marks_match.group(1), re.I)
            update_columns = re.findall(r"`([a-z][a-z0-9_]*)`=%s", marks_match.group(2), re.I)
            value_count = len(columns)
            if columns != update_columns or len(params) != 2 + (2 * value_count):
                return "Academic update values are invalid."
            if params[0] != usn or params[1] is None:
                return "Academic update target is invalid."
            if params[2 : 2 + value_count] != params[2 + value_count :]:
                return "Academic update values do not match."
            table = 'marks'

    creations = query_dict.get('column_creations', [])
    if not isinstance(creations, list) or creations:
        return "Dynamic column definitions are invalid."
    return None


# ── Serialiser ────────────────────────────────────────────────────────────────

def _serialize_row(row: dict) -> dict:
    clean = {}
    for k, v in row.items():
        if v is None:
            clean[k] = None
        elif hasattr(v, 'isoformat'):
            clean[k] = v.isoformat()
        else:
            try:
                clean[k] = float(v) if hasattr(v, '__float__') and not isinstance(v, (int, float, str, bool)) else v
            except Exception:
                clean[k] = v
    return clean


# ── Query runner ──────────────────────────────────────────────────────────────

def _run_query(query_dict: dict) -> list:
    op  = query_dict.get("operation", "").lower()
    sql = query_dict.get("sql", "")
    if not sql:
        raise ValueError("Missing SQL.")
    with db_conn() as conn:
        if op == "select":
            cur = conn.cursor(dictionary=True)
            cur.execute(sql, query_dict.get("params", []))
            rows = [_serialize_row(r) for r in cur.fetchall()]
            cur.close()
            return rows
        else:
            cur = conn.cursor()
            cur.execute(sql)
            conn.commit()
            affected = cur.rowcount
            cur.close()
            return [{"affected_rows": affected}]


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _get_cache(natural_query: str):
    try:
        with db_conn() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT sql_query, result_json FROM query_cache WHERE user_query=%s",
                (f"{_CACHE_VERSION}{natural_query}"[:255],)
            )
            row = cur.fetchone()
            cur.close()
        if row and row.get("result_json"):
            return row["sql_query"], json.loads(row["result_json"])
    except Exception:
        pass
    return None, None


def _set_cache(natural_query: str, sql: str, result: list):
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO query_cache (user_query, sql_query, result_json) VALUES (%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE sql_query=%s, result_json=%s, created_at=NOW()",
                (f"{_CACHE_VERSION}{natural_query}"[:255], sql, json.dumps(result, default=str),
                 sql, json.dumps(result, default=str))
            )
            conn.commit()
            cur.close()
    except Exception:
        pass


def _clear_cache():
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM query_cache")
            conn.commit()
            cur.close()
    except Exception:
        pass


def _log_history(role: str, natural: str, sql: str, elapsed: float):
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO query_history (user_role, natural_query, generated_query, execution_time) "
                "VALUES (%s,%s,%s,%s)",
                (role, natural, sql, elapsed)
            )
            conn.commit()
            cur.close()
    except Exception:
        pass


# ── Query intent detection ────────────────────────────────────────────────────

_PERSONAL_KEYWORDS = re.compile(
    r'\b(personal|father|mother|dob|birth|blood|address|village|district|state|phone|email|aadhar|gender|religion|caste|family)\b',
    re.IGNORECASE
)
_ACADEMIC_KEYWORDS = re.compile(
    r'\b(academic|mark|marks|gpa|sgpa|cgpa|semester|sem|result|grade|performance|score)\b',
    re.IGNORECASE
)

_PERSONAL_FIELDS = {
    "usn", "name", "dob", "father_name", "mother_name", "blood_group",
    "gender", "religion", "caste", "sub_caste", "category", "address",
    "village", "district", "state", "region",
    "permanent_address", "current_address", "phone", "emergency_contact_number", "email", "aadhar_no",
    "year_and_branch", "year_of_joining", "status",
    "admission_year", "current_year", "student_type", "estimated_semester",
    "graduation_year", "graduation_status"
}
_ACADEMIC_FIELDS = {"usn", "name", "semester", "sgpa", "cgpa", "year"}


_COMPLETE_PROFILE_RE = re.compile(
    r'\b('
    r'everything\s+about'
    r'|complete\s+information'
    r'|full\s+information'
    r'|complete\s+details'
    r'|full\s+details'
    r'|entire\s+profile'
    r'|all\s+information'
    r'|all\s+about'
    r'|all\s+details'
    r'|tell\s+me\s+everything'
    r'|show\s+everything'
    r'|give\s+me\s+everything'
    r'|full\s+profile'
    r'|complete\s+profile'
    r'|student\s+profile'
    r'|both\s+academic'
    r'|both\s+personal'
    r'|both\s+details'
    r'|academic\s+and\s+personal'
    r'|personal\s+and\s+academic'
    r'|both\s+academic\s+and\s+personal'
    r'|both\s+personal\s+and\s+academic'
    r')\b',
    re.IGNORECASE
)


def _detect_intent(nq: str) -> str:
    """Returns 'personal', 'academic', 'complete_profile', 'scalar_number', 'girls_names', or 'full'."""
    if re.search(r'\b(?:how\s+many|count|number\s+of)\b.*\b(?:rural|urban)\b', nq, re.I):
        return 'scalar_number'
    if re.search(r'\bhow\s+many\s+students\b|\bcount\b.*\bcgpa\b|\bnumber\s+of\s+students\b', nq, re.I):
        return 'scalar_number'
    if re.search(r'\brural\b', nq, re.I):
        return 'rural_search'
    if re.search(r'\burban\b', nq, re.I):
        return 'urban_search'
    if re.search(r'\b(?:students?|student records?)\b.*\b(?:from|in|at|near)\b', nq, re.I):
        return 'location_search'
    if re.search(r'\b(?:give|show|list|get)?\s*only\s*(?:girls?|female|women)\s*names?\b|\b(?:girls?|female)\s*names?\s*only\b|\bgirls?\s*names?\b', nq, re.I):
        return 'girls_names'
    # Check complete profile first (Kannada + English)
    if is_complete_profile_intent(nq) or _COMPLETE_PROFILE_RE.search(nq):
        return 'complete_profile'
    has_personal = bool(_PERSONAL_KEYWORDS.search(nq))
    has_academic = bool(_ACADEMIC_KEYWORDS.search(nq))
    if has_personal and not has_academic:
        return 'personal'
    if has_academic and not has_personal:
        return 'academic'
    return 'full'



def _split_select_items(select_text: str) -> list[str]:
    """Split a SELECT list without splitting commas inside expressions."""
    items, start, depth = [], 0, 0
    for index, char in enumerate(select_text):
        if char == '(':
            depth += 1
        elif char == ')':
            depth = max(0, depth - 1)
        elif char == ',' and depth == 0:
            items.append(select_text[start:index].strip())
            start = index + 1
    items.append(select_text[start:].strip())
    return [item for item in items if item]


def _enforce_specific_select(nq: str, query_dict: dict) -> dict:
    """Keep narrow personal requests narrow even if the LLM adds identity fields."""
    if query_dict.get('operation', '').lower() != 'select':
        return query_dict
    if _COMPLETE_PROFILE_RE.search(nq) or is_complete_profile_intent(nq):
        return query_dict

    field_patterns = [
        (r'\b(?:student\s+)?name\b', 'name'),
        (r'\bphone\s*(?:number|no)?\b|\bmobile\b|\bcontact\s+number\b', 'phone'),
        (r'\bemail\b|\bmail\b', 'email'),
        (r'\baddress\b', 'address'),
        (r'\bfather\s+name\b|\bdad(?:dy)?\s+name\b', 'father_name'),
        (r'\bmother\s+name\b|\bmom(?:my)?\s+name\b', 'mother_name'),
    ]
    requested = [column for pattern, column in field_patterns if re.search(pattern, nq, re.I)]
    if not requested:
        return query_dict

    sql = query_dict.get('sql', '')
    match = re.match(r'(?is)^\s*SELECT\s+(.*?)\s+FROM\s+', sql)
    if not match:
        return query_dict

    items = _split_select_items(match.group(1))
    selected = []
    for column in requested:
        column_match = next(
            (item for item in items if re.search(rf'(?i)(?:\b\w+\.)?`?{re.escape(column)}`?(?:\s+AS\s+\w+)?\s*$', item)),
            None,
        )
        selected.append(column_match or f's.{column}')

    query_dict = dict(query_dict)
    query_dict['sql'] = f"SELECT {', '.join(selected)} FROM {sql[match.end():]}"
    return query_dict


def _filter_by_intent(rows: list[dict], intent: str, natural_query: str | None = None) -> list[dict]:
    """Preserve SQL-selected columns, including aliases."""
    if intent == 'girls_names' or (natural_query and re.search(r'\b(?:give|show|list|get|display)?\s*only\s*(?:girls?|female)\s*names?\b', natural_query, re.I)):
        return [{'name': r.get('name')} for r in rows if r.get('name')]

    if intent == 'personal' and natural_query:
        requested = set()
        for pattern, column in (
            (r'\b(?:usn|student\s+number)\b', 'usn'),
            (r'\b(?:student\s+)?name\b', 'name'),
            (r'\bphone\s*(?:number|no)?\b|\bmobile\b|\bcontact\s+number\b', 'phone'),
            (r'\bemail\b|\bmail\b', 'email'),
            (r'\baddress\b', 'address'),
            (r'\bvillage\b', 'village'),
            (r'\bdistrict\b', 'district'),
            (r'\bstate\b', 'state'),
            (r'\bregion\b', 'region'),
            (r'\bfather(?:[\'’]s)?\s+name\b|\bdad(?:dy)?(?:[\'’]s)?\s+name\b', 'father_name'),
            (r'\bmother(?:[\'’]s)?\s+name\b|\bmom(?:my)?(?:[\'’]s)?\s+name\b', 'mother_name'),
            (r'\bblood\s+group\b', 'blood_group'),
            (r'\b(?:date\s+of\s+birth|dob|birth\s+date)\b', 'dob'),
            (r'\bage\b', 'age'),
        ):
            match = re.search(pattern, natural_query, re.I)
            if column == 'name' and match and re.search(
                r"\b(?:father|mother|dad|mom)(?:['’]s)?\s+$",
                natural_query[:match.start()],
                re.I,
            ):
                continue
            if match:
                requested.add(column)
        if requested:
            return [{k: v for k, v in row.items() if k in requested} for row in rows]
    return rows


def _apply_dynamic_student_fields(rows: list[dict]) -> list[dict]:
    """Replace persisted semester metadata with the current value derived from each USN."""
    from graduation_manager import parse_usn_full

    enriched = []
    for row in rows:
        updated = dict(row)
        updated.pop('estimated_semester', None)
        usn = updated.get('usn')
        calculated = parse_usn_full(usn) if usn else None
        if not calculated:
            enriched.append(updated)
            continue
        for key in (
            'student_type', 'admission_batch', 'current_year', 'current_sem',
            'graduation_year', 'graduation_status',
        ):
            if key in updated or key == 'current_sem':
                updated[key] = calculated[key]
        enriched.append(updated)
    return enriched



# ── Multi-student ambiguity detection ─────────────────────────────────────────

def _build_full_profile_row(usn: str) -> list[dict]:
    """Merge personal profile + academic rows + graduation data into enriched list."""
    from graduation_manager import parse_usn_full
    profile = get_student_profile(usn) or {}
    academic = get_student_data(usn) or []
    # Enrich profile with graduation data
    usn_data = parse_usn_full(usn)
    if usn_data:
        for key in ('student_type', 'admission_batch', 'current_year', 'current_sem',
                    'graduation_year', 'graduation_status'):
            if key not in profile or profile.get(key) is None:
                profile[key] = usn_data.get(key)
    if academic:
        return _apply_dynamic_student_fields([{**profile, **row} for row in academic])
    # Personal-only student (no marks yet)
    return _apply_dynamic_student_fields([profile]) if profile else []


def _check_ambiguity(data: list[dict], nq: str) -> dict | None:
    """
    If SQL returns multiple DISTINCT students by USN, and they share
    a similar name → return an ambiguity suggestion so user can choose.
    Returns None if no ambiguity (single student or genuinely different query).
    """
    if not data:
        return None

    if re.search(r'\brural\b|\burban\b|\b(?:students?|student records?)\b.*\b(?:from|in|at|near)\b', nq, re.I):
        return None

    # Collect unique USNs in result
    usns = list(dict.fromkeys(r.get("usn", "") for r in data if r.get("usn")))
    if len(usns) <= 1:
        return None  # only one student — no ambiguity

    # Check: are all results for a single name-like search (not a bulk query)?
    term = extract_search_term(nq)
    if not term:
        return None

    # If the query is a bulk-type query (all students, top N, etc.) → no ambiguity
    bulk_patterns = re.compile(
        r'\b(all|every|list|top\s+\d+|show\s+all|display\s+all|compare|semester\s+\d|girls?|female|cgpa|how\s+many|count|village)\b',
        re.IGNORECASE
    )
    if bulk_patterns.search(nq):
        return None


    # Build suggestion cards for each unique USN
    suggestions = []
    for usn in usns[:6]:
        rows_for_usn = [r for r in data if r.get("usn") == usn]
        name = rows_for_usn[0].get("name", usn) if rows_for_usn else usn
        profile = get_student_profile(usn) or {}
        acad    = get_student_data(usn) or []
        enriched = [{**profile, **row} for row in acad] if acad else [profile]
        suggestions.append({
            "usn":     usn,
            "name":    name,
            "score":   1.0,
            "pct":     100,
            "data":    enriched,
            "profile": profile,
        })

    return {
        "type":           "multiple_match",
        "search_term":    term,
        "confidence":     1.0,
        "auto_corrected": False,
        "message": (
            f"Multiple matching students found for \"{term}\".\n"
            f"Which student details do you want?"
        ),
        "top_match":   suggestions[0],
        "suggestions": suggestions,
    }


# ── Full profile enrichment ───────────────────────────────────────────────────

def _enrich_with_profile(data: list[dict], nq: str, intent: str) -> list[dict]:
    """
    Full profile queries intentionally combine the profile with academic data.
    Narrow SQL queries must remain exactly as returned by the database.
    """
    if intent != 'complete_profile':
        return data

    usns = list(dict.fromkeys(r.get("usn", "") for r in data if r.get("usn")))
    if len(usns) != 1:
        return data  # multi-student result — don't over-enrich

    usn = usns[0]
    profile = get_student_profile(usn) or {}
    if not profile:
        return data

    # For complete_profile: also add graduation data
    if intent == 'complete_profile':
        from graduation_manager import parse_usn_full
        usn_data = parse_usn_full(usn)
        if usn_data:
            for key in ('student_type', 'admission_batch', 'current_year', 'current_sem',
                        'graduation_year', 'graduation_status'):
                if key not in profile or profile.get(key) is None:
                    profile[key] = usn_data.get(key)

    # For full/personal/complete_profile intent with single student: merge profile into every row
    return _apply_dynamic_student_fields([{**profile, **row} for row in data])


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/suggest")
def suggest_students(q: str, current_user: dict = Depends(get_current_user)):
    """
    Live search suggestions for the frontend dropdown.
    Returns top-5 closest matches with score and match_type label.
    Never returns empty for partial inputs ≥ 2 chars if any match exists.
    """
    from fuzzy_search import get_live_suggestions, _normalize
    suggestions = get_live_suggestions(q.strip(), limit=5)

    # Annotate each suggestion with a human-readable match_type
    q_norm = _normalize(q.strip())
    for s in suggestions:
        name_norm = _normalize(s.get('name', ''))
        score = s.get('score', 0)
        if name_norm == q_norm or s.get('usn', '').lower() == q.strip().lower():
            s['match_type'] = 'exact'
        elif name_norm.startswith(q_norm) or any(
            _normalize(t).startswith(q_norm)
            for t in (s.get('name') or '').split()
        ):
            s['match_type'] = 'prefix'
        elif score >= 0.75:
            s['match_type'] = 'fuzzy'
        else:
            s['match_type'] = 'phonetic'

    return suggestions




@router.post("/generate")

def generate_query(request: QueryRequest, current_user: dict = Depends(get_current_user)):
    start = time.time()
    nq = request.natural_query.strip()
    language = getattr(request, 'language', 'english')
    response_language = getattr(request, 'response_language', 'english')
    
    # DEBUG: Log received parameters
    logger.info(f"[DEBUG] Received query: {nq[:50]}...")
    logger.info(f"[DEBUG] Language mode: {language}")
    logger.info(f"[DEBUG] Response language: {response_language}")

    # ──────────────────────────────────────────────────────────────────────────
    # CRITICAL: Semantic Kannada → English Translation
    # ──────────────────────────────────────────────────────────────────────────
    # If query is in Kannada/mixed, translate to English BEFORE entering pipeline.
    # This ensures the SAME existing pipeline handles all languages.
    
    original_query = nq  # Preserve original query for logging/display
    translation_metadata = None
    
    if language in ('kannada', 'mixed'):
        from translation_service import translate_query_if_needed
        try:
            nq, translation_metadata = translate_query_if_needed(nq, language)
            logger.info(f"[TRANSLATE] Original: {original_query[:80]}")
            logger.info(f"[TRANSLATE] Translated: {nq[:80]}")
            logger.info(f"[TRANSLATE] Method: {translation_metadata.get('translation_method')}")
            logger.info(f"[TRANSLATE] Confidence: {translation_metadata.get('translation_confidence', 0):.2f}")
        except Exception as e:
            logger.error(f"[TRANSLATE] Translation failed: {e}")
            # Fallback: use keyword normalization
            normalized_nq, detected_lang = kn_normalize_query(nq)
            nq = normalized_nq
            logger.warning(f"[TRANSLATE] Fallback to keyword normalization")

    # Sprint 2: Detect language BEFORE intent check (for response labeling)
    # Use response_language from request if provided
    if not response_language or response_language == 'english':
        response_language = kn_detect_language(original_query)

    # Sprint 2: Normalize Kannada/mixed queries for intent detection
    # (This is now redundant if translation happened, but kept for backward compat)
    normalized_nq, _ = kn_normalize_query(nq)

    # Use normalized query for intent detection (keeps existing engine intact)
    intent = _detect_intent(normalized_nq)
    # Also check original query for Kannada complete-profile phrases
    if intent != 'complete_profile' and is_complete_profile_intent(original_query):
        intent = 'complete_profile'

    partial_update = _build_update_request(nq) if re.match(r'^\s*update\b', nq, re.I) else None
    if partial_update and partial_update.get("action_required") == "select_student":
        return {"action_required": "select_student", "suggestions": partial_update["suggestions"], "message": partial_update["message"]}

    # Cache lookup (SELECT only)
    cached_sql, cached_result = _get_cache(nq)
    if cached_sql and cached_result is not None:
        if cached_sql.strip().upper().startswith("SELECT"):
            cached_result = _filter_by_intent(cached_result, intent, nq)
            cached_result = _apply_dynamic_student_fields(cached_result)
            is_scalar = (
                intent == 'scalar_number' or
                (len(cached_result) == 1 and len(cached_result[0]) == 1 and
                 (isinstance(list(cached_result[0].values())[0], (int, float)) or
                  re.search(r'\bhow\s+many\b|\bcount\b', nq, re.I)))
            )
            scalar_val = list(cached_result[0].values())[0] if (is_scalar and cached_result) else None
            return {
                "action_required": "none",
                "query": cached_sql,
                "data": cached_result,
                "execution_time": round(time.time() - start, 4),
                "cached": True,
                "intent": intent,
                "is_scalar_number": is_scalar,
                "scalar_value": scalar_val,
            }


    if partial_update:
        result = {"success": True, "query_dict": partial_update}
    else:
        result = generate_sql_query(nq, current_user["role"])
    if not result["success"]:
        error_message = str(result.get("error_msg", ""))
        if error_message.startswith("ERROR:"):
            raise HTTPException(
                503,
                "AI service temporarily unavailable. This query could not be safely resolved locally.",
            )
        raise HTTPException(400, "Could not generate a safe database query.")

    query_dict = _enforce_specific_select(nq, result["query_dict"])
    if not (query_dict.get('operation') == 'update' and query_dict.get('executions')):
        validation = validate_sql_query(query_dict, current_user["role"])
        if not validation["is_valid"]:
            try:
                with db_conn() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO security_logs (user_role, attempted_query, reason) VALUES (%s,%s,%s)",
                        (current_user["role"], str(query_dict), validation["reason"])
                    )
                    conn.commit()
                    cur.close()
            except Exception:
                pass
            raise HTTPException(403, "Invalid student data.")

    op = query_dict.get("operation", "").lower()

    if op in {"insert", "delete"} or (op == "update" and query_dict.get('executions')):
        return {
            "action_required": "confirm",
            "action_type": op.upper(),
            "query": query_dict.get("sql", ""),
            "query_dict": query_dict,
            "original_query": nq,
            "data": [],
            "execution_time": 0,
        }

    try:
        data = _run_query(query_dict)
        elapsed = time.time() - start
        _log_history(current_user["role"], nq, query_dict["sql"], elapsed)
        write_audit_log(
            action="AI_QUERY",
            username=current_user["username"],
            role=current_user["role"],
            summary=f"Query: '{original_query[:100]}'",
            success=True
        )

        # ── 0 results → fuzzy fallback ────────────────────────────────────────
        if len(data) == 0:
            if intent in {'location_search', 'rural_search', 'urban_search'}:
                return {
                    "action_required": "none",
                    "query": query_dict["sql"],
                    "data": [],
                    "execution_time": round(elapsed, 4),
                    "cached": False,
                    "intent": intent,
                    "no_match_message": "No students matched the requested address filters.",
                }

            suggestion = smart_fallback(nq)
            stype = suggestion.get('type', 'no_match')

            if stype == 'no_match' or not suggestion.get('suggestions'):
                return {
                    "action_required": "none",
                    "query": query_dict["sql"],
                    "data": [],
                    "execution_time": round(elapsed, 4),
                    "cached": False,
                    "no_match_message": suggestion.get('message', 'No matching records available.'),
                }

            if suggestion.get('auto_corrected'):
                top = suggestion['suggestions'][0]
                top_data = _filter_by_intent(top['data'], intent, nq)
                return {
                    "action_required": "none",
                    "query": query_dict["sql"],
                    "data": top_data,
                    "execution_time": round(elapsed, 4),
                    "cached": False,
                    "auto_corrected": True,
                    "correction_message": suggestion['message'],
                    "suggestion": suggestion,
                    "intent": intent,
                }

            # suggestion | possible_matches | multiple_match
            return {
                "action_required": "none",
                "query": query_dict["sql"],
                "data": [],
                "execution_time": round(elapsed, 4),
                "cached": False,
                "suggestion": suggestion,
                "intent": intent,
            }

        # Keep calculated academic metadata current for every student query,
        # including bulk results that read persisted current_sem values.
        data = _apply_dynamic_student_fields(data)

        # ── Multi-student ambiguity check (SQL returned > 1 student) ─────────
        ambiguity = _check_ambiguity(data, nq)
        if ambiguity:
            return {
                "action_required": "none",
                "query": query_dict["sql"],
                "data": [],
                "execution_time": round(elapsed, 4),
                "cached": False,
                "suggestion": ambiguity,
                "intent": intent,
            }

        # ── Single student full-profile enrichment ────────────────────────────
        data = _enrich_with_profile(data, nq, intent)

        # ── Intent-based column filtering ─────────────────────────────────────
        data = _filter_by_intent(data, intent, nq)

        # ── Complete-profile fallback: if SQL returned nothing, try profile builder ──
        if intent == 'complete_profile' and not data:
            from fuzzy_search import extract_search_term
            from kannada_processor import extract_search_term_multilingual
            term = extract_search_term_multilingual(nq) or extract_search_term(nq)
            if term:
                candidates = fuzzy_search_students(term, limit=3, min_score=0.75)
                if len(candidates) == 1:
                    data = _build_full_profile_row(candidates[0]['usn'])

        is_scalar = (
            intent == 'scalar_number' or
            (len(data) == 1 and len(data[0]) == 1 and
             (isinstance(list(data[0].values())[0], (int, float)) or
              re.search(r'\bhow\s+many\b|\bcount\b', nq, re.I)))
        )
        scalar_val = list(data[0].values())[0] if (is_scalar and data and len(data) == 1) else None


        # Check girls names response
        if len(data) > 0 and list(data[0].keys()) == ['name'] and re.search(r'\bgirls?\b|\bfemale\b', nq, re.I):
            intent = 'girls_names'

        _set_cache(nq, query_dict["sql"], data)
        return {
            "action_required": "none",
            "query": query_dict["sql"],
            "data": data,
            "execution_time": round(elapsed, 4),
            "cached": False,
            "intent": intent,
            "response_language": response_language,
            "is_scalar_number": is_scalar,
            "scalar_value": scalar_val,
        }


    except Exception as e:
        elapsed = time.time() - start
        suggestion = smart_fallback(nq)
        stype = suggestion.get('type', 'no_match') if suggestion else 'no_match'

        _actionable = {'suggestion', 'possible_matches', 'multiple_match'}
        if suggestion and stype in _actionable and suggestion.get('suggestions'):
            if suggestion.get('auto_corrected'):
                top = suggestion['suggestions'][0]
                top_data = _filter_by_intent(top['data'], intent, nq)
                return {
                    "action_required": "none",
                    "query": str(e),
                    "data": top_data,
                    "execution_time": round(elapsed, 4),
                    "cached": False,
                    "auto_corrected": True,
                    "correction_message": suggestion['message'],
                    "suggestion": suggestion,
                    "intent": intent,
                }
            return {
                "action_required": "none",
                "query": str(e),
                "data": [],
                "execution_time": round(elapsed, 4),
                "cached": False,
                "suggestion": suggestion,
                "intent": intent,
            }
        raise safe_http_error(400, e, "query")


@router.post("/execute")
def execute_confirmed(request: ExecuteRequest, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "Staff":
        raise HTTPException(403, "Permission denied.")

    op  = request.query_dict.get("operation", "").lower()
    sql = request.query_dict.get("sql", "")
    if op == 'update' and request.query_dict.get('executions'):
        update_error = _validate_structured_update(request.query_dict)
        if update_error:
            raise HTTPException(400, update_error)
    else:
        validation = validate_sql_query(request.query_dict, current_user["role"])
        if not validation["is_valid"]:
            raise HTTPException(403, "Invalid student data.")

    try:
        victims = []
        pre_students = []
        restore_tokens = []
        select_sql = ""
        undo_token = ""
        affected_usns = []

        if op == "delete":
            # Snapshot victims BEFORE deletion
            select_sql = re.sub(r'^delete\s+from', 'SELECT usn, name FROM', sql, flags=re.IGNORECASE)
            try:
                victims = _run_query({"operation": "select", "sql": select_sql})
            except Exception:
                pass

            affected_usns = [v.get("usn") for v in victims if v.get("usn")]

        elif op == "insert":
            usn = None
            student_name = None
            match = re.search(r"VALUES\s*\(\s*'([^']+)'\s*,\s*'([^']+)'", sql, re.IGNORECASE)
            if match:
                usn = match.group(1)
                student_name = match.group(2)
            else:
                m2 = re.search(r"VALUES\s*\(\s*'([^']+)'", sql, re.IGNORECASE)
                if m2: usn = m2.group(1)

            if usn:
                affected_usns = [usn]

        elif op == "update" and request.query_dict.get('executions'):
            affected_usns = request.query_dict.get('affected_usns', []) or []
            if affected_usns:
                try:
                    with db_conn() as lookup_conn:
                        lookup_cur = lookup_conn.cursor(dictionary=True)
                        placeholders = ','.join(['%s'] * len(affected_usns))
                        lookup_cur.execute(f"SELECT * FROM students WHERE usn IN ({placeholders})", tuple(affected_usns))
                        pre_students = lookup_cur.fetchall()
                        lookup_cur.execute(f"SELECT * FROM marks WHERE usn IN ({placeholders}) ORDER BY usn, semester", tuple(affected_usns))
                        pre_marks = lookup_cur.fetchall()
                        lookup_cur.close()
                except Exception:
                    pre_students = []
                    pre_marks = []

        # A write is only allowed when its complete affected-record set is
        # known. This prevents successful but non-reversible mutations.
        if op in ("delete", "update") and not affected_usns:
            raise HTTPException(404, "No record found.")
        if op == "insert" and not usn:
            raise HTTPException(400, "Could not save changes.")

        # The database change and its activity/history records are one unit of
        # work. A failed log rolls back the mutation, and a failed mutation
        # cannot appear as a successful activity.
        with db_conn() as conn:
            conn.autocommit = False
            conn.start_transaction()
            cur = conn.cursor()
            try:
                if affected_usns:
                    from routes_undo import create_undo_snapshot
                    operation_labels = {"delete": "Deleted", "insert": "Added", "update": "Updated"}
                    snapshot_operations = {"delete": "DELETE", "insert": "ADD", "update": "UPDATE"}
                    undo_token = create_undo_snapshot(
                        snapshot_operations[op], affected_usns, current_user["username"],
                        f"{operation_labels[op]} {len(affected_usns)} student(s)", conn=conn,
                    )
                if op == "delete" and victims:
                    affected_usns = [v["usn"] for v in victims if v.get("usn")]
                    if affected_usns:
                        placeholders = ','.join(['%s'] * len(affected_usns))
                        cur.execute(f"DELETE FROM marks WHERE usn IN ({placeholders})", tuple(affected_usns))

                if op == "update" and request.query_dict.get('executions'):
                    for creation in { (c['table'], c['column']): c for c in request.query_dict.get('column_creations', []) }.values():
                        _create_column_if_missing(cur, conn, creation['table'], creation['column'], creation['data_type'])
                    affected_rows = 0
                    for execution in request.query_dict.get('executions', []):
                        cur.execute(execution['sql'], tuple(execution['params']))
                        affected_rows += cur.rowcount
                else:
                    params = request.query_dict.get("params")
                    if params is None:
                        cur.execute(sql)
                    else:
                        cur.execute(sql, tuple(params))
                    affected_rows = cur.rowcount

                if op == "delete":
                    for victim in victims:
                        if victim.get("usn"):
                            cur.execute(
                                "INSERT INTO deletion_logs (usn, student_name, deleted_by, restore_token) VALUES (%s,%s,%s,%s)",
                                (victim["usn"], victim.get("name"), current_user["username"], undo_token if 'undo_token' in locals() else None),
                            )
                    audit_action = "DELETED"
                    audit_target = ','.join(v.get("usn", "") for v in victims)
                    audit_summary = f"Deleted {len(victims)} student(s)"
                elif op == "insert":
                    if not usn:
                        raise ValueError("Invalid USN")
                    from routes_files import _parse_usn
                    usn_data = _parse_usn(usn)
                    if usn_data:
                        cur.execute(
                            "UPDATE students SET admission_year=%s, current_year=%s, student_type=%s, estimated_semester=%s WHERE usn=%s",
                            (usn_data.get("admission_batch"), usn_data.get("current_year"),
                             usn_data.get("student_type"), usn_data.get("estimated_semester"), usn),
                        )
                    cur.execute(
                        "INSERT INTO addition_logs (usn, student_name, added_by) VALUES (%s,%s,%s)",
                        (usn, student_name or usn, current_user["username"]),
                    )
                    audit_action, audit_target = "ADDED", usn
                    audit_summary = f"Added student {student_name or usn} ({usn})"
                elif op == "update" and request.query_dict.get('executions'):
                    post_cur = conn.cursor(dictionary=True)
                    placeholders = ','.join(['%s'] * len(affected_usns))
                    post_cur.execute(f"SELECT * FROM students WHERE usn IN ({placeholders})", tuple(affected_usns))
                    post_students = post_cur.fetchall()
                    post_cur.close()
                    pre_by_usn = {s["usn"]: s for s in pre_students if s.get("usn")}
                    changed_fields = []
                    for post_student in post_students:
                        student_usn = post_student.get("usn")
                        before = pre_by_usn.get(student_usn)
                        if not before:
                            continue
                        for column, new_value in post_student.items():
                            if column in ("created_at", "updated_at"):
                                continue
                            old_value = before.get(column)
                            if str(old_value) != str(new_value) and not (old_value is None and new_value is None):
                                changed_fields.append(column)
                                cur.execute(
                                    "INSERT INTO student_history (usn, field_name, old_value, new_value, updated_by) VALUES (%s,%s,%s,%s,%s)",
                                    (student_usn, column, str(old_value) if old_value is not None else None,
                                     str(new_value) if new_value is not None else None, current_user["username"]),
                                )
                    audit_action = "UPDATED" if changed_fields else "UNCHANGED"
                    audit_target = ','.join(s.get("usn", "") for s in pre_students)
                    audit_summary = (f"Updated {len(pre_students)} student(s): {', '.join(sorted(set(changed_fields)))}"
                                     if changed_fields else "No student values changed.")
                else:
                    raise ValueError("Unsupported operation")

                cur.execute(
                    "INSERT INTO audit_log (username, role, action, target_table, target_id, summary, success) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (current_user["username"], current_user["role"], audit_action, "students", audit_target, audit_summary, 1),
                )
                if undo_token:
                    from routes_undo import finalize_undo_snapshot
                    finalize_undo_snapshot(undo_token, affected_usns, conn)
                conn.commit()
                cur.close()
                data = [{"affected_rows": affected_rows}]
            except Exception:
                conn.rollback()
                cur.close()
                raise

        _log_history(
            current_user["role"], request.original_query,
            request.query_dict.get("sql", ""), 0
        )
        _clear_cache()

        if undo_token:
            if op == "delete":
                restore_tokens = [{"usn": v.get("usn"), "name": v.get("name") or v.get("usn"), "token": undo_token} for v in victims]
            elif op == "insert":
                restore_tokens = [{"usn": usn, "name": student_name or usn, "token": undo_token}]
            else:
                restore_tokens = [{"usn": affected_usns[0], "name": f"{len(affected_usns)} student(s)", "token": undo_token}]

        # Build response with detailed operation info for modal popups
        affected_count = len(victims) if op == "delete" else (1 if op == "insert" else len(pre_students))
        student_list = [{"usn": v.get("usn"), "name": v.get("name") or v.get("usn")} for v in victims] if op == "delete" else (
            [{"usn": usn, "name": student_name or usn}] if op == "insert" and usn else (
                [{"usn": s.get("usn"), "name": s.get("name") or s.get("usn")} for s in pre_students] if op == "update" else []
            )
        )

        response = {
            "success": True, 
            "message": {
                "insert": "Student added successfully.",
                "delete": "Student deleted successfully.",
                "update": "Student updated successfully.",
            }[op],
            "data": data,
            "operation_details": {
                "operation_type": {"insert": "ADD", "delete": "DELETE", "update": "UPDATE"}[op],
                "affected_rows": affected_count,
                "students": student_list,
                "tables_updated": "students, marks" if op in ("delete", "insert", "update") else "students",
                "storage_path": "students table",
                "performed_by": current_user["username"],
                "timestamp": datetime.now().strftime("%Y-%m-%d %I:%M %p")
            }
        }

        if restore_tokens:
            response["restore_tokens"] = restore_tokens
            response["undo_available"] = True
            
        return response

    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(400, e, op or "operation")

@router.get("/recent_activity")
def get_recent_activity(current_user: dict = Depends(get_current_user)):
    # Fallback/bridge recent activity that also serves the 6 sections
    from routes_undo import get_activity
    return get_activity(current_user)


@router.post("/sync-vtu")
def sync_vtu(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "Staff":
        return {"success": False, "message": "Unauthorized"}
        
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT usn, current_sem FROM students")
        students = cur.fetchall()
        
        from routes_files import _parse_usn
        
        all_usns = [s["usn"] for s in students if s.get("usn")]
        undo_token = ""
        updates = 0
        conn.autocommit = False
        conn.start_transaction()
        try:
            if all_usns:
                from routes_undo import create_undo_snapshot
                undo_token = create_undo_snapshot(
                    "SEMESTER_UPDATE", all_usns, current_user["username"], "VTU Semester Sync", conn=conn
                )

            for s in students:
                usn = s["usn"]
                usn_data = _parse_usn(usn)
                if not usn_data:
                    continue
                cur.execute(
                    """UPDATE students SET admission_year=%s, current_year=%s,
                       student_type=%s, estimated_semester=%s, current_sem=%s
                       WHERE usn=%s""",
                    (usn_data.get("admission_batch"), usn_data.get("current_year"),
                     usn_data.get("student_type"), usn_data.get("current_sem"),
                     usn_data.get("current_sem"), usn)
                )
                updates += 1
            if undo_token:
                from routes_undo import finalize_undo_snapshot
                finalize_undo_snapshot(undo_token, all_usns, conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
        
    return {
        "success": True, 
        "message": f"VTU Sync complete. Updated {updates} students.",
        "restore_tokens": [{"token": undo_token, "name": "VTU Semester Sync", "usn": "ALL"}],
        "undo_available": True
    }




@router.get("/history")
def get_history(limit: int = 10, current_user: dict = Depends(get_current_user)):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        if current_user["role"] == "Staff":
            cur.execute(
                "SELECT * FROM query_history WHERE user_role='Staff' "
                "ORDER BY timestamp DESC LIMIT %s", (limit,)
            )
        else:
            cur.execute(
                "SELECT * FROM query_history ORDER BY timestamp DESC LIMIT %s", (limit,)
            )
        rows = cur.fetchall()
        cur.close()
    for r in rows:
        if r.get("timestamp"):
            r["timestamp"] = str(r["timestamp"])
    return rows


@router.get("/analytics")
def get_analytics(current_user: dict = Depends(get_current_user)):
    from graduation_manager import get_graduation_analytics
    
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)

        cur.execute("SELECT COUNT(*) AS total FROM students")
        total_students = cur.fetchone()["total"]

        cur.execute("SELECT COUNT(*) AS total FROM marks")
        total_marks = cur.fetchone()["total"]

        cur.execute("SELECT COUNT(*) AS total FROM uploaded_files")
        total_files = cur.fetchone()["total"]

        cur.execute("SELECT COUNT(*) AS total FROM query_history")
        total_queries = cur.fetchone()["total"]

        cur.execute(
            "SELECT semester, ROUND(AVG(sgpa),2) AS avg_sgpa, COUNT(DISTINCT usn) AS student_count "
            "FROM marks GROUP BY semester ORDER BY semester"
        )
        semester_stats = cur.fetchall()

        cur.execute(
            "SELECT s.usn, s.name, ROUND(AVG(m.sgpa),2) AS cgpa "
            "FROM students s JOIN marks m ON s.usn=m.usn "
            "GROUP BY s.usn, s.name ORDER BY cgpa DESC LIMIT 10"
        )
        top_students = cur.fetchall()

        cur.execute("SELECT user_role, COUNT(*) AS cnt FROM query_history GROUP BY user_role")
        query_by_role = cur.fetchall()

        cur.close()
    
    # Get graduation analytics
    grad_analytics = get_graduation_analytics()

    return {
        "total_students": total_students,
        "total_marks": total_marks,
        "total_files": total_files,
        "total_queries": total_queries,
        "semester_stats": semester_stats,
        "top_students": top_students,
        "query_by_role": query_by_role,
        "graduation_analytics": grad_analytics,
    }


@router.get("/profile/{usn}")
def get_student_profile_api(usn: str, current_user: dict = Depends(get_current_user)):
    """
    Return a complete unified student profile for a given USN.

    Response structure:
      {
        "personal": { all fields from students table },
        "academic": [ { semester, sgpa, cgpa } ... ],
        "graduation": { graduation_year, graduation_status, student_type, ... },
        "has_personal": bool,
        "has_academic": bool,
      }
    """
    from graduation_manager import parse_usn_full
    normalized_usn = _normalize_usn(usn)

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)

        # Personal data — all columns
        cur.execute("SELECT * FROM students WHERE UPPER(REPLACE(REPLACE(REPLACE(usn,' ',''),'-',''),'.',''))=%s",
                    (normalized_usn,))
        personal_row = cur.fetchone()

        if not personal_row:
            raise HTTPException(404, "Student not found.")

        actual_usn = personal_row.get('usn', usn)
        write_audit_log(
            action="PROFILE_VIEWED",
            username=current_user["username"],
            role=current_user["role"],
            target_table="students",
            target_id=actual_usn,
            summary=f"Opened profile for student: {personal_row.get('name', actual_usn)} ({actual_usn})",
            success=True
        )

        # Academic data — all semesters with cumulative CGPA
        cur.execute(
            "SELECT semester, sgpa, "
            "ROUND(AVG(sgpa) OVER (PARTITION BY usn ORDER BY semester "
            "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS cgpa "
            "FROM marks WHERE usn=%s ORDER BY semester ASC",
            (actual_usn,)
        )
        academic_rows = cur.fetchall()
        cur.close()

    # Serialize dates / decimals
    personal = _serialize_row(personal_row)

    # Graduation data
    graduation = {}
    usn_data = parse_usn_full(actual_usn)
    if usn_data:
        graduation = {
            'student_type': usn_data.get('student_type'),
            'admission_batch': usn_data.get('admission_batch'),
            'graduation_year': usn_data.get('graduation_year'),
            'graduation_status': usn_data.get('graduation_status'),
            'current_year': usn_data.get('current_year'),
            'current_sem': usn_data.get('current_sem'),
        }

    academic = [_serialize_row(r) for r in academic_rows]

    return {
        "personal": personal,
        "academic": academic,
        "graduation": graduation,
        "has_personal": bool(personal),
        "has_academic": bool(academic),
    }


@router.get("/profile/search")
def search_student_profiles(name: str, current_user: dict = Depends(get_current_user)):
    """
    Fuzzy name search returning up to 5 student profile cards.
    Used when user types a name for the complete-profile intent.
    """
    if not name or len(name.strip()) < 2:
        raise HTTPException(400, "Please provide at least 2 characters.")

    # Handle Kannada input: extract search term
    from kannada_processor import extract_search_term_multilingual
    effective_name = extract_search_term_multilingual(name) or name.strip()

    candidates = fuzzy_search_students(effective_name, limit=5, min_score=0.55)
    if not candidates:
        raise HTTPException(404, "No matching students found.")

    return {
        "candidates": candidates,
        "search_term": effective_name,
        "original_query": name,
    }
