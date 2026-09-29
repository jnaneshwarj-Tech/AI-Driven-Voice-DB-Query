"""
routes_query.py — AI query engine.
Features:
  - Query cache, cumulative CGPA, NLP synonyms, fuzzy search fallback.
  - Conditional extraction: "personal" → personal only, "academic" → marks only.
  - Multiple same-name students → ambiguity selection, never auto-merge.
"""
import json, time, re, logging, os, difflib
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from database import db_conn, write_audit_log
from config import settings
from auth import get_current_user, require_roles
from report_service import mask_rows_for_role
from rag_sql_generator import (
    generate_sql_query,
    _BRANCH_NORMALIZATION,
    _detect_target_semester as _rag_detect_semester,
    _extract_branches as _rag_extract_branches,
    _normalize_branch as _rag_normalize_branch,
    _build_comprehensive_student_query as _rag_build_sem_branch_query,
    _validate_semester_branch_sql as _rag_validate_sem_branch,
)


def _canonical_branch_code(raw) -> str:
    """Collapse any branch representation to its authoritative canonical code.

    Single source of truth is rag_sql_generator._BRANCH_NORMALIZATION, whose
    alias tuples list the canonical code first. Unknown values fall back to the
    upper-cased input so comparisons stay deterministic.
    """
    aliases = _rag_normalize_branch(str(raw or ""))
    if aliases:
        return aliases[0]
    return str(raw or "").strip().upper()


# Authoritative branch code extracted straight from the USN, mirroring
# graduation_manager.parse_usn_full's pattern ^(\d)([A-Z]{2,3})(\d{2})([A-Z]{2,4})(\d{2,3}).
# A fixed SUBSTRING position is wrong because the college code is 2-3 letters,
# so the branch group is not always at offset 7. Non-matching USNs yield ''.
# NOTE: no '$' may appear (query_security_validator rejects it as Mongo syntax),
# so the branch is isolated by stripping the leading degree+college+year prefix
# and then stripping the trailing roll digits instead of using a capture group.
_USN_BRANCH_CODE_SQL = (
    "CASE WHEN UPPER(TRIM(COALESCE(s.usn, ''))) REGEXP "
    "'^[0-9][A-Z]{2,3}[0-9]{2}[A-Z]{2,4}[0-9]{2,3}' "
    "THEN REGEXP_REPLACE(REGEXP_REPLACE(UPPER(TRIM(COALESCE(s.usn, ''))), "
    "'^[0-9][A-Z]{2,3}[0-9]{2}', ''), '[0-9]', '') "
    "ELSE '' END"
)
from query_security_validator import (
    create_confirmation_token,
    is_delete_all_request,
    is_delete_request,
    validate_sql_query,
    verify_confirmation_token,
)
from fuzzy_search import smart_fallback, get_student_data, get_student_profile, extract_search_term, fuzzy_search_students, _levenshtein
from error_messages import safe_http_error
from canonical_fields import map_column, normalize_header, parse_wide_sem_col
from kannada_processor import (
    normalize_query as kn_normalize_query,
    is_complete_profile_intent,
    detect_language as kn_detect_language,
    is_structural_word as kn_is_structural_word,
    get_response_labels,
)

router = APIRouter(prefix="/api/query", tags=["Query Engine"])
logger = logging.getLogger(__name__)
_CACHE_VERSION = "selected-columns-v8-occupation-typos-and-copula:"


def _log_blocked_query(current_user: dict, action: str, query: str) -> None:
    logger.warning("%s user=%s", action, current_user.get("username", "unknown"))
    try:
        write_audit_log(
            action=action,
            username=current_user.get("username", "unknown"),
            role=current_user.get("role", "unknown"),
            target_table="students",
            summary=f"Blocked destructive query request: {str(query)[:200]}",
            success=False,
        )
    except Exception:
        logger.exception("Failed to record blocked query security event.")

def _normalize_usn(raw: str) -> str:
    return re.sub(r'[^A-Za-z0-9]', '', str(raw) or '').upper()


def _is_probable_usn(raw: str) -> bool:
    normalized = _normalize_usn(raw)
    return bool(re.fullmatch(r'[A-Z0-9]{4,}', normalized)) and any(ch.isdigit() for ch in normalized)


_SEARCHBAR_RECORD_IMPERATIVE_RE = re.compile(
    r'\b(record|mark|note|log|enter|set|make|declare|discontinue|dropout|dropped)\b', re.I)


def _is_searchbar_lifecycle_record(text: str) -> bool:
    """A search-bar lifecycle RECORD command: an imperative status change that
    carries either an explicit record verb or a concrete USN. Plain reads such as
    'discontinued students' or 'students who rejoined' (no verb marker, no USN)
    return False so they stay queries."""
    import lifecycle as _LC
    if not _LC.is_lifecycle_record_command(text):
        return False
    return bool(_LC._USN_RE.search(text)
                or _SEARCHBAR_RECORD_IMPERATIVE_RE.search(text))


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

    # Natural "<field> of <target>" order, e.g. "phone of 1QA23CS001" or
    # "father name of Ravi". Only taken when the leading phrase is a real column.
    of_parts = re.split(r'\s+of\s+', left.strip(), maxsplit=1, flags=re.I)
    if len(of_parts) == 2:
        # Strip a leading article ("the address") so the column resolves.
        candidate_field = re.sub(r'^\s*(?:the|a|an)\s+', '', of_parts[0].strip(), flags=re.I)
        target_text = of_parts[1].strip()
        if candidate_field and target_text:
            canonical, _, _, _ = map_column(candidate_field)
            if canonical and normalize_header(candidate_field) != 'all_information':
                return target_text, candidate_field

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
    candidate_text = re.sub(r'^\s*(?:to|as)\s+', '', text.strip(), flags=re.I)
    words = candidate_text.split()
    best_match = None
    for count in range(1, len(words) + 1):
        if words[count - 1].lower() in ('to', 'as'):
            break
        field_text = ' '.join(words[:count])
        canonical, _, confidence, _ = map_column(field_text)
        if not canonical or normalize_header(field_text) == 'all_information':
            continue
        if confidence >= 0.8 or confidence == 0.0:
            value_start = count
            if value_start < len(words) and words[value_start].lower() in ('to', 'as'):
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


# Staff fill a blank field from the search bar with any of these verbs, and they
# write "as" as often as "to" ("fill email of 9QA23CS001 as kid@college.edu").
# Only "update"/"modify" are unambiguous edit imperatives: a softer verb whose
# sentence does not parse as an assignment must fall back to the read path
# instead of erroring ("enter Hassan district students" stays a search).
_UPDATE_INTENT_RE = re.compile(
    r'^\s*(update|modify|change|correct|set|fill\s*in|fill|put|enter|record|note|mark)\s+(.+)$',
    re.I)
_ASSIGNMENT_CONNECTOR_RE = re.compile(r'\b(?:to|as)\b', re.I)


def _parse_update_assignments(natural_query: str) -> dict:
    match = _UPDATE_INTENT_RE.match(natural_query)
    if not match:
        return None
    strong_verb = match.group(1).lower() in ('update', 'modify')
    try:
        return _parse_update_payload(match.group(2).strip(), strong_verb)
    except HTTPException:
        if strong_verb:
            raise
        return None


def _parse_update_payload(payload: str, strong_verb: bool) -> dict:
    first_to = _ASSIGNMENT_CONNECTOR_RE.search(payload)
    if not first_to:
        if strong_verb:
            raise HTTPException(400, "Please specify the information to update.")
        return None

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


def _clean_update_target(raw: str) -> str:
    """Drop descriptor words so a USN/name is not glued onto 'student'/'usn'."""
    t = (raw or "").strip()
    return re.sub(
        r'^(?:the\s+)?student\b[\s:,#]*(?:with\s+)?(?:usn\s+|id\s+|roll\s+number\s+)?',
        '', t, flags=re.I,
    ).strip() or t


def _match_student(target_text: str) -> dict:
    normalized_target = _clean_update_target(target_text)
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


# The USN is the permanent identity key of a student record: every child table,
# undo snapshot and audit row references it, so editing it must be refused with
# a reason the staff member can act on, not a generic "field not found".
_USN_IMMUTABLE_MSG = ("The USN is a student's permanent identity and cannot be "
                      "edited.")


def _resolve_assignment(conn, student: dict, assignment: dict) -> dict:
    raw_field = assignment['field_text']
    raw_value = assignment['value_text']
    canonical, mapping_type, confidence, _ = map_column(raw_field)
    canonical_norm = normalize_header(raw_field)
    if canonical == 'usn':
        raise HTTPException(400, _USN_IMMUTABLE_MSG)

    table_columns = {
        'students': _load_table_columns(conn, 'students'),
        'marks': _load_table_columns(conn, 'marks'),
    }

    def _choose_table() -> str:
        if canonical.startswith('sem_') or canonical in {'sgpa', 'cgpa'}:
            return 'marks'
        if 'mark' in canonical_norm or 'marks' in canonical_norm:
            return 'marks'
        if mapping_type == 'synonym' and canonical in {'year', 'semester'}:
            return 'marks'
        # Demographic/identity fields belong to students even when a stray column
        # of the same name exists in marks (e.g. marks.name, marks.father_name).
        if canonical in table_columns['students']:
            return 'students'
        if canonical in table_columns['marks']:
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

    create_if_missing = False

    # Canonical student fields the app computes on the fly (never a real column).
    _DERIVED_STUDENT_FIELDS = {'age'}

    if column not in table_columns[table]:
        # Auto-create only for confidently recognized, storable canonical fields on
        # the students table (migration-safe). Never turn an untrusted/unknown header
        # (passthrough/fuzzy/ambiguous) or a derived/virtual field into a SQL identifier.
        if (
            table == 'students'
            and mapping_type in {'exact', 'synonym', 'context'}
            and column == canonical
            and column not in {'usn', 'student_id'}
            and column not in _DERIVED_STUDENT_FIELDS
            and re.fullmatch(r'[a-z][a-z0-9_]{1,62}', column)
        ):
            create_if_missing = True
        else:
            raise HTTPException(400, f"Field '{raw_field}' is not available in the database.")

    if column in {'usn', 'student_id'} and table == 'students':
        raise HTTPException(400, _USN_IMMUTABLE_MSG)

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
        'create_if_missing': create_if_missing,
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
        resolved_all = []
        grouped = {}
        for assignment in parsed['assignments']:
            resolved = _resolve_assignment(conn, student, assignment)
            resolved_all.append(resolved)
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
        # Staff confirm this dialog without reading SQL, so it has to name the
        # student and every value that will change.
        'message': (
            f"{student.get('name') or student['usn']} ({student['usn']}): "
            + ', '.join(
                f"{r['column']} → "
                + ('(blank)' if r['value'] is None
                   else (str(r['value'])[:40] + '…' if len(str(r['value'])) > 40 else str(r['value'])))
                for r in resolved_all)
        ),
    }


_DELETE_VERB_RE = re.compile(
    r'^\s*(?:please\s+|kindly\s+)?(?:delete|remove|erase|del|drop)\b',
    re.I,
)
_DELETE_FILLER_RE = re.compile(
    r'\b(?:with\s+usn|usn|students?|the|a|an|records?|details?|of|named|please|kindly)\b',
    re.I,
)
_USN_TOKEN_RE = re.compile(r'\b[0-9][A-Za-z]{2}[0-9]{2}[A-Za-z]{2,3}[0-9]{3}\b')


def _extract_delete_target(nq: str) -> str:
    """Pull the specific student identifier (USN preferred, else name) out of a
    natural-language delete request. Returns '' when no concrete target exists."""
    text = (nq or "").strip()
    usn_match = _USN_TOKEN_RE.search(text)
    if usn_match:
        return usn_match.group(0)
    text = _DELETE_VERB_RE.sub('', text)
    text = _DELETE_FILLER_RE.sub(' ', text)
    return re.sub(r'\s+', ' ', text).strip(" .,!?'\"-")


def _build_delete_request(nq: str) -> dict | None:
    """Resolve an admin delete request to a single, USN-scoped DELETE query_dict.

    Never produces an unscoped DELETE: a missing or ambiguous target asks the user
    to disambiguate instead. Delete-all is blocked earlier in the pipeline, so this
    only ever targets one uniquely identified student.
    """
    target = _extract_delete_target(nq)
    if not target:
        return {
            'action_required': 'select_student',
            'suggestions': [],
            'message': 'Please specify which student to delete (name or USN).',
        }

    match = _match_student(target)
    if match.get('ambiguous'):
        return {
            'action_required': 'select_student',
            'suggestions': match['ambiguous'],
            'message': 'Multiple students matched. Please choose the exact student to delete.',
        }

    student = match['student']
    usn = str(student.get('usn') or '').strip()
    if not usn:
        return {
            'action_required': 'select_student',
            'suggestions': [],
            'message': 'Could not resolve a unique student record to delete.',
        }
    safe_usn = usn.replace("'", "''")
    name = student.get('name') or usn
    return {
        'operation': 'delete',
        'sql': f"DELETE FROM students WHERE usn = '{safe_usn}'",
        'student_usn': usn,
        'student_name': name,
        'original_query': nq,
        'message': (
            f"Warning: This will permanently remove the selected student data "
            f"({name}, USN {usn}). Do you want to continue?"
        ),
    }


_ADD_VERB_RE = re.compile(
    r'^\s*(?:please\s+|kindly\s+)?(?:add|insert|create|register|enroll|enrol)\b',
    re.I,
)
_ADD_FIELD_STOP = re.compile(
    r'\b(?:usn|named?|called|student|new|a|an|the|with|and|is|as|record|entry|details?)\b',
    re.I,
)


def _extract_add_name(text: str) -> str:
    """Pull a student name out of an add request. Handles 'named X', 'name X',
    'name: X', and a trailing '<USN> <Name>' form."""
    m = re.search(r'\b(?:named?|called)\s+(?:as\s+)?([A-Za-z][A-Za-z .\'-]+)', text, re.I)
    if m:
        return m.group(1).strip(" .'-")
    m = re.search(r'\bname\s*[:=]\s*([A-Za-z][A-Za-z .\'-]+)', text, re.I)
    if m:
        return m.group(1).strip(" .'-")
    # Fallback: drop the USN token and add-verbs/fillers, keep the rest as the name.
    remainder = _USN_TOKEN_RE.sub(' ', text)
    remainder = _ADD_VERB_RE.sub(' ', remainder)
    remainder = _ADD_FIELD_STOP.sub(' ', remainder)
    remainder = re.sub(r'\s+', ' ', remainder).strip(" .,!?'\"-")
    return remainder


def _build_insert_request(nq: str) -> dict | None:
    """Deterministically build a single-student INSERT from an add request.

    Mirrors the update/delete builders so that adding a student does not depend on
    the LLM being reachable. Returns a query_dict ready for confirmation, or a
    select_student/error dict when the USN or name is missing or duplicated.
    """
    text = (nq or "").strip()
    if not _ADD_VERB_RE.match(text):
        return None
    if not re.search(r'\bstudent\b|\brecord\b|\busn\b', text, re.I):
        return None

    usn_match = _USN_TOKEN_RE.search(text)
    usn = (usn_match.group(0).upper() if usn_match else "").strip()
    if not usn:
        return {
            'action_required': 'select_student',
            'suggestions': [],
            'message': 'Please provide a valid USN to add a student (e.g. 4HG23CS032).',
        }

    name = _extract_add_name(text)
    if not name:
        return {
            'action_required': 'select_student',
            'suggestions': [],
            'message': 'Please provide the student name to add (e.g. "add student 4HG23CS032 named Ravi Kumar").',
        }

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT usn FROM students WHERE UPPER(usn)=%s", (usn,))
        exists = cur.fetchone()
        cur.close()
    if exists:
        return {
            'action_required': 'select_student',
            'suggestions': [],
            'message': f'A student with USN {usn} already exists. Use update to modify this record.',
        }

    safe_usn = usn.replace("'", "''")
    safe_name = name.replace("'", "''")
    return {
        'operation': 'insert',
        'sql': f"INSERT INTO students (usn, name) VALUES ('{safe_usn}', '{safe_name}')",
        'student_usn': usn,
        'student_name': name,
        'original_query': nq,
        'message': f"Add new student {name} (USN {usn})?",
    }


def _unmapped_filter_clause(query: str) -> str | None:
    known_terms = {
        "student", "students", "lateral", "entry", "le", "direct", "second", "2nd",
        "branch", "department", "dept", "stream", "course", "cs", "cse", "is", "ise",
        "ec", "ece", "cv", "me", "mech", "aiml", "ai", "ml", "eee", "civil", "civ",
        "mechanical", "electronics", "information", "science", "computer", "semester", "sem", "blood", "group", "type",
        "a", "b", "ab", "o", "cgpa", "sgpa", "gpa", "age", "rural", "urban", "area",
        "civ",
        "areas", "region", "regions", "village", "villages", "emergency", "contact", "phone",
        "number", "numbers", "mobile", "email", "address", "father", "mother", "name", "dob",
        "gender", "male", "female", "status", "active", "graduated", "available", "present", "entered", "recorded",
        "provided", "missing", "null", "empty", "blank", "not", "no", "any", "the", "an",
        "with", "without", "having", "has", "have", "whose", "and", "or", "in", "from",
        "currently", "studying", "student's", "students'", "father's", "mother's",
        # possessive pronouns are projection connectives ("with their blood group"),
        # never a column name — they must not trigger the "could not map" guard.
        "their", "his", "her", "its", "our", "your", "my", "them",
        "positive", "negative",
        # expanded field terms
        "birth", "date", "dob", "permanent", "current", "taluk", "district", "state",
        "aadhar", "uid", "religion", "caste", "category", "sub", "subcaste", "year",
        "admission", "joining", "roll", "division", "section", "domain",
        "usn", "id", "record", "data", "info", "information", "details", "profile",
        # backlogs/arrears are compiled into an EXISTS filter by this builder.
        "backlog", "backlogs", "arrear", "arrears", "cleared",
        "zero",
        "list", "show", "count", "how", "many", "all", "every", "some",
        # comparison operators & ranking/connective words — these never name a column,
        # so they must not trigger the "could not map" guard (e.g. "more than 8 cgpa").
        "more", "most", "greater", "less", "above", "below", "over", "under",
        "exceed", "exceeds", "than", "least", "maximum", "minimum", "between",
        "exactly", "equal", "equals", "except", "excluding", "top", "last",
        "first", "bottom", "highest", "lowest", "best", "worst", "rank", "ranks",
        "ranked", "ranking", "sort", "sorted", "sorts", "order", "ordered",
        "arrange", "arranged", "give", "gives", "display", "displayed", "find",
        "fine", "who", "whom", "that", "this", "these", "those", "are", "was",
        "were", "being", "been", "get", "gets", "into", "about", "own", "very",
        "at", "near", "up", "distict", "distrcit", "distrct", "hsan",
        # missing/value synonyms
        "without", "no", "missing", "absent", "lack", "lacking", "lacks", "empty",
        "unknown", "unavailable", "unset", "unfilled", "not", "doesn't", "dont",
        "doesnt", "don't", "hasn't", "hasnt", "haven't", "havent",
        # Fee status is compiled into its own condition from student_fees, so
        # these words are mapped and must not raise "could not map: paid".
        "fee", "fees", "payment", "payments", "paid", "pay", "paying", "unpaid",
        "pending", "due", "dues", "outstanding", "challan", "balance", "partial",
        "partially", "baki",
    }
    # Terms the intent-field layer can resolve (plurals, contact/occupation
    # synonyms, Kannada/Romanized aliases) must never trip the guard, since the
    # resolver — not this whitelist — decides whether they map.
    try:
        import intent_fields as _IF
        known_terms |= _IF.known_query_terms()
    except Exception:
        known_terms |= {"mothers", "fathers", "guardians", "occupation",
                        "occupations", "profession", "profession", "job", "jobs"}
    pattern = re.compile(
        r"\b(?:with|having|without|whose|have|has)\s+"
        r"(?:(?:a|an|the|any|no|not)\s+)?([A-Za-z][A-Za-z'-]*)",
        re.I,
    )
    for match in pattern.finditer(query):
        term = match.group(1).casefold().strip("'-")
        if term not in known_terms and not term.isdigit():
            return term
    return None


def _current_academic_fields_sql(alias: str = "s") -> tuple[str, str]:
    usn = f"UPPER(TRIM(COALESCE({alias}.usn, '')))"
    valid_usn = (
        f"({usn} REGEXP '^[0-9][A-Z]{{2,3}}[0-9]{{2}}[A-Z]{{2,4}}[0-9]{{2,3}}' "
        f"AND CHAR_LENGTH({usn}) BETWEEN 9 AND 13)"
    )
    admission_year = f"(2000 + CAST(SUBSTRING({usn}, 4, 2) AS UNSIGNED))"
    lateral_entry = f"(CAST(RIGHT({usn}, 3) AS UNSIGNED) >= 400)"
    years_since_admission = (
        f"(YEAR(CURDATE()) - {admission_year} + {lateral_entry} "
        "- (MONTH(CURDATE()) < 7))"
    )
    semester = (
        "GREATEST(1, LEAST(8, "
        f"({years_since_admission} * 2) + IF(MONTH(CURDATE()) >= 7, 1, 0)))"
    )
    current_sem = f"CASE WHEN {valid_usn} THEN {semester} ELSE {alias}.current_sem END"
    current_year = (
        f"CASE WHEN {valid_usn} THEN GREATEST(1, LEAST(CAST(LEFT({usn}, 1) AS UNSIGNED), "
        f"(({semester} + 1) DIV 2))) ELSE {alias}.current_year END"
    )
    return current_sem, current_year


class QueryRequest(BaseModel):
    natural_query: str
    language: str = 'english'  # 'english', 'kannada', or 'mixed'
    response_language: str = 'english'  # Response language preference
    debug: bool = False
class ExecuteRequest(BaseModel):
    query_dict: dict
    original_query: str
    confirmed: bool = False
    confirmation_token: str | None = None


def _unpaid_fee_usns() -> list[str]:
    """USNs with at least one fee row that normalizes to 'unpaid' (same rule as
    reports/exports). Used by the lifecycle 'discontinued but fees pending' intent
    so the NL list can never disagree with the Fees Details section."""
    try:
        import report_service
        matched: list[str] = []
        with db_conn() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT DISTINCT usn, status FROM student_fees WHERE usn IS NOT NULL")
            seen = set()
            for r in cur.fetchall():
                canon, _ = report_service.normalize_fee_status(r.get("status"))
                if canon == "unpaid" and r["usn"] not in seen:
                    seen.add(r["usn"]); matched.append(r["usn"])
            cur.close()
        return matched
    except Exception:
        return []


# ── Exact lifecycle status naming (spec §9) ─────────────────────────────────
# Naming one canonical status means THAT status, not the family around it:
# "temporarily discontinued" is not "any discontinued student", and the
# register's own labels ("Admission Cancelled", "Other") have to be askable.
# Built lazily: lifecycle imports routes_query, so routes_query must not import
# lifecycle at module level.
_EXACT_STATUS_LABELS: list[tuple[str, re.Pattern]] | None = None


def _exact_status_labels() -> list[tuple[str, re.Pattern]]:
    global _EXACT_STATUS_LABELS
    if _EXACT_STATUS_LABELS is None:
        import lifecycle as LC
        labels = []
        # Longest label wins, so "temporarily discontinued" is not read as the
        # shorter, wider "discontinued" family.
        for status in sorted(LC.LIFECYCLE_STATUSES, key=len, reverse=True):
            words = status.lower().replace("-", " ").replace("_", " ").split()
            if len(words) < 2:
                continue  # a bare 'active' / 'other' means too many things
            if len(words) == 2:
                # Tolerate one filler word between the halves: staff write
                # "students whose admission was cancelled".
                body = (re.escape(words[0]) + r"\W+(?:\w+\W+)?" + re.escape(words[1]))
            else:
                body = r"\W+".join(re.escape(w) for w in words)
            labels.append((status, re.compile(r"\b" + body + r"\b", re.I)))
        _EXACT_STATUS_LABELS = labels
    return _EXACT_STATUS_LABELS


# Words that carry no condition of their own. A question built only from these
# plus a status word asks for that status and nothing else.
_LIFECYCLE_QUESTION_FILLER = frozenset({
    "show", "list", "display", "find", "get", "tell", "print", "me", "us", "please",
    "how", "many", "much", "count", "number", "total", "all", "every", "each",
    "the", "a", "an", "of", "for", "to", "in", "with", "and", "or", "is", "are",
    "was", "were", "who", "that", "this", "students", "student", "currently",
    "now", "only", "just", "status", "lifecycle", "life", "cycle", "marked",
    "recorded", "their", "his", "her", "s",
})


def _bare_lifecycle_status(eq: str) -> str | None:
    """'Active' and 'Other' are also ordinary English words ('active backlogs',
    'other branches'), so they name a lifecycle status only when the question
    asks for nothing else. Any leftover condition word defers to the ordinary
    pipeline, which knows backlogs, fees, semesters and rankings."""
    toks = [t for t in re.split(r"[^a-z0-9]+", (eq or "").lower()) if t]
    if not toks:
        return None
    import lifecycle as LC
    for status in (LC.STATUS_ACTIVE, LC.STATUS_OTHER):
        word = status.lower()
        if word in toks and not set(toks) - (_LIFECYCLE_QUESTION_FILLER | {word}):
            return status
    return None


def _explicit_lifecycle_status(eq: str) -> str | None:
    return (_exact_status_label(eq) or _bare_lifecycle_status(eq))


def _exact_status_label(eq: str) -> str | None:
    for status, rx in _exact_status_labels():
        if rx.search(eq or ""):
            return status
    return None


def _build_lifecycle_query(nq: str) -> dict | None:
    """Deterministic SQL for Student Lifecycle intents (spec §9): dropout,
    discontinued, readmission pending/approved-not-joined, rejoined, cleared
    backlog after rejoining, per-semester counts, incomplete lifecycle records,
    and a single student's complete status history.

    Reads the current status from the same expression the Lifecycle register
    answers with — COALESCE(student_lifecycle_status.current_status,
    students.lifecycle_status) — so a status question and the register can never
    disagree, and joins student_lifecycle_status for the effective/enrolled
    detail. This is READ-only; it never mutates anything. When
    no lifecycle keyword is present it returns None so the ordinary pipeline
    (backlogs / fees / demographics / LLM) proceeds untouched.
    """
    eq = (nq or "").strip().lower()
    if not eq:
        return None
    is_count = bool(re.search(r'\b(?:how\s+many|count|number\s+of)\b', eq))
    order = "ORDER BY s.usn ASC"

    import lifecycle as LC

    # Lifecycle status vocabulary present in the (translated) question.
    _dropout     = bool(re.search(r'\bdrop\s*outs?\b|\bdropped\s+out\b|\bdropout\b|\bleft\s+(?:the\s+)?(?:college|course)\b|\bleft\b.*\bnot\s+returned\b', eq))
    _discont     = bool(re.search(r'\bdiscontinu\w*\b|\bstopped\s+(?:studies|college|course)\b|\bodu\s+nilistid\w*\b|\bniyarpi\s+bes\w*\b', eq))
    _readmit_req = bool(re.search(r'\breadmission\b.*\b(?:pending|requested|request|waiting|await|apply)\w*\b|\b(?:pending|requested|waiting)\b.*\breadmission\b', eq))
    _readmit_app = bool(re.search(r'\breadmission\b.*\bapprov\w*\b|\bapprov\w*\b.*\breadmission\b|\bgot\s+readmission\b', eq))
    _not_joined  = bool(re.search(r'\bnot\s+(?:yet\s+)?(?:joined|rejoined|re-?joined|rejoin|come)\b|\bwithout\s+joining\b|\byet\s+to\s+(?:join|rejoin)\b|\bnot\s+joined\b', eq))
    _rejoined    = bool(re.search(r'\bre-?join(?:ed|ing)?\b|\bmatte\s+(?:join|sere)\w*\b|\bcome\s+back\b|\bback\s+to\s+college\b|\bresum\w*\b|\breattended\b', eq))
    _graduated   = bool(re.search(r'\bgraduat\w*\b|\bpassed\s+out\b', eq))
    _transferred = bool(re.search(r'\btransferred?\b', eq))

    # "cleared backlog after rejoining"
    _cleared_bl  = bool(re.search(r'\bclear(?:ed|ing)?\b|\bresolv\w*\b|\bremoved?\b', eq)) and bool(re.search(r'\bbacklog|\barrear', eq))

    # "history of <USN>"
    _his_m = re.search(r'\b(?:complete\s+)?(?:status\s+)?history\b', eq)
    _usn_m = _USN_TOKEN_RE.search(nq)
    if _his_m and _usn_m:
        usn = _usn_m.group(0)
        return {"operation": "select", "sql": (
            "SELECT usn, event_type, from_status, to_status, effective_date, "
            "last_enrolled_semester, requested_semester, approved_semester, "
            "rejoin_date, scheme, reason, approval_ref, actor_username, created_at "
            "FROM student_lifecycle_events WHERE usn=%s "
            "ORDER BY created_at ASC, id ASC"
        ), "params": [usn]}

    # Grouping: "in each/per semester"
    _per_sem = bool(re.search(r'\b(?:each|per|wise|category|grouped)\b', eq)) and bool(re.search(r'\bsem(?:ester)?\b', eq))

    # Semester filter (which semester was last attended)
    _sem_m = re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?\s*sem(?:ester)?\b', eq)
    _sem_flt = f" AND ls.last_enrolled_semester = {int(_sem_m.group(1))}" if _sem_m else ""

    # Batch / admission year ("from 2023 batch", "2023 batch")
    _batch_m = re.search(r'\b(\d{4})\b[\s-]*\b(?:batch|admission|year\s*of\s*admission)\b', eq)
    if not _batch_m:
        _batch_m = re.search(r'\b(?:batch|admission)\b[^0-9]*\b(\d{4})\b', eq)
    _batch_flt = f" AND s.admission_year = {int(_batch_m.group(1))}" if _batch_m else ""

    # Effective / dropout year ("dropped out in 2024" — a bare 4-digit year).
    _yr_flt = ""
    if not _batch_m:
        _yr_m = re.search(r'\b(?:in|during|since)\s+(\d{4})\b', eq)
        if _yr_m:
            _yr_flt = f" AND YEAR(ls.effective_date) = {int(_yr_m.group(1))}"

    # Reason category ("discontinued due to financial problems", "for personal reasons").
    # Only classify when an explicit reason cue is present AND the following text hits a
    # real category keyword — never the 'other' fallback — so an unrelated trailing word
    # (e.g. "for the CSE branch") can't inject a spurious filter. reason_cat is validated
    # against the LC.REASON_CATEGORIES whitelist before being inlined, so it is
    # injection-safe.
    _reason_m = re.search(
        r'(?:due to|because of|because|on account of|reason(?:ed)?(?:\s+as|\s+is)?|'
        r'ಕಾರಣ|caran)\s+([a-z\u0c80-\u0cff ]{3,60})', eq)
    if not _reason_m:
        _reason_m = re.search(r'\bfor\s+([a-z\u0c80-\u0cff ]+?)\s+reasons?\b', eq)
    _reason_cat = None
    if _reason_m:
        _rc = LC.classify_reason_category(_reason_m.group(1))
        if _rc and _rc != "other":
            _reason_cat = _rc
    _reason_flt = (f" AND ls.reason_category = '{_reason_cat}'"
                   if _reason_cat in LC.REASON_CATEGORIES else "")

    # "discontinued who later rejoined": current status Rejoined-Active AND a prior
    # discontinuation/dropout event exists. The subquery uses only canonical status
    # literals (never user text), so it is injection-safe.
    _rejoin_after_discont = bool(_rejoined and (_discont or _dropout))
    _discont_literals = ",".join(
        "'%s'" % s for s in sorted(LC.DISCONTINUED_STATUSES))
    _rejoin_discont_flt = (
        f" AND s.usn IN (SELECT le.usn FROM student_lifecycle_events le "
        f"WHERE le.from_status IN ({_discont_literals}))"
        if _rejoin_after_discont else "")

    # Fee-pending combined intent ("discontinued but fees still pending")
    _fees_pending = bool(re.search(r'\bfees?\b|\bpayment\b|\boutstanding\b|\barrears?\b|\bdue\b(?! to)', eq)) and \
                    bool(re.search(r'\bpending\b|\bunpaid\b|\bdue\b(?! to)|\bnot\s+paid\b|\bbaki\b', eq))

    # Which lifecycle status set to filter on. An exactly-named canonical status
    # wins over the family keywords, so "temporarily discontinued" is not widened
    # to every discontinued/dropout student.
    _exact = _explicit_lifecycle_status(eq)
    status_set: list[str] = []
    if _exact and _rejoined and _exact in LC.DISCONTINUED_STATUSES:
        # "temporarily discontinued students who later rejoined" is a Rejoined
        # register with a prior discontinuation behind it.
        status_set = [LC.STATUS_REJOINED]
    elif _exact:
        status_set = [_exact]
    elif _readmit_app and _not_joined:
        status_set = [LC.STATUS_READMISSION_APPROVED]
    elif _readmit_req:
        status_set = [LC.STATUS_READMISSION_REQUESTED]
    elif _rejoined and not _cleared_bl:
        status_set = [LC.STATUS_REJOINED]
    elif _graduated:
        status_set = [LC.STATUS_GRADUATED]
    elif _transferred:
        status_set = [LC.STATUS_TRANSFERRED]
    elif _cleared_bl and _rejoined:
        status_set = [LC.STATUS_REJOINED]
    elif _dropout:
        status_set = [LC.STATUS_DROPOUT, LC.STATUS_TEMP_DISCONTINUED,
                      LC.STATUS_DISCONTINUED_REVIEW]
    elif _discont:
        status_set = [LC.STATUS_TEMP_DISCONTINUED, LC.STATUS_DISCONTINUED_REVIEW,
                      LC.STATUS_DROPOUT]
    elif _readmit_app or _readmit_req or _rejoined or _not_joined:
        status_set = [LC.STATUS_READMISSION_REQUESTED, LC.STATUS_READMISSION_APPROVED,
                      LC.STATUS_REJOINED]

    # If nothing lifecycle-specific matched, defer to the rest of the pipeline.
    if not status_set:
        return None

    placeholders = ",".join(["%s"] * len(status_set))
    base_join = ("FROM students s "
                 "LEFT JOIN student_lifecycle_status ls ON ls.usn = s.usn")
    # One definition of "current status" for the whole product: the derived
    # register with the student row as fallback, which is the exact expression
    # /lifecycle/list answers with. Filtering only on students.lifecycle_status
    # made a student whose two sources disagree — e.g. a status change undone
    # before the register was re-synced — findable under the stale status and
    # invisible under the one the Lifecycle tab shows.
    status_flt = f"COALESCE(ls.current_status, s.lifecycle_status) IN ({placeholders})"
    where = status_flt + _sem_flt + _batch_flt + _yr_flt + _reason_flt + _rejoin_discont_flt

    params = list(status_set)

    # Discontinued-with-unpaid-fees: intersect the status set with unpaid USNs.
    if _fees_pending:
        unpaid = _unpaid_fee_usns()
        if not unpaid:
            return {"operation": "select",
                    "sql": "SELECT s.usn, s.name FROM students s WHERE s.usn IN (NULL) ORDER BY s.usn ASC",
                    "params": []}
        uph = ",".join(["%s"] * len(unpaid))
        where += f" AND s.usn IN ({uph})"
        params = list(status_set) + unpaid

    # Rejoined-after-clearing-backlogs: no open backlog for that student.
    if _cleared_bl and _rejoined:
        where += (" AND s.usn NOT IN "
                  "(SELECT sb.usn FROM student_backlogs sb WHERE sb.cleared = 0)")

    if is_count and _per_sem:
        return {"operation": "select", "sql": (
            f"SELECT ls.last_enrolled_semester AS semester, "
            f"COUNT(DISTINCT s.usn) AS students "
            f"{base_join} WHERE {where} "
            f"GROUP BY ls.last_enrolled_semester ORDER BY semester ASC"
        ), "params": params}
    if is_count:
        return {"operation": "select", "sql": (
            f"SELECT COUNT(DISTINCT s.usn) AS total_students "
            f"{base_join} WHERE {where}"
        ), "params": params}

    # Listing: project lifecycle + the academic facts staff expect to see filled.
    _cgpa_expr = ("ROUND(COALESCE((SELECT AVG(mm.sgpa) FROM marks mm "
                  "WHERE mm.usn=s.usn AND mm.sgpa IS NOT NULL), s.cgpa), 2)")
    proj = (f"SELECT DISTINCT s.usn, s.name, s.branch, s.admission_year, "
            f"s.student_type, "
            f"COALESCE(ls.current_status, s.lifecycle_status) AS current_status, "
            f"ls.effective_date, ls.last_enrolled_semester AS last_semester, "
            f"ls.last_enrolled_academic_year AS last_academic_year, "
            f"ls.scheme, ls.reason, {_cgpa_expr} AS cgpa "
            f"{base_join} WHERE {where} {order}")
    return {"operation": "select", "sql": proj, "params": params}


_OCC_KEYWORDS = ("occupation", "profession", "designation")


def _fix_occupation_typos(s: str) -> str:
    """Repair misspellings of the occupation keywords ('occcupation') so the
    deterministic patterns see canonical text. Same first letter + high
    similarity keeps false positives (e.g. 'location') away."""
    def _fix(tok: str) -> str:
        if len(tok) < 7 or not tok.isalpha():
            return tok
        for canon in _OCC_KEYWORDS:
            if tok != canon and tok[0] == canon[0] \
                    and difflib.SequenceMatcher(None, tok, canon).ratio() >= 0.8:
                return canon
        return tok
    return " ".join(_fix(w) for w in s.split(" "))


# Grade abbreviations staff type phonetically. Getting one letter wrong must not
# silently change the meaning of the query: "top 5 students by capa" has to rank
# by CGPA, not return the first five USNs in student-number order.
_GRADE_METRICS = ("cgpa", "sgpa", "gpa")
_RANKING_CONTEXT_RE = re.compile(
    r"\b(?:top|first|last|bottom|highest|lowest|best|worst|fewest|toppers?|"
    r"order|ordered|sort|sorted|rank|ranked|ranking|wise)\b", re.I)
# Only a word sitting in the sort-key slot is a candidate. Without this, a
# student's name that happens to resemble an abbreviation ("named capra") would
# be rewritten and the query would stop finding that student.
_SORT_KEY_SLOT_RE = re.compile(
    r"\b(?P<pre>by|in|of|for|as\s+per|order\s+by|sort\s+by|rank\s+by|"
    r"top\s+\d+\s+(?:students?)?)\s+(?P<tok>[a-zA-Z]{4,8})\b")


def _fix_metric_typos(s: str) -> str:
    """Repair misspellings of the grade abbreviations ('capa' -> 'cgpa',
    'cpga' -> 'cgpa'). Deliberately narrow: it only runs inside a ranking/sort
    query, only on the word in the sort-key slot, and only when that word shares
    the abbreviation's first letter and is within edit distance 2 of it."""
    if not _RANKING_CONTEXT_RE.search(s):
        return s

    def _repair(m: re.Match) -> str:
        tok = m.group("tok")
        t = tok.casefold()
        if t in _GRADE_METRICS:
            return m.group(0)
        best, best_d = None, 3
        for canon in _GRADE_METRICS:
            if t[0] != canon[0]:
                continue
            d = _levenshtein(t, canon)
            if d < best_d:
                best, best_d = canon, d
        return m.group(0)[:m.start("tok") - m.start()] + best if best else m.group(0)

    return _SORT_KEY_SLOT_RE.sub(_repair, s)


def _column_contains_value(value: str, column: str) -> bool:
    """Data-driven membership test (spacing/case tolerant). `column` is always a
    code constant, never user input."""
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT 1 FROM students WHERE REPLACE(LOWER(`{column}`), ' ', '') LIKE %s LIMIT 1",
                (f"%{value.replace(' ', '')}%",))
            found = cur.fetchone() is not None
            cur.close()
        return found
    except Exception:
        return False


# Words that carry no filtering meaning in a contact request — pure verbs,
# articles, student/subject nouns, phone nouns, and Kannada/Romanized aliases.
# A contact question whose ONLY remaining tokens are these is a bare listing
# ("give me the students' mother phone numbers") and is safe for the intent
# resolver to answer. Any leftover content token (rural, cs, 7th, blood,
# lateral, ajjampura, cgpa, discontinued …) means the query carries extra
# conditions and must fall through to the compound AST path instead.
_CONTACT_FILLER = frozenset({
    # request verbs / politeness / quantifiers / result nouns
    "give", "show", "list", "display", "get", "tell", "find", "search",
    "provide", "extract", "print", "fetch", "output", "me", "us", "please",
    "can", "could", "would", "want", "need", "kindly", "generate", "let",
    "see", "view", "pull", "dump", "export", "all", "every", "each", "which",
    "complete", "full", "only", "just", "know", "about", "details", "detail",
    "info", "information", "record", "records", "data",
    # articles / prepositions / copulas
    "the", "a", "an", "of", "for", "to", "in", "from", "with", "and", "or",
    "is", "are", "was", "were", "their", "his", "her", "its", "that", "whose",
    "who", "s",
    # student / subject nouns (English + Kannada + Romanized)
    "student", "students", "strength", "mother", "mothers", "maternal", "tayi",
    "thaye", "amma", "tande", "thande", "nane", "father", "fathers", "paternal",
    "appa", "parent", "parents", "parental", "guardian", "guardians", "ward",
    "wards", "abhibhataka", "emergency",
    # phone / contact nouns (English + Kannada + Romanized)
    "phone", "phones", "mobile", "mobiles", "contact", "contacts", "number",
    "numbers", "nos", "cell", "mahati", "mohathi", "fone", "no",
})

# Absence phrasing means the user wants students LACKING a contact — a
# missing/IS NULL condition the compound path already answers, never a listing.
_CONTACT_ABSENCE_RE = re.compile(
    r"\bwithout\b|\bmissing\b|\black(?:s|ing)?\b|\blacking\b|\babsent\b|"
    r"\bempty\b|\bnot\s+(?:have|has|entered|provided|filled|available)\b|"
    r"\b(?:have|has)\s+no\b|\bdon'?t\s+have\b|\bdoes\s+not\s+have\b|"
    r"\bno\s+(?:mother|father|parent|guardian|emergency|contact|phone|mobile|number)\b",
    re.I,
)


def _is_bare_contact_listing(nq: str) -> bool:
    """True only when the query *just* asks to list a contact number — no
    absence term and no extra filter condition. Prevents the intent resolver
    from hijacking multi-condition ('rural CS … without emergency contact') or
    missing-value queries the compound AST path already handles correctly."""
    text = (nq or "").lower()
    if _CONTACT_ABSENCE_RE.search(text):
        return False
    toks = {t for t in re.split(r"[^a-z0-9\u0c00-\u0cff]+", text) if t}
    return not (toks - _CONTACT_FILLER)


# A student-level filter that must not be dropped when it appears next to a
# single-topic question ("CS students having zero backlogs" is a branch filter
# AND a backlog filter, not just a backlog question).
_COMPANION_FILTER_RE = re.compile(
    r"\b(?:cgpa|sgpa|percentage|marks|district|taluk|village|state|urban|rural|"
    r"male|female|girls?|boys?|gender|blood\s*group|age[ds]?\s+\d|\d+\s*years?\s*old|"
    r"active|graduat\w*|dropout|drop\s*out|discontinu\w*|re-?admission|re-?join\w*|"
    r"transferred|lateral|regular|bonafide|fee|fees|paid|unpaid|admission\s+year|"
    r"batch|year\s+of\s+joining|from\s+the\s+\d{4}\s+(?:batch|year))\b",
    re.IGNORECASE,
)


def _has_companion_filters(eq: str) -> bool:
    """True when the question asks for more than the topic it names."""
    if _COMPANION_FILTER_RE.search(eq):
        return True
    if _rag_extract_branches(eq):
        return True
    # A place name is a filter even when the word "district" is not typed:
    # "students with no backlogs from Hassan" must not lose Hassan.
    for column in ("district", "village", "taluk", "state"):
        for value in _column_values(column):
            if len(value) >= 4 and re.search(rf"\b{re.escape(value.casefold())}\b", eq):
                return True
    return False


def _backlog_student_filter_sql(eq: str) -> tuple[str, list] | None:
    """WHERE fragment (on the `s` alias) expressing a backlog/arrears request.

    Kept separate from the standalone backlog queries, which answer with one row
    per backlog subject: this is the student-level form used when the request
    also carries other filters that must survive.
    """
    if not re.search(r"\bbacklog(?:s)?\b|\barrear(?:s)?\b", eq):
        return None
    if re.search(r"\b(?:without|no|zero|not\s+have|not\s+having|don'?t\s+have|"
                 r"have\s+no|has\s+no)\b", eq):
        return ("s.usn NOT IN (SELECT usn FROM student_backlogs WHERE cleared=0)", [])
    inner = ["cleared=0"]
    params: list = []
    _subj_sem = ("NULLIF(CAST(NULLIF(REGEXP_SUBSTR(LOWER(subject), "
                 "'[1-8](st|nd|rd|th)?[ ]?sem'), '') AS UNSIGNED), 0)")
    sem_m = re.search(r"\b(\d+)(?:st|nd|rd|th)?\s*(?:sem(?:ester)?)\b", eq)
    if sem_m:
        inner.append(f"COALESCE(NULLIF(semester, 0), {_subj_sem}) = {int(sem_m.group(1))}")
    subj_m = re.search(
        r"\bbacklogs?\s+(?:in|of|for|on|subject(?:s)?(?:\s+is|\s+are)?|)\s+"
        r"([a-z][a-z ]*?)"
        r"(?=\s+(?:students?|student|list|show|display|who|have|has|having|please|\?|$)|[,;.]|$)",
        eq)
    if subj_m:
        subject = re.sub(r"\b(?:the|a|an|subject|is|are)\b", "",
                         subj_m.group(1).strip()).strip()
        if subject:
            inner.append("REPLACE(LOWER(subject), ' ', '') LIKE %s")
            params.append(f"%{subject.replace(' ', '')}%")
    return ("s.usn IN (SELECT usn FROM student_backlogs WHERE "
            + " AND ".join(inner) + ")", params)


# Columns whose values come from the college's own typed-in data. Staff spell
# these differently every day ("Dharwad"/"Dhrwd", "Hindhu"/"Hindu") and the
# imported sheets themselves carry typos, so a filter value that matches nothing
# is resolved against the values that actually exist instead of returning zero
# rows. Only positive operators are corrected — a negated filter keeps the
# literal the user asked for.
_FUZZY_VALUE_COLUMNS = {
    "district", "village", "taluk", "state", "area", "region", "caste",
    "sub_caste", "religion", "category", "father_occupation",
    "mother_occupation", "student_type", "kannada_medium", "blood_group",
    "branch", "division", "domain",
}
_DISTINCT_VALUES: dict[tuple[str, str], list[str]] = {}


def _column_values(column: str) -> list[str]:
    key = (str(settings.MYSQL_DB), column)
    cached = _DISTINCT_VALUES.get(key)
    if cached is not None:
        return cached
    values: list[str] = []
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            # `column` is from _FUZZY_VALUE_COLUMNS, never from user input.
            cur.execute(
                f"SELECT DISTINCT `{column}` FROM students "
                f"WHERE `{column}` IS NOT NULL AND TRIM(`{column}`) <> ''")
            values = [str(r[0]).strip() for r in cur.fetchall() if str(r[0]).strip()]
            cur.close()
    except Exception:
        values = []
    _DISTINCT_VALUES[key] = values
    return values


def _closest_column_value(column: str, term: str) -> str | None:
    """Real DB value closest to a mistyped one, or None if the term already
    matches a value (then nothing is wrong) or nothing is close enough."""
    known = _column_values(column)
    if not known or not str(term).strip():
        return None
    needle = str(term).strip().casefold()
    folded = {k: k.casefold() for k in known}
    for cand in folded.values():
        if needle == cand or needle in cand:
            return None
        # A real value written inside a longer phrase ("haveri district") already
        # matches. A value with typo debris glued onto it ("haveridd") does not:
        # require the whole-word form before calling it good.
        if cand in needle and re.search(
                rf"(?<![a-z0-9]){re.escape(cand)}(?![a-z0-9])", needle):
            return None
    best, score = None, 0.0
    for original, cand in folded.items():
        ratio = difflib.SequenceMatcher(None, needle, cand).ratio()
        common = {w for w in re.split(r"[^a-z0-9]+", cand) if w} & \
                 {w for w in re.split(r"[^a-z0-9]+", needle) if w}
        if common:
            ratio = max(ratio, 0.75 + 0.05 * len(common))
        if ratio > score:
            best, score = original, ratio
    return best if score >= 0.6 else None


def _best_value_match(column: str, term: str) -> tuple[str | None, float]:
    needle = str(term).strip().casefold()
    if not needle:
        return None, 0.0
    best, score = None, 0.0
    for known in _column_values(column):
        ratio = difflib.SequenceMatcher(None, needle, known.casefold()).ratio()
        if ratio > score:
            best, score = known, ratio
    return best, score


# A stray space inside a value ("Have ri" for Haveri) splits it into two tokens
# that match nothing; the glued form matches a real value almost exactly.
_SPLIT_VALUE_MIN_RATIO = 0.86


def _repair_split_values(text: str) -> str:
    """Join column values typed with an extra space inside the word."""
    parts = re.split(r"(\s+)", text)
    changed = False
    for i in range(len(parts) - 2):
        first, sep, second = parts[i], parts[i + 1], parts[i + 2]
        if sep.strip():
            continue
        if not all(re.fullmatch(r"[A-Za-z][A-Za-z']{1,14}", w)
                   for w in (first, second)):
            continue
        for column in sorted(_FUZZY_VALUE_COLUMNS):
            value, score = _best_value_match(column, first + second)
            if score < _SPLIT_VALUE_MIN_RATIO:
                continue
            half = max(_best_value_match(column, first)[1],
                       _best_value_match(column, second)[1])
            if half >= score:
                continue
            parts[i], parts[i + 2] = value, ""
            changed = True
            break
    if not changed:
        return text
    return re.sub(r"\s{2,}", " ", "".join(parts)).strip()


def _fuzzy_filter_value(field: str, operator: str, values: list):
    """Correct one filter literal against the column's real values.

    Returns (values, [(asked, understood), ...]). LIKE wildcards are preserved so
    the corrected value stays inside the same SQL fragment.
    """
    if field not in _FUZZY_VALUE_COLUMNS or operator not in (
            "CONTAINS", "EQUALS", "IN", "LIKE", "STARTS_WITH"):
        return values, []
    notes = []
    fixed = []
    for raw in values:
        text = str(raw)
        inner = text.strip("%")
        if not inner or inner.isdigit():
            fixed.append(raw)
            continue
        best = _closest_column_value(field, inner)
        if best:
            fixed.append(text.replace(inner, best))
            notes.append((inner, best))
        else:
            fixed.append(raw)
    return fixed, notes


# Words staff type for a numeric threshold. The alternation is built longest-form
# first, because a regex picks the first alternative, not the longest: reading
# "greater than or equal to" as "greater than" leaves "or equal to 7" behind, and
# the whole condition used to be dropped, answering with every student in the
# database instead of the ones asked for.
_OP_SYNONYMS = {
    "greater than or equal to": ">=", "greater than or equals to": ">=",
    "greater than or equal": ">=", "more than or equal to": ">=",
    "is not less than": ">=", "not less than": ">=", "no less than": ">=",
    "not below": ">=", "at least": ">=", "atleast": ">=", "or equal to": ">=",
    "or above": ">=", "or over": ">=", "or older": ">=", "minimum": ">=",
    "and above": ">=", "not younger than": ">=", "or equal": ">=",
    "no smaller than": ">=",
    "greater than": ">", "more than": ">", "older than": ">",
    "exceeds": ">", "exceed": ">", "not fewer than": ">=", "fewer than": "<",
    "above": ">", "over": ">", "greater": ">", "more": ">", "mele": ">", "mela": ">",
    "less than or equal to": "<=", "less than or equals to": "<=",
    "less than or equal": "<=", "fewer than or equal to": "<=",
    "is not greater than": "<=", "not greater than": "<=", "not more than": "<=",
    "no more than": "<=", "not above": "<=", "at most": "<=", "atmost": "<=",
    # "cgpa up to 7" is the inclusive ceiling staff use most often; without these
    # forms the threshold parsed to nothing and the question was answered as
    # "students who have any CGPA at all" — every row in the table.
    "up to": "<=", "upto": "<=", "up-to": "<=", "or up to": "<=", "within": "<=",
    "not over": "<=", "no greater than": "<=", "or under": "<=", "or fewer": "<=",
    "till": "<=", "until": "<=", "and below": "<=",
    "maximum": "<=", "younger than": "<", "or below": "<=", "or younger": "<=",
    "or less": "<=", "less than": "<", "below": "<", "under": "<", "less": "<",
    "equal to": "=", "equals to": "=", "equals": "=", "equal": "=", "exactly": "=",
    ">=": ">=", "=>": ">=", "<=": "<=", "=<": "<=", "==": "=", ">": ">", "<": "<",
    "=": "=",
}
_OP_WORD = r"(?:" + "|".join(
    re.escape(k) for k in sorted(_OP_SYNONYMS, key=lambda k: (-len(k), k))) + r")"
# "cgpa is above 7" / "age of at least 18": staff insert a linking word between
# the field and the operator, which must not break the match.
_COPULA = r"(?:is\s+|are\s+|was\s+|were\s+|of\s+|as\s+|be\s+|being\s+)?"
_NUM_RE = r"(\d+(?:\.\d+)?)"


def _comparison_match(query: str, field_words: str) -> tuple[str, float, re.Match] | None:
    """Match a numeric threshold either field-first ("cgpa above 7",
    "age is at least 18") or value-first ("at least 7 cgpa").

    Returns (SQL operator, value, match). The match is returned so callers can
    inspect the text right after the number ("18 or older").
    """
    field_first = re.search(
        rf"\b(?:{field_words})\s*{_COPULA}(?:(not)\s+)?({_OP_WORD})?\s*(?:of\s+)?{_NUM_RE}",
        query)
    if field_first:
        negation, word, raw = field_first.group(1), field_first.group(2), field_first.group(3)
        return _operator_of(negation, word), float(raw), field_first
    value_first = re.search(
        rf"(?:(not)\s+)?({_OP_WORD})\s*{_NUM_RE}\s*(?:of\s+)?(?:{field_words})\b",
        query)
    if value_first:
        negation, word, raw = value_first.groups()
        return _operator_of(negation, word), float(raw), value_first
    return None


def _operator_of(negation: str | None, word: str | None) -> str:
    operator = _OP_SYNONYMS.get((word or "").casefold().strip(), "=")
    if negation:
        operator = {"<": ">=", ">": "<=", "=": "NOT_EQUALS"}.get(operator, operator)
    return operator


_FEE_TOPIC_RE = re.compile(
    r"\bfees?\b|\bfee\b|\bpayment\b|\bchallan\b|\bdues?\b|\boutstanding\b|"
    r"\bpaid\b|\bunpaid\b|\bpending\b",
    re.I,
)


def _fee_status_target(query: str) -> str | None:
    """Which fee-status class the question asks about, or None.

    'paid_all' is kept apart from 'paid' on purpose: "has paid all fees" means no
    unpaid row left behind, while "students who paid fees" means at least one row
    was paid. A student with one paid and one pending row qualifies for the
    second reading and must not appear in the first.
    """
    if not _FEE_TOPIC_RE.search(query):
        return None
    if re.search(r"\bpartial(?:ly)?\b|\bpart\s+paid\b|\bsome\s+(?:amount\s+)?paid\b", query):
        return "partial"
    if re.search(
            r"\ball\s+fees?\s+paid\b|\bfees?\s+(?:are\s+|is\s+)?(?:fully|complete|entire)"
            r"\w*\s+paid\b|\bpaid\s+(?:all|everything|the\s+full|the\s+entire|complete)"
            r"\w*\b|\bno\s+(?:due|dues|balance|pending|remaining|outstanding)\b|"
            r"\bfees?\s+(?:cleared|done|completed)\b|\bfully\s+paid\b|\bclear(?:ed)?\s+fees?\b",
            query):
        return "paid_all"
    if re.search(
            r"\b(?:not\s+(?:paid|pay|cleared|done|yet)|haven'?t\s+paid|didn'?t\s+pay|"
            r"unpaid|not\s+paid|pending|due|dues|outstanding|balance\s+(?:left|there|remain)?"
            r"|baki)\b",
            query):
        return "unpaid"
    if re.search(
            r"\b(?:fully\s+paid|full\s+amount\s+paid|fees?\s+paid|already\s+paid|cleared|paid)\b",
            query):
        return "paid"
    return None


def _fee_status_usns(target: str) -> list[str]:
    """USNs whose fee rows normalise to this status class (report_service rule).

    The messy stored spellings ("No", "not paid", "-", "Balance 5000") are
    canonicalised in Python by the same helper the reports use, so the NL list,
    the profile FEE DETAILS section and the exports can never disagree.
    """
    import report_service
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT DISTINCT usn, status FROM student_fees WHERE usn IS NOT NULL")
        rows = cur.fetchall()
        cur.close()
    unpaid_seen: set[str] = set()
    matched: list[str] = []
    matched_seen: set[str] = set()
    for row in rows:
        canon, _ = report_service.normalize_fee_status(row.get("status"))
        usn = row.get("usn")
        if not usn:
            continue
        if canon == "unpaid":
            unpaid_seen.add(usn)
        if canon == target and usn not in matched_seen:
            matched_seen.add(usn)
            matched.append(usn)
    if target == "paid_all":
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT usn FROM students")
            all_usns = [r[0] for r in cur.fetchall()]
            cur.close()
        return [usn for usn in all_usns if usn not in unpaid_seen]
    return matched


def _has_companion_student_filter(query: str) -> bool:
    """True when the question also restricts students by a students-table field.

    The fee-status path answers from a fixed query of its own, so any extra
    condition (district, gender, caste, CGPA…) has to be left to the main filter
    engine, which composes all conditions together.
    """
    return bool(re.search(
        r"\bdistrict(?:s)?\b|\btaluk(?:s)?\b|\bvillage(?:s)?\b|\btehsil(?:s)?\b|"
        r"\bmandal(?:s)?\b|\bstate\b|\bzone\b|\b(?:rural|urban)\b|"
        r"\b(?:male|female|girls?|boys?|women|men|ladies)\b|"
        r"\bbranch(?:es)?\b|\bdepartment(?:s)?\b|\b(?:cse|ece|ise|cv|mech|civil|"
        r"mechanical|computer\s+science|electronics|information\s+science)\b|"
        r"\bsem(?:ester)?\b|\b(?:cgpa|sgpa|gpa)\b|\bcumulative\s+gpa\b|"
        r"\bcaste\b|\breligion\b|\brelegion\b|\bcategory\b|\bcaste\b|"
        r"\baged?\b|\byears?\s+old\b|\blateral\b|\bactive\b|\bgraduated\b|"
        r"\bblood\s+(?:group|type)\b|\bquota\b|\bbacklogs?\b|\barrears?\b|"
        r"\bkannada\s+medium\b|\bphysically\b|\bdistance\b|\bkm\b|"
        r"\baadhar\b|\bphone\b|\bmobile\b|\bemail\b|\boccupation\b",
        query, re.I,
    ))


def _build_dynamic_field_query(nq: str) -> dict | None:
    """
    Build deterministic SQL for new Google Form fields.
    Uses actual DB columns (hk_status, father_occupation, etc.) NOT dynamic_data JSON.
    """
    eq = nq.strip().lower()
    is_count = bool(re.search(r'\b(?:count|how\s+many|number\s+of)\b', eq))
    order = "ORDER BY s.usn ASC"

    # ── Fee payment status (unpaid / partially paid / paid) ───────────────────
    # Free-text statuses in student_fees are classified with the SAME authoritative
    # rule used by reports (report_service.normalize_fee_status), so the NL list,
    # the profile FEE DETAILS section, and exports never disagree. A student
    # qualifies when at least one of their fee rows normalizes to the requested
    # class. Blank / "none" / "not applicable" rows are never treated as unpaid
    # (spec §7). Fees are matched on status only — no balance is ever invented.
    # A fee question that also restricts students by district, gender, caste, CGPA
    # or any other students-table field must go through the main filter engine,
    # which composes every condition. Answering it here dropped those conditions
    # ("students from Haveri who have not paid fees" listed unpaid students of
    # every district), and narrowing the projection to the dropped filter then
    # removed the fee columns the ORDER BY still referenced (MySQL 3065).
    # "paid all fees" needs the same engine, because it excludes students who have
    # an unpaid row even when they also have a paid one.
    _fee_target = _fee_status_target(eq) if _FEE_TOPIC_RE.search(eq) else None
    if _fee_target and _fee_target != "paid_all" \
            and not _has_companion_student_filter(eq):
        matched = _fee_status_usns(_fee_target)
        if is_count:
            if not matched:
                return {"operation": "select", "sql": "SELECT 0 AS students_" + _fee_target + "_fees", "params": []}
            _ph = ", ".join(["%s"] * len(matched))
            return {"operation": "select", "sql": f"SELECT COUNT(DISTINCT usn) AS students_{_fee_target}_fees FROM student_fees WHERE usn IN ({_ph})", "params": matched}
        if not matched:
            return {"operation": "select", "sql": "SELECT s.usn, s.name FROM students s WHERE s.usn IN (NULL) ORDER BY s.usn ASC", "params": []}
        _ph = ", ".join(["%s"] * len(matched))
        return {"operation": "select", "sql": (
            f"SELECT DISTINCT s.usn, s.name, s.branch, sf.fee_type, sf.year, "
            f"sf.status AS fee_status, sf.amount_paid, sf.remaining_amount "
            f"FROM students s JOIN student_fees sf ON sf.usn = s.usn "
            f"WHERE s.usn IN ({_ph}) ORDER BY s.usn ASC, sf.fee_type ASC, sf.year ASC"
        ), "params": matched}

    # ── Incomplete personal details ──────────────────────────────────────────

    # Configurable required-personal-field set derived from the real schema. A
    # field counts as missing only when NULL or empty/whitespace — never 0, "No"
    # or "Not applicable". Returns the missing-field names + a count so the list
    # is diagnosable, and never conflates academic omissions with personal ones.
    _REQUIRED_PERSONAL_FIELDS = (
        ("name", "Name"), ("gender", "Gender"), ("dob", "Date of Birth"),
        ("blood_group", "Blood Group"), ("aadhar_no", "Aadhaar"),
        ("phone", "Phone"), ("email", "Email"), ("address", "Address"),
        ("father_name", "Father Name"), ("mother_name", "Mother Name"),
    )
    if re.search(
        r"\bincomplete\b|\bmissing\b[^.]*\b(?:personal|detail|information|info|profile|record|field)\b|"
        r"\b(?:personal|contact|demographic|basic)\b[^.]*\b(?:missing|incomplete|empty|blank|not\s+(?:filled|provided|entered|available))\b",
        eq,
    ):
        _miss = lambda c: f"(NULLIF(TRIM(COALESCE(s.`{c}`, '')), '') IS NULL)"
        or_conds = " OR ".join(_miss(c) for c, _ in _REQUIRED_PERSONAL_FIELDS)
        # CONCAT_WS skips NULLs, so present fields contribute nothing and no
        # trailing-separator TRIM(... FROM ...) (which contains the FROM keyword)
        # is needed. Labels are developer constants, never user input.
        name_concat = "CONCAT_WS(', ', " + ", ".join(
            f"IF({_miss(c)}, '{label}', NULL)" for c, label in _REQUIRED_PERSONAL_FIELDS
        ) + ")"
        count_expr = " + ".join(f"IF({_miss(c)}, 1, 0)" for c, _ in _REQUIRED_PERSONAL_FIELDS)
        if is_count:
            return {"operation": "select",
                    "sql": f"SELECT COUNT(*) AS students_with_incomplete_details FROM students s WHERE {or_conds}",
                    "params": []}
        return {"operation": "select",
                "sql": (
                    f"SELECT s.usn, s.name, s.current_sem, "
                    f"{name_concat} AS missing_fields, "
                    f"({count_expr}) AS missing_count "
                    f"FROM students s WHERE {or_conds} "
                    f"ORDER BY missing_count DESC, s.usn ASC"
                ),
                "params": []}

    # ── HK / Non-HK ──────────────────────────────────────────────────────────
    is_nonhk = bool(re.search(r'\b(non[-\s]hk|not\s+hk|non\s+hk)\b', eq))
    is_hk    = bool(re.search(r'\bhk\b', eq))
    if is_hk or is_nonhk:
        hk_val = "Non-HK" if is_nonhk else "HK"
        label  = "total_non_hk_students" if is_nonhk else "total_hk_students"
        if is_count:
            return {"operation":"select","sql":f"SELECT COUNT(*) AS {label} FROM students s WHERE s.hk_status = %s","params":[hk_val]}
        return {"operation":"select","sql":f"SELECT s.usn, s.name, s.hk_status, s.district, s.current_sem FROM students s WHERE s.hk_status = %s {order}","params":[hk_val]}

    # ── Backlogs ──────────────────────────────────────────────────────────────
    if re.search(r'\bbacklog(?:s)?\b|\barrear(?:s)?\b', eq):
        # These answers are one row per backlog subject and deliberately carry no
        # other filter, so a combined request ("active CS students in semester 6
        # from Hassan with zero backlogs") must go to the combined engine instead
        # of silently losing branch/semester/CGPA/district here.
        if _has_companion_filters(eq):
            return None
        no_bl   = bool(re.search(r'\b(?:without|no|zero|0|not\s+have|not\s+having|don.t\s+have)\b', eq))
        CS_EXPR, _ = _current_academic_fields_sql("s")
        # A backlog's semester is often left out of sb.semester but written into the
        # free-text subject ("4th sem", "3 sem", "3rd and 4th sem"). Derive it:
        # stored value -> parsed from subject -> the student's current semester.
        _subj_sem = ("NULLIF(CAST(NULLIF(REGEXP_SUBSTR(LOWER(sb.subject), "
                     "'[1-8](st|nd|rd|th)?[ ]?sem'), '') AS UNSIGNED), 0)")
        _sem_disp = f"COALESCE(NULLIF(sb.semester, 0), {_subj_sem}, {CS_EXPR})"
        sem_m   = re.search(r'\b(\d+)(?:st|nd|rd|th)?\s*(?:sem(?:ester)?)\b', eq)
        sem_flt = f" AND {_sem_disp} = {int(sem_m.group(1))}" if sem_m else ""
        # Optional subject name, e.g. "backlog in operating system".
        subj_m  = re.search(
            r'\bbacklogs?\s+(?:in|of|for|on|subject(?:s)?(?:\s+is|\s+are)?|)\s+'
            r'([a-z][a-z ]*?)'
            r'(?=\s+(?:students?|student|list|show|display|who|have|has|having|please|\?|$)|[,;.]|$)',
            eq,
        )
        subject = (subj_m.group(1).strip() if subj_m else "")
        subject = re.sub(r'\b(?:the|a|an|subject|is|are)\b', '', subject).strip()
        subj_flt = ""
        subj_params = []
        if subject and not no_bl:
            subj_flt = " AND REPLACE(LOWER(sb.subject), ' ', '') LIKE %s"
            subj_params = [f"%{subject.replace(' ', '')}%"]
        if no_bl:
            if is_count:
                return {"operation":"select","sql":"SELECT COUNT(DISTINCT s.usn) AS students_without_backlogs FROM students s WHERE s.usn NOT IN (SELECT usn FROM student_backlogs WHERE cleared=0)","params":[]}
            return {"operation":"select","sql":f"SELECT s.usn, s.name, s.branch FROM students s WHERE s.usn NOT IN (SELECT usn FROM student_backlogs WHERE cleared=0) {order}","params":[]}
        # Academic truth projected alongside the backlog (spec: fill blank
        # SEM/CGPA by USN). Semester spans every backlog; sgpa is that semester's
        # SGPA; cgpa is the cumulative average of the student's marks.
        _cgpa_expr = ("ROUND(COALESCE((SELECT AVG(mm.sgpa) FROM marks mm "
                      "WHERE mm.usn=s.usn AND mm.sgpa IS NOT NULL), s.cgpa), 2)")
        _sgpa_expr = (f"(SELECT m.sgpa FROM marks m WHERE m.usn=s.usn "
                      f"AND m.semester={_sem_disp} AND m.sgpa IS NOT NULL LIMIT 1)")
        if is_count:
            return {"operation":"select","sql":f"SELECT COUNT(DISTINCT s.usn) AS students_with_backlogs FROM students s JOIN student_backlogs sb ON sb.usn=s.usn WHERE sb.cleared=0{sem_flt}{subj_flt}","params":subj_params}
        return {"operation":"select","sql":f"SELECT DISTINCT s.usn, s.name, s.branch, sb.subject, {_sem_disp} AS semester, sb.cleared, {_sgpa_expr} AS sgpa, {_cgpa_expr} AS cgpa FROM students s JOIN student_backlogs sb ON sb.usn=s.usn WHERE sb.cleared=0{sem_flt}{subj_flt} {order}","params":subj_params}

    # ── Parent occupation (father / mother), value-aware & general ────────────
    # Handles "mother occupation is house wife", "father's job is a farmer",
    # "students whose mother profession is home nurse", "occupation of <Name>",
    # and the bare "list mother occupation" listing — without a hardcoded word
    # list, so no occupation value is ever silently dropped.
    eq_occ = _fix_occupation_typos(eq)
    father_occ = bool(re.search(r"\bfathers?(?:['’]s)?\s*(?:occupation|job|work|profession|designation)\b|\bfather\s+occupation\b", eq_occ))
    mother_occ = bool(re.search(r"\bmothers?(?:['’]s)?\s*(?:occupation|job|work|profession|designation)\b|\bmother\s+occupation\b", eq_occ))
    if father_occ or mother_occ:
        field = "mother_occupation" if mother_occ else "father_occupation"
        # Name-targeted: "occupation of Divya" (but not "of all students").
        name_m = re.search(r"\b(?:occupation|job|work|profession|designation)\s+of\s+([a-z][a-z ]*?)(?:\s+(?:students?|having|with|in|from)\b|$)", eq_occ)
        if name_m and not re.search(r"\ball\b", eq_occ) and name_m.group(1).strip() not in {"the", "a", "an"}:
            return {"operation": "select", "sql": f"SELECT s.usn, s.name, s.{field} FROM students s WHERE s.name LIKE %s", "params": [f"%{name_m.group(1).strip()}%"]}
        # Occupation value: text after the keyword and an optional copula.
        val_m = re.search(r"\b(?:occupation|job|work|profession|designation)\b[^a-z0-9]*(?:is|are|was|=|:)\s*([a-z][a-z ]*)", eq_occ)
        if not val_m:
            val_m = re.search(r"\b(?:mother|father)(?:['’]s)?\s+(?:occupation|job|work|profession)\s+(?:of\s+)?([a-z][a-z ]*)", eq_occ)
        value = ""
        if val_m:
            value = re.sub(r"\b(?:students?|having|with|whose|that|who|the|a|an)\b.*$", "", val_m.group(1)).strip()
        if not value:
            # "<value> father occupation" ("show Carpenter father occupation
            # students"): the value sits BEFORE the keyword, which neither pattern
            # above can see, so the question was answered as "any recorded
            # occupation" — 56 rows instead of the 13 carpenters asked for. The
            # candidate only counts when the column actually holds that word, so a
            # bare listing request keeps its own answer.
            pre_m = re.search(
                r"^(?:(?:show|list|display|find|get|give|print|tell|me|count|how|many|"
                r"number|of|all|the|only|details?|information|info|records?|profile|"
                r"data|for|about|students?|student|whose|which|who|with|having|and|or)\s+)*"
                r"(?P<value>[a-z][a-z ]{2,30}?)\s+"
                r"(?:mother|father)(?:['’]s)?\s+(?:occupation|job|work|profession|designation)\b",
                eq_occ)
            candidate = pre_m.group("value").strip(" .'-") if pre_m else ""
            if candidate:
                matched, ratio = _best_value_match(field, candidate)
                if matched and ratio >= 0.6:
                    value = candidate
        if value:
            # spacing-tolerant so "house wife" also matches stored "housewife".
            return {"operation": "select", "sql": f"SELECT s.usn, s.name, s.{field} FROM students s WHERE REPLACE(LOWER(s.{field}), ' ', '') LIKE %s {order}", "params": [f"%{value.replace(' ', '')}%"]}
        return {"operation": "select", "sql": f"SELECT s.usn, s.name, s.{field} FROM students s WHERE s.{field} IS NOT NULL AND s.{field} != '' {order}", "params": []}

    # "father is (a) teacher" / "mothers are farmers" / "mother works as a nurse"
    # — occupation intent with no keyword. Decided by the DATA: the value is
    # treated as an occupation UNLESS it matches a stored parent NAME (so
    # "father is Ramesh" stays a name query). Singular/plural and spacing
    # variants are all matched against the occupation column.
    cop = re.search(
        r"\b(?P<parent>father|mother)s?(?:['’]s)?\s+"
        r"(?:is|are|was|were|works?\s+as|working\s+as|do(?:es)?\s+as)\s+(?:an?\s+)?"
        r"(?P<value>[a-z][a-z ]{2,})",
        eq_occ)
    if cop:
        value = re.sub(
            r"\b(?:students?|having|with|whose|that|who|the|a|an)\b.*$", "",
            cop.group("value")).strip(" .,;:")
        is_mother = cop.group("parent") == "mother"
        occ_field = "mother_occupation" if is_mother else "father_occupation"
        name_field = "mother_name" if is_mother else "father_name"
        if value and not _column_contains_value(value, name_field):
            stem = value.replace(" ", "").lower()
            variants = {stem}
            if stem.endswith("s"):
                variants.add(stem[:-1])      # teachers -> teacher
            else:
                variants.add(stem + "s")     # teacher  -> teachers
            conds = " OR ".join(
                [f"REPLACE(LOWER(s.`{occ_field}`), ' ', '') LIKE %s"] * len(variants))
            return {"operation": "select",
                    "sql": f"SELECT s.usn, s.name, s.{occ_field} FROM students s "
                           f"WHERE ({conds}) {order}",
                    "params": [f"%{v}%" for v in sorted(variants)]}


    # ── Kannada medium ────────────────────────────────────────────────────────
    if re.search(r'\bkannada\s+medium\b', eq):
        if is_count:
            return {"operation":"select","sql":"SELECT COUNT(*) AS kannada_medium_students FROM students s WHERE UPPER(TRIM(s.kannada_medium)) IN ('YES', 'Y')","params":[]}
        return {"operation":"select","sql":f"SELECT s.usn, s.name, s.kannada_medium, s.branch, s.district FROM students s WHERE UPPER(TRIM(s.kannada_medium)) IN ('YES', 'Y') {order}","params":[]}

    # ── Physically handicapped ────────────────────────────────────────────────
    if re.search(r'\bphysically\s+(?:handicapped|disabled|challenged)\b|\bph\b', eq):
        if is_count:
            return {"operation":"select","sql":"SELECT COUNT(*) AS ph_students FROM students s WHERE UPPER(TRIM(s.physically_handicapped)) IN ('YES', 'Y')","params":[]}
        return {"operation":"select","sql":f"SELECT s.usn, s.name, s.physically_handicapped, s.branch FROM students s WHERE UPPER(TRIM(s.physically_handicapped)) IN ('YES', 'Y') {order}","params":[]}

    # ── Distance from college ─────────────────────────────────────────────────
    # Free-text values ("7 km", "15km", "32.9 km") — CAST coerces the number.
    # Semantics: near/close to college < 50 km, far/distant > 100 km,
    # "between X and Y (km)" -> BETWEEN, plus explicit more/less-than numbers.
    _dist_expr = "CAST(s.distance_from_college AS UNSIGNED)"
    _dist_proj = "SELECT s.usn, s.name, s.distance_from_college, s.district, s.area_type FROM students s"
    _dist_notnull = "s.distance_from_college IS NOT NULL AND TRIM(s.distance_from_college) <> ''"
    _college_ctx = bool(re.search(r'\bcollege\b|\bcampus\b|\bnative\b|\bdistance\b|\bkm\b|\bkms\b|\bkilomet', eq))
    dist_gt      = re.search(r'\b(?:more\s+than|greater\s+than|above|over|>)\s*(\d+)\b', eq)
    dist_lt      = re.search(r'\b(?:less\s+than|below|under|<)\s*(\d+)\b', eq)
    dist_between = re.search(r'\bbetween\b\s*(\d+)\s*(?:km|kms|kilomet(?:er|re)s?)?\s*(?:and|&|to|-|–)\s*(\d+)\s*(?:km|kms|kilomet(?:er|re)s?)?', eq)
    near = bool(re.search(r'\bnear(?:er|ly|est)?\b|\bclose\b', eq)) and _college_ctx and not (dist_gt or dist_lt or dist_between)
    far  = bool(re.search(r'\bfarr?\b|\bdistant\b|\bfar\b|\bfarther\b|\bfurther\b', eq)) and _college_ctx and not (dist_gt or dist_lt or dist_between)
    if dist_between and _college_ctx:
        return {"operation":"select","sql":f"{_dist_proj} WHERE {_dist_notnull} AND {_dist_expr} BETWEEN %s AND %s {order}","params":[int(dist_between.group(1)), int(dist_between.group(2))]}
    if dist_lt and _college_ctx:
        return {"operation":"select","sql":f"{_dist_proj} WHERE {_dist_notnull} AND {_dist_expr} < %s {order}","params":[int(dist_lt.group(1))]}
    if dist_gt and _college_ctx:
        return {"operation":"select","sql":f"{_dist_proj} WHERE {_dist_notnull} AND {_dist_expr} > %s {order}","params":[int(dist_gt.group(1))]}
    if near:
        return {"operation":"select","sql":f"{_dist_proj} WHERE {_dist_notnull} AND {_dist_expr} < 50 {order}","params":[]}
    if far:
        return {"operation":"select","sql":f"{_dist_proj} WHERE {_dist_notnull} AND {_dist_expr} > 100 {order}","params":[]}

    # ── Contact numbers (mother / father / parent / guardian / emergency) ──────
    # Resolved through the intent-field layer so the ACTUAL stored heading is used
    # (real column or uploaded dynamic key), with an honest fallback: a
    # mother/father-specific number is preferred, and only when none exists do we
    # fall back to the general parent/guardian contact — always labeled as such,
    # never passed off as the mother's/father's own number. Bare "student phone"
    # is left to the generic projection below.
    try:
        import intent_fields
        contact_subject = intent_fields.detect_contact_subject(eq)
    except Exception:
        intent_fields = None
        contact_subject = None
    if (intent_fields is not None and contact_subject in ("mother", "father", "parent", "guardian", "emergency")
            and _is_bare_contact_listing(eq)):
        res = intent_fields.resolve_contact(contact_subject)
        if res.available:
            alias = re.sub(r"[^a-z0-9]+", "_", res.label.lower()).strip("_")
            note = res.note or ""
            proj = f"{res.sql} AS `{alias}`"
            where = f"WHERE {res.sql} IS NOT NULL AND TRIM({res.sql}) NOT IN ('', 'null', 'NULL', 'None')"
            body = {"operation": "select",
                    "sql": f"SELECT s.usn, s.name, {proj} FROM students s {where} {order}",
                    "params": [], "intent_contact": True}
            if note:
                body["message"] = note
            return body
        # Nothing suitable exists → explain, return no invented rows.
        return {"operation": "select",
                "sql": "SELECT s.usn, s.name FROM students s WHERE s.usn IN (NULL) ORDER BY s.usn ASC",
                "params": [], "intent_contact": True, "message": res.get("note") or
                "That contact field is not available for these students."}


    # ── Quota / Reservation ───────────────────────────────────────────────────
    if re.search(r'\bquota\b|\breservation\b', eq):
        generic_quota_words = {"details", "detail", "type", "category", "categories", "students", "student",
                               "show", "give", "list", "display", "get", "the", "a", "an", "all", "is", "are",
                               "quota", "quotas", "reservation", "reservations", "having", "with", "who"}
        quota_m = re.search(r'\b(?:quota|reservation)\s+(?:of\s+|is\s+|for\s+|as\s+)?([a-z]+(?:\s+[a-z]+)?)\b', eq)
        # Value-before-keyword ("defence quota", "sports quota", "horizon quota").
        quota_before_m = re.search(r'\b([a-z]+)\s+(?:quota|reservation)\b', eq)
        value = ""
        if quota_m:
            cand = quota_m.group(1).strip().lower()
            first = cand.split()[0] if cand else ""
            if first not in generic_quota_words:
                value = re.sub(r"\b(?:students?|having|with|who|the|in|from)\b.*$", "", cand).strip()
        if not value and quota_before_m:
            cand = quota_before_m.group(1).strip().lower()
            if cand not in generic_quota_words:
                value = cand
        if value:
            return {"operation":"select","sql":f"SELECT s.usn, s.name, s.quota FROM students s WHERE LOWER(s.quota) LIKE %s {order}","params":[f"%{value}%"]}
        return {"operation":"select","sql":f"SELECT s.usn, s.name, s.quota FROM students s WHERE NULLIF(TRIM(COALESCE(s.quota, '')), '') IS NOT NULL AND LOWER(TRIM(s.quota)) NOT LIKE 'not applicable%' {order}","params":[]}

    # ── SNQ Quota ─────────────────────────────────────────────────────────────
    if re.search(r'\bsnq\b', eq):
        if is_count:
            return {"operation":"select","sql":"SELECT COUNT(*) AS snq_students FROM students s WHERE UPPER(TRIM(s.snq_quota)) IN ('YES', 'Y')","params":[]}
        return {"operation":"select","sql":f"SELECT s.usn, s.name, s.snq_quota FROM students s WHERE UPPER(TRIM(s.snq_quota)) IN ('YES', 'Y') {order}","params":[]}

    return None



_RANK_CARDINAL = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
    "twenty": 20, "thirty": 30, "fifty": 50, "hundred": 100,
}
_RANK_KW = r"(?:top|first|last|bottom|lowest|highest|best|worst|fewest)"
_RANK_NOUN = r"(?:students?|records?|rows?|toppers?|performers?|engineers?|candidates?)"
_ALT_CARDINAL = "|".join(sorted(_RANK_CARDINAL, key=len, reverse=True))


def _detect_rank_limit(query: str) -> int | None:
    """Return N for a top/last-N ranking, whether N is a digit or a spelled word.

    Covers both "top 5 by CGPA" and "the five students with the highest CGPA".
    """
    m = re.search(rf"\b{_RANK_KW}\s+(\d+)\b", query)
    if m:
        return int(m.group(1))
    m = re.search(rf"\b{_RANK_KW}\s+({_ALT_CARDINAL})\b", query)
    if m:
        return _RANK_CARDINAL[m.group(1)]
    # spelled number *before* the noun: "five students with the highest ..."
    m = re.search(
        rf"\b(?:(?:the|about|around|only)\s+)?(\d+|{_ALT_CARDINAL})\s+{_RANK_NOUN}\b"
        rf"[^.?!;]*\b(?:with|by|having|who have|that have|who\s+are|are)?\s*(?:the)?\s*"
        rf"{_RANK_KW}\b",
        query,
    )
    if m:
        return int(m.group(1)) if m.group(1).isdigit() else _RANK_CARDINAL[m.group(1)]
    return None


def build_deterministic_student_query(nq: str) -> dict | None:
    """Build safe, parameterized SQL for common multi-attribute student filters."""
    text = (nq or "").strip()
    if not text:
        return None
    text = _repair_split_values(text)

    # ── Lifecycle intents (dropout / discontinued / readmission / rejoin) ──────
    # Runs BEFORE the fee/backlog/dynamic blocks so a query like "discontinued
    # students with fees pending" or "readmission pending" is not misrouted to the
    # fee handler (which matches the bare words 'pending'/'fees').
    lifecycle_result = _build_lifecycle_query(text)
    if lifecycle_result:
        lifecycle_result["lifecycle"] = True
        return lifecycle_result

    # ── Dynamic field queries (HK, distance, occupations, backlogs, etc.) ─────
    dyn_result = _build_dynamic_field_query(text)
    if dyn_result:
        return dyn_result

    # Repair misspelt grade abbreviations before any metric parsing so a typo in
    # the search bar ranks by the intended column instead of returning wrong rows.
    text = _fix_metric_typos(text)

    # ── Authoritative semester / branch extraction ────────────────────────────
    # Use deterministic extraction from rag_sql_generator (single source of
    # truth) so word ordinals ("first semester") and disambiguated 2-letter
    # branch codes ("is" / "me") are handled regardless of what other filters
    # appear. The VALUES are injected into the rest of this function's logic
    # (which already supports sem/branch/age/rural/parent/address/etc. combined
    # queries) rather than returning early — this way no filter is dropped.
    _tsem = _rag_detect_semester(text)
    _tbr  = _rag_extract_branches(text)

    query = text.casefold()

    # Parse academic-year queries such as "3rd year students" before semester
    # extraction so the year filter is applied instead of misclassifying the
    # ordinal as a semester.
    target_year = None
    year_word_map = {
        "first": 1, "second": 2, "third": 3, "fourth": 4,
        "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
    }
    for word, num in year_word_map.items():
        if re.search(rf"\b(?:in|from|of|for|studying\s+in|students?\s+(?:from|of|in))\s*(?:the\s+)?{word}\s*[-_\s]*year\b", query, re.I):
            target_year = num
            break
        if re.search(rf"\b(?:current\s+)?year\s*(?:is|=|:)?\s*{word}\b", query, re.I):
            target_year = num
            break
    if target_year is None:
        year_numeric_match = re.search(r"\b(?:in|from|of|for|studying\s+in|students?\s+(?:from|of|in))\s*(?:the\s+)?([1-4])(?:st|nd|rd|th)?\s*[-_\s]*year\b|\b(?:current\s+)?year\s*(?:is|=|:)?\s*([1-4])(?:st|nd|rd|th)?\b", query, re.I)
        if year_numeric_match:
            target_year = int(next(group for group in year_numeric_match.groups() if group is not None))

    where_clauses: list[str] = []
    params: list = []
    filter_conditions: list[dict] = []

    value_corrections: list[tuple[str, str, str]] = []

    def add_filter_condition(field: str, operator: str, value, sql: str, values=()) -> None:
        if any(existing["field"] == field and existing["sql"] == sql for existing in filter_conditions):
            return
        values, notes = _fuzzy_filter_value(field, operator, list(values))
        if notes:
            value_corrections.extend((field, asked, understood)
                                     for asked, understood in notes)
            if len(notes) == 1 and operator != "IN":
                value = notes[0][1]
        filter_conditions.append({
            "field": field,
            "operator": operator,
            "value": value,
            "sql": sql,
            "params": list(values),
        })
        where_clauses.append(sql)
        params.extend(values)

    def _correction_message() -> str:
        if not value_corrections:
            return ""
        return "Read as: " + ", ".join(
            f"'{asked}' → '{understood}' ({field})"
            for field, asked, understood in value_corrections) + "."

    selected_fields = ["s.usn", "s.name"]
    cgpa_expression = (
        "COALESCE((SELECT AVG(m.sgpa) FROM marks m WHERE m.usn=s.usn "
        "AND m.sgpa IS NOT NULL), s.cgpa)"
    )
    # Filters and rankings must judge the number the staff member sees in the
    # result grid; comparing the unrounded average made "cgpa at least 9.47"
    # reject the student whose CGPA row reads 9.47.
    cgpa_compared = f"ROUND({cgpa_expression}, 2)"
    is_count = bool(re.search(r"\b(?:count|how\s+many|number\s+of)\b", query))
    lateral_requested = bool(
        re.search(r"\blateral(?:[\s-]+entry)?\b|\bdirect\s+(?:second|2nd)\s+year\b", query)
        or re.search(r"\bLE\b", text, re.I)
    )
    count_and_list = is_count and bool(
        re.search(r"\b(?:and|also)\b.*\b(?:show|list|display|give|names?|usns?)\b", query)
    )
    missing_request = bool(
        re.search(
            r"\b(?:without|no|missing|does\s+not\s+have|do\s+not\s+have|don't\s+have|"
            r"does\s*n'?t\s+have|has\s+no|have\s+no|not\s+have|not\s+has|not\s+having|"
            r"haven'?t|hasn'?t|not\s+entered|null|empty|blank)\b",
            query,
        )
    )

    if lateral_requested:
        # Stored rows say "Lateral", the USN-derived fallback says "LATERAL ENTRY";
        # comparing to one literal answered "show lateral entry students" with zero
        # rows because no spelling matched both.
        lateral_expression = (
            "COALESCE(NULLIF(UPPER(TRIM(s.student_type)), ''), "
            "CASE WHEN UPPER(s.usn) REGEXP "
            "'^[0-9][A-Z]{2,3}[0-9]{2}[A-Z]{2,4}[0-9]{2,3}' "
            "AND CHAR_LENGTH(s.usn) BETWEEN 9 AND 13 "
            "AND RIGHT(UPPER(s.usn), 3) REGEXP '^[0-9]{3}' "
            "THEN CASE WHEN CAST(RIGHT(s.usn, 3) AS UNSIGNED) >= 400 "
            "THEN 'LATERAL ENTRY' ELSE 'REGULAR' END ELSE '' END)"
        )
        add_filter_condition(
            "student_type",
            "IN",
            "LATERAL ENTRY",
            f"{lateral_expression} IN (%s, %s)",
            ["LATERAL", "LATERAL ENTRY"],
        )
        selected_fields.append("s.student_type")

    # ── Plural name listing: "students named X" / "students called X" ──────────
    # The LLM resolves a lone name to exact equality, so "students named Rahul"
    # returns 0 when the stored full name is "Rahul Sharma". For an explicit
    # plural list request, match the name fragment with LIKE instead. Singular
    # lookups ("the student named X") are left to the existing resolver.
    _name_list_m = re.search(
        r"\bstudents\b[^.?!]*?\b(?:named|called|whose\s+name\s+is)\s+"
        r"([a-z][a-z .'-]*?)"
        r"(?=\s+(?:from|in|with|having|who|whose|and|branch|semester|sem|cgpa|sgpa|"
        r"aged?|age|blood|father|mother|gender|male|female|study|studying|of)\b|[?.!,;]|$)",
        query,
    )
    if _name_list_m:
        _nm = re.sub(r"\s+", " ", _name_list_m.group(1)).strip()
        if _nm and _nm not in {"the", "a", "an", "all", "every", "each"}:
            add_filter_condition(
                "name", "CONTAINS", _nm,
                "LOWER(TRIM(s.name)) LIKE %s", [f"%{_nm.lower()}%"],
            )

    # ── Backlogs / arrears as one filter among many ───────────────────────────
    _bk = _backlog_student_filter_sql(query)
    if _bk:
        _bk_sql, _bk_params = _bk
        add_filter_condition(
            "backlogs",
            "NOT_EXISTS" if _bk_sql.startswith("s.usn NOT IN") else "EXISTS",
            _bk_params[0] if _bk_params else "any backlog",
            _bk_sql, _bk_params,
        )

    # ── Universal field registry (covers ALL student fields + dynamically added ones) ──
    # Order matters: longer/more-specific patterns first to avoid partial matches.
    field_patterns = (
        ("cgpa", r"\bcgpa\b|\bcumulative\s+gpa\b"),
        ("sgpa", r"\bsgpa\b"),
        ("emergency_contact_number", r"\bemergency\s+(?:contact|phone|number)\b"),
        ("phone", r"\bphone(?:\s+numbers?)?\b|\bmobile(?:\s+numbers?)?\b|\bcontact\s+number\b"),
        ("email", r"\bemail\b|\bmail\b"),
        ("permanent_address", r"\bpermanent\s+address\b|\bhome\s+address\b"),
        ("current_address", r"\bcurrent\s+address\b|\blocal\s+address\b"),
        ("address", r"\baddress\b"),
        ("village", r"\bvillage\b|\bnative\s+(?:village|place)\b"),
        ("area_type", r"\barea\s+type\b|\brural[/\s]?urban\s+type\b"),
        ("area", r"\barea\b|\blocality\b"),
        ("region", r"\bregion\b"),
        ("taluk", r"\btaluk\b|\btehsil\b|\bmandal\b"),
        ("district", r"\bdistrict\b"),
        ("state", r"\bstate\b(?!\s+of\s+the\s+art)"),
        ("father_name", r"\bfather(?:['']s)?\s+name\b|\bdad(?:dy)?(?:['']s)?\s+name\b"),
        ("mother_name", r"\bmother(?:['']s)?\s+name\b|\bmom(?:my)?(?:['']s)?\s+name\b"),
        ("blood_group", r"\bblood\s*(?:group|type)\b|ರಕ್ತದ\s*ಗುಂಪು"),
        ("dob", r"\b(?:date\s+of\s+birth|dob|birth\s+date|birthdate)\b"),
        ("gender", r"\bgender\b|\bsex\b(?!ual)"),
        ("religion", r"\breligion\b"),
        ("caste", r"\bcaste\b|\bcast\b"),
        ("aadhar_no", r"\baadhar\b|\baadhaar\b|\buid\b"),
        ("branch", r"\bbranch\b|\bdepartment\b|\bdept\b|\bstream\b"),
        ("current_sem", r"\bcurrent\s+sem(?:ester)?\b"),
        ("year_of_joining", r"\byear\s+of\s+joining\b|\badmission\s+year\b|\bjoining\s+year\b"),
        ("status", r"\bstatus\b"),
        ("division", r"\bdivision\b|\bsection\b"),
        ("domain", r"\bdomain\b"),
    )
    requested_data_fields = []
    for column, pattern in field_patterns:
        if not re.search(pattern, query, re.I):
            continue
        if column == "area" and re.search(r"\b(?:rural|urban)\b", query, re.I):
            continue
        requested_data_fields.append((column, pattern))
    requested_data_field = requested_data_fields[0] if requested_data_fields else None

    def _build_missing_sql(column: str) -> str:
        """Build SQL expression for 'field is missing' covering NULL and empty string."""
        _numeric_cols = {"cgpa", "sgpa", "dob", "year_of_joining", "current_sem", "admission_year", "current_year", "roll_number"}
        if column in _numeric_cols:
            return f"s.`{column}` IS NULL"
        return f"NULLIF(TRIM(COALESCE(s.`{column}`, '')), '') IS NULL"

    def _build_present_sql(column: str) -> str:
        """Build SQL expression for 'field has data' covering non-NULL and non-empty."""
        _numeric_cols = {"cgpa", "sgpa", "dob", "year_of_joining", "current_sem", "admission_year", "current_year", "roll_number"}
        if column in _numeric_cols:
            return f"s.`{column}` IS NOT NULL"
        return f"NULLIF(TRIM(COALESCE(s.`{column}`, '')), '') IS NOT NULL"

    if missing_request and requested_data_field:
        column, _ = requested_data_field
        skip_missing = False
        if column == "blood_group" and re.search(
            r"(?<![A-Z0-9])(AB|A|B|O)\s*(\+|-|plus|positive|pos|negative|neg|-)?(?![A-Z])",
            query,
            re.I,
        ):
            skip_missing = True
        elif column in ("cgpa", "sgpa") and re.search(
            r"\b(?:cgpa|sgpa|gpa)\s*(?:is\s+)?(?:(?:not\s+)?(?:above|over|greater|below|under|less|at\s+least|at\s+most|not\s+below|not\s+above|>=|<=|>|<|=))?\s*(\d+(?:\.\d+)?)",
            query,
            re.I,
        ):
            skip_missing = True

        if not skip_missing:
            if column == "cgpa":
                missing_cgpa_sql = (
                    "(NOT EXISTS (SELECT 1 FROM marks m WHERE m.usn=s.usn AND m.sgpa IS NOT NULL) "
                    "AND s.cgpa IS NULL)"
                )
                add_filter_condition("cgpa", "MISSING", None, missing_cgpa_sql)
                selected_fields.append(f"ROUND({cgpa_expression}, 2) AS cgpa")
            elif column == "sgpa":
                missing_sgpa_sql = "NOT EXISTS (SELECT 1 FROM marks m WHERE m.usn=s.usn AND m.sgpa IS NOT NULL)"
                add_filter_condition("sgpa", "MISSING", None, missing_sgpa_sql)
                selected_fields.append("(SELECT AVG(m.sgpa) FROM marks m WHERE m.usn=s.usn AND m.sgpa IS NOT NULL) AS sgpa")
            else:
                missing_sql = _build_missing_sql(column)
                add_filter_condition(column, "MISSING", None, missing_sql)
                selected_fields.append(f"s.`{column}`")
    elif requested_data_field and re.search(
        r"\b(?:which|who|show|list|students?|whose)\b.*\b(?:have|has|with|available|present|entered|recorded|provided)\b",
        query,
    ):
        column, field_pattern = requested_data_field
        # "students of Have district" is a mistyped place value, but "Have" also
        # spells the verb the presence test below looks for, and answering it as
        # "students who have a district" silently returns 58 of 65 students. A
        # word sitting between a place preposition and the column keyword is a
        # value; the fuzzy value resolver handles it. "students who have district"
        # (no preposition) keeps its presence meaning.
        if re.search(
            rf"\b(?:of|from|in|at)\s+[a-z][a-z'\-]*\s+(?:{field_pattern})\b",
            query, re.I,
        ):
            skip_present = True
        else:
            skip_present = False
        if column == "blood_group" and re.search(
            r"(?<![A-Z0-9])(AB|A|B|O)\s*(\+|-|plus|positive|pos|negative|neg|-)?(?![A-Z])",
            query,
            re.I,
        ):
            skip_present = True
        elif column in ("cgpa", "sgpa") and re.search(
            r"\b(?:cgpa|sgpa|gpa)\s*(?:is\s+)?(?:(?:not\s+)?(?:above|over|greater|below|under|less|at\s+least|at\s+most|not\s+below|not\s+above|>=|<=|>|<|=))?\s*(\d+(?:\.\d+)?)",
            query,
            re.I,
        ):
            skip_present = True

        if not skip_present:
            if column == "cgpa":
                present_cgpa_sql = (
                    "(EXISTS (SELECT 1 FROM marks m WHERE m.usn=s.usn AND m.sgpa IS NOT NULL) "
                    "OR s.cgpa IS NOT NULL)"
                )
                add_filter_condition("cgpa", "PRESENT", None, present_cgpa_sql)
                selected_fields.append(f"ROUND({cgpa_expression}, 2) AS cgpa")
            elif column == "sgpa":
                present_sgpa_sql = "EXISTS (SELECT 1 FROM marks m WHERE m.usn=s.usn AND m.sgpa IS NOT NULL)"
                add_filter_condition("sgpa", "PRESENT", None, present_sgpa_sql)
                selected_fields.append("(SELECT AVG(m.sgpa) FROM marks m WHERE m.usn=s.usn AND m.sgpa IS NOT NULL) AS sgpa")
            else:
                add_filter_condition(column, "PRESENT", None, _build_present_sql(column))
                selected_fields.append(f"s.`{column}`")

    parent_stop = (
        r"(?=\s+(?:students?|from|in|with|and|or|age|aged|years?\s+old|blood|branch|"
        r"department|semester|sem|cgpa|rural|urban|male|female|without|no|missing|"
        r"phone|mobile|emergency|email|address|show|list|count)\b|[,;.!?]|$)"
    )
    parent_pattern = re.compile(
        r"\b(?P<parent>father|mother)(?:['’]s)?(?:\s+name)?\s*"
        r"(?:is|=|named|called)?\s*(?P<value>.+?)" + parent_stop,
        re.I,
    )
    for match in parent_pattern.finditer(text):
        field = "father_name" if match.group("parent").casefold() == "father" else "mother_name"
        parent_name = match.group("value").strip(" .'-,;:")
        # A bare projection item ("show father name and cgpa") leaves only punctuation
        # or a filler after "father name"; treat it as a projection, not a value filter.
        if not re.search(r"[^\W\d_]", parent_name, re.UNICODE):
            continue
        # "<field> of <subject>" ("father name of Ravi") is a lookup-by-name
        # projection, not "father_name = 'of ravi'"; let the name handler take it.
        _lead = parent_name.split()[0].casefold() if parent_name.split() else ""
        if _lead in {"of", "for", "the", "is", "in", "to", "all", "and", "a", "an", "that", "which"}:
            continue
        if parent_name.casefold() in {"available", "present", "entered", "recorded", "provided"}:
            add_filter_condition(
                field,
                "PRESENT",
                None,
                f"NULLIF(TRIM(COALESCE(s.{field}, '')), '') IS NOT NULL",
            )
            selected_fields.append(f"s.{field}")
            continue
        if parent_name and parent_name.casefold() not in {
            "name", "is", "the", "a", "an", "of", "students", "student", "missing",
            "without", "no", "null", "empty", "blank", "available", "present",
            "entered", "recorded", "provided", "not",
        }:
            preceding_clause = text[max(0, match.start() - 24):match.start()]
            field_is_negated = bool(re.search(
                r"\b(?:without|no|missing|does\s+not\s+have|don't\s+have)\s*$",
                preceding_clause, re.I,
            ))
            if not field_is_negated:
                exact_match = not bool(re.search(
                    r"\b(?:contains?|includes?|partial(?:ly)?)\b",
                    match.group(0), re.I
                ))
                if exact_match:
                    add_filter_condition(field, "EQUALS", parent_name, f"LOWER(TRIM(s.{field})) = LOWER(TRIM(%s))", [parent_name])
                else:
                    add_filter_condition(field, "CONTAINS", parent_name, f"LOWER(TRIM(s.{field})) LIKE LOWER(%s)", [f"%{parent_name}%"])
                selected_fields.append(f"s.{field}")

    blood_context = bool(re.search(r"blood|ರಕ್ತ", query))
    blood_pattern = re.compile(
        r"(?<![A-Z0-9])(AB|A|B|O)\s*(\+|-|plus|positive|pos|negative|neg)(?![A-Z])",
        re.I,
    )
    blood_values = []
    for match in blood_pattern.finditer(text):
        group, suffix = match.groups()
        sign = "+" if suffix.casefold() in {"+", "plus", "positive", "pos"} else "-"
        blood_values.append(group.upper() + sign)
    if blood_values and (blood_context or re.search(r"\bstudents?\b", query)):
        blood_values = list(dict.fromkeys(blood_values))
        blood_expression = (
            "REPLACE(REPLACE(REPLACE(UPPER(COALESCE(s.blood_group, '')), "
            "'POSITIVE', '+'), 'NEGATIVE', '-'), ' ', '')"
        )
        placeholders = ", ".join(["%s"] * len(blood_values))
        # `query` is casefolded, so match blood-group letters case-insensitively.
        negated = bool(re.search(
            r"\b(?:not|don't|doesn't|without)\b.{0,24}"
            r"(?:blood(?:\s*(?:group|type))?|(?:AB|A|B|O)\s*(?:\+|-|positive|negative))",
            query, re.I,
        ))
        if negated:
            blood_sql = (
                f"({blood_expression} NOT IN ({placeholders}) AND "
                f"NULLIF(TRIM(COALESCE(s.blood_group, '')), '') IS NOT NULL)"
            )
        else:
            blood_sql = f"{blood_expression} IN ({placeholders})"
        add_filter_condition(
            "blood_group", "NOT_IN" if negated else "IN", blood_values, blood_sql, blood_values
        )
        selected_fields.append("s.blood_group")

    # Rural/Urban filter — use s.area_type column (authoritative, set during import)
    # NEVER fall back to address REGEXP — area_type is always set correctly on upload.
    for area_type in ("RURAL", "URBAN"):
        if re.search(rf"\bnot\b.{{0,20}}\b{area_type.lower()}\b", query):
            add_filter_condition(
                "rural_status", "NOT_EQUALS", area_type,
                "UPPER(COALESCE(s.area_type, '')) != %s",
                [area_type],
            )
            selected_fields.extend(("s.area_type", "s.village", "s.region"))
        elif re.search(rf"\b{area_type.lower()}\b", query):
            add_filter_condition(
                "rural_status", "EQUALS", area_type,
                "UPPER(COALESCE(s.area_type, '')) = %s",
                [area_type],
            )
            selected_fields.extend(("s.area_type", "s.village", "s.region"))

    # Both genders named side by side ("male and female students") is the union.
    # Named as two separate conditions ("male students … who are female") the
    # request cannot be satisfied: silently keeping only the last gender read
    # every such question as its opposite.
    _GENDER_WORDS = (
        ("FEMALE", r"female|females|girls?|women|woman|ladies"),
        ("MALE", r"male|males|boys?|men"),
    )
    gender_hits = sorted(
        [(match.start(), kind)
         for kind, pattern in _GENDER_WORDS
         for match in re.finditer(rf"\b(?:{pattern})\b", query)]
    )
    if gender_hits:
        selected_fields.append("s.gender")
        kinds = {kind for _pos, kind in gender_hits}
        if len(kinds) > 1:
            paired = any(kind != gender_hits[0][1] and pos - gender_hits[0][0] <= 16
                         for pos, kind in gender_hits[1:])
            if not paired:
                raise HTTPException(
                    400,
                    "This request filters on two different genders at once, which no "
                    "student can satisfy. Please ask for one gender at a time.",
                )
            add_filter_condition(
                "gender", "IN", ["FEMALE", "MALE"],
                "UPPER(COALESCE(s.gender, '')) IN (%s, %s)", ["FEMALE", "MALE"],
            )
        else:
            kind = gender_hits[0][1]
            add_filter_condition("gender", "EQUALS", kind,
                                 "UPPER(COALESCE(s.gender, '')) = %s", [kind])

    # ── Religion / Caste / Category — value-aware so everyday staff phrasing
    # ("muslim students", "vokkaliga caste", "hindu relegion", "2A category")
    # filters correctly instead of being dropped or sent to the LLM. Spelling
    # variants are tolerated and common synonyms are expanded (Muslim ↔ Islam).
    _RELISSION_SYNONYMS = {
        "muslim": ("muslim", "islam"), "islam": ("muslim", "islam"),
        "hindu": ("hindu", "hindhu"), "christian": ("christian",),
        "jain": ("jain",), "sikh": ("sikh",),
    }
    _religion_known = {
        "hindu", "hindhu", "muslim", "islam", "christian", "jain", "jains",
        "jain digambar", "lingayatha", "sikh", "buddhist",
    }
    rel_m = re.search(
        r"\b(?:religion|relegion|religon|faith)\s*(?:is|:|=|of)?\s*([a-z][a-z ]*)|"
        r"\b([a-z]+(?:\s+[a-z]+)?)\s*(?:religion|relegion|religon|faith)\b",
        query,
    )
    rel_value = ""
    if rel_m:
        rel_value = next((g for g in rel_m.groups() if g), "").strip()
        rel_value = re.sub(r"^(?:list|show|display|all|the|a|an|get|find|give|students?)\s+", "", rel_value)
        rel_value = re.sub(r"\b(?:students?|in|the|a|an|of|and|with|who|whose|cate?gory)\b.*$", "", rel_value).strip()
    # Bare religion word without the "religion" keyword ("list muslim students").
    if not rel_value:
        for w in _RELISSION_SYNONYMS:
            if re.search(rf"\b{re.escape(w)}\b", query):
                rel_value = w
                break
    if rel_value and rel_value in _religion_known | set(_RELISSION_SYNONYMS):
        variants = _RELISSION_SYNONYMS.get(rel_value, (rel_value,))
        conds = " OR ".join(
            "LOWER(COALESCE(s.religion,'')) LIKE %s" for _ in variants)
        rel_params = [f"%{v}%" for v in variants]
        add_filter_condition("religion", "CONTAINS", rel_value, f"({conds})", rel_params)
        # The SQL matches any synonym variant; tell the row verifier the same so a
        # stored spelling variant ("Hindhu") is not rejected against "hindu".
        filter_conditions[-1]["any_of"] = list(variants)
        if "s.religion" not in selected_fields:
            selected_fields.append("s.religion")

    cast_m = re.search(
        r"\b(?:caste|cast|community|sub[-\s]?caste)\s*(?:is|:|=|of)?\s*([a-z][a-z ]*)|"
        r"\b([a-z][a-z ]*?)\s*(?:caste|community)\b",
        query,
    )
    cast_value = ""
    if cast_m:
        raw_cast = next((g for g in cast_m.groups() if g), "").strip()
        # The capture is anchored at the earliest word of the sentence, so it
        # usually still holds the request itself ("list students of general").
        # Removing only a leading command word left "students of general" and the
        # trailing cleanup then emptied it, so the caste filter silently vanished.
        _cast_words = [w for w in re.split(r"\s+", raw_cast) if w.casefold() not in {
            "list", "show", "display", "get", "find", "give", "print", "tell", "me",
            "all", "the", "a", "an", "of", "for", "to", "in", "is", "are", "and",
            "or", "with", "who", "whose", "which", "students", "student", "having",
            "has", "have", "category", "community", "backlog", "fees", "fee"}]
        cast_value = " ".join(_cast_words).strip()
    _caste_generic = {"", "is", "the", "a", "an", "of", "what", "which", "list", "show", "all", "backlog", "quota"}
    if cast_value and cast_value not in _caste_generic:
        add_filter_condition(
            "caste", "CONTAINS", cast_value,
            "LOWER(CONCAT_WS(' ', COALESCE(s.caste,''), COALESCE(s.sub_caste,''))) LIKE %s",
            [f"%{cast_value}%"],
        )
        selected_fields.extend(("s.caste", "s.sub_caste"))

    # ── Reservation / cast category ("2A", "3B", "SC", "ST", "Cat-1", ...) ────
    # Handled separately from caste because the values overlap ("SC" can be a
    # category) and staff say "category" explicitly. Single-token categories are
    # matched tolerantly (case + surrounding text).
    cat_m = re.search(
        r"\bcategory\b\s*(?:is|:|=|of|in|as)?\s*([a-z0-9][a-z0-9\-]*)|"
        r"\b([a-z0-9][a-z0-9\-]*)\s+category\b",
        query,
    )
    cat_value = ""
    if cat_m:
        cat_value = next((g for g in cat_m.groups() if g), "").strip()
    _cat_generic = {"", "the", "a", "an", "is", "of", "in", "what", "which",
                    "list", "show", "all", "students", "student", "reservation",
                    "category", "wise", "based", "and"}
    if cat_value and cat_value not in _cat_generic:
        add_filter_condition(
            "category", "CONTAINS", cat_value,
            "LOWER(TRIM(COALESCE(s.category, ''))) LIKE %s", [f"%{cat_value}%"],
        )
        if "s.category" not in selected_fields:
            selected_fields.append("s.category")


    # ── Status (active / graduated / inactive) ────────────────────────────────
    status_value = None
    if re.search(r"\bgraduated\b|\balumni\b|\bpassed[\s-]?out\b", query):
        status_value = "GRADUATED"
    elif re.search(r"\bactive\b|\bcurrent\s+students?\b|\benrolled\b", query):
        status_value = "ACTIVE"
    elif re.search(r"\binactive\b", query):
        status_value = "INACTIVE"
    if status_value:
        add_filter_condition("status", "EQUALS", status_value, "UPPER(COALESCE(s.status, '')) = %s", [status_value])
        selected_fields.append("s.status")

    # ── Fee status next to other filters ──────────────────────────────────────
    # A fee-only question is answered by the fee query above. As soon as the
    # question also names a district, gender, caste or score, the fee class
    # becomes one more condition here, so no part of the request is dropped.
    fee_target = _fee_status_target(query) if _FEE_TOPIC_RE.search(query) else None
    if fee_target:
        fee_usns = _fee_status_usns(fee_target)
        if fee_usns:
            _fee_ph = ", ".join(["%s"] * len(fee_usns))
            add_filter_condition("fee_status", "IN", fee_target,
                                 f"s.usn IN ({_fee_ph})", fee_usns)
        else:
            add_filter_condition("fee_status", "EQUALS", fee_target, "1 = 0")

    # ── DOB / birth year / month ──────────────────────────────────────────────
    _MONTHS = ("january", "february", "march", "april", "may", "june", "july",
               "august", "september", "october", "november", "december")
    dob_year_range = re.search(
        r"\bborn\s+(?:between|from|during|in)\s+(\d{4})\s+(?:and|to|through|up\s+to|-|–)\s+(\d{4})\b",
        query,
    )
    dob_year = re.search(r"\bborn\s+in\s+(\d{4})\b", query)
    dob_after = re.search(r"\bborn\s+(?:after|since|from)\s+(?:\d{1,2}\s+\w+\s+)?(\d{4})\b", query)
    dob_before = re.search(r"\bborn\s+(?:before|until|upto|up\s+to)\s+(?:\d{1,2}\s+\w+\s+)?(\d{4})\b", query)
    dob_month = next(
        (i + 1 for i, m in enumerate(_MONTHS) if re.search(rf"\bborn\s+in\s+{m}\b", query)),
        None,
    )
    if dob_year_range:
        low, high = sorted((int(dob_year_range.group(1)), int(dob_year_range.group(2))))
        add_filter_condition("dob", "YEAR_BETWEEN", [low, high], "YEAR(s.dob) BETWEEN %s AND %s", [low, high])
        selected_fields.append("s.dob")
    elif dob_year:
        year = int(dob_year.group(1))
        add_filter_condition("dob", "YEAR_EQUALS", year, "YEAR(s.dob) = %s", [year])
        selected_fields.append("s.dob")
    elif dob_after:
        year = int(dob_after.group(1))
        add_filter_condition("dob", "YEAR_GREATER_EQUAL", year, "YEAR(s.dob) >= %s", [year])
        selected_fields.append("s.dob")
    elif dob_before:
        year = int(dob_before.group(1))
        add_filter_condition("dob", "YEAR_LESS_EQUAL", year, "YEAR(s.dob) <= %s", [year])
        selected_fields.append("s.dob")
    elif dob_month:
        add_filter_condition("dob", "MONTH_EQUALS", dob_month, "MONTH(s.dob) = %s", [dob_month])
        selected_fields.append("s.dob")

    # ── Joining year / batch (distinct from DOB "born in") ────────────────────
    join_year = re.search(
        r"\b(?:joined|joining|join|admitted|admission|enrolled|enrolment|enrollment)\b"
        r"\s*(?:in|on|during|year)?\s*(\d{4})\b",
        query,
    ) or re.search(r"\byear\s+of\s+(?:joining|admission)\b\s*(?:is|=|:)?\s*(\d{4})\b", query) \
       or re.search(r"\bbatch\s*(?:of)?\s*(\d{4})\b", query) \
       or re.search(r"\b(\d{4})\s*(?:batch|intake|admission|joining)\b", query) \
       or re.search(r"\bwho\s+(?:joined|admitted|enrolled)\s+in\s+(\d{4})\b", query) \
       or re.search(r"\b(?:students|student)\s+of\s+(\d{4})\b", query) \
       or re.search(r"\bshow\s+(\d{4})\s+(?:students|student)\b", query)
    if join_year:
        yr = int(join_year.group(1))
        add_filter_condition("admission_year", "EQUALS", yr, "s.admission_year = %s", [yr])
        selected_fields.append("s.year_of_joining")
        selected_fields.append("s.admission_year")

    # Every branch spelling maps to its sibling spellings. Derived from the
    # single source of truth in rag_sql_generator; the hand-written copy of this
    # table used to omit "CIV", so "student in CIV" leaked a bogus
    # address LIKE '%civ%' filter alongside the correct branch filter and
    # answered with zero students.
    branch_aliases: dict[str, tuple[str, ...]] = {}
    for _alias_group in _BRANCH_NORMALIZATION.values():
        for _alias in _alias_group:
            branch_aliases[_alias] = _alias_group
    # Words that make up a department name ("electronics and communication
    # engineering"). A place filter may never be built out of them: the split on
    # "and" left "communication engineering", which matched no address and
    # answered the whole EC department with zero students.
    _branch_vocab = {word for _group in _BRANCH_NORMALIZATION.values()
                     for _alias in _group
                     for word in re.findall(r"[a-z]+", str(_alias).lower())}
    branches = []

    # 1. Multi-word and explicit branch names (case-insensitive)
    if re.search(r"\bcomputer\s+science\b", query):
        branches.append("CS")
    if re.search(r"\binformation\s+science\b", query):
        branches.append("IS")
    if re.search(r"\belectronics(?:\s*(?:and|&)\s*communication)?\b", query):
        branches.append("EC")
    if re.search(r"\bmechanical(?:\s+engineering)?\b", query):
        branches.append("ME")
    if re.search(r"\bcivil(?:\s+engineering)?\b", query):
        branches.append("CV")
    if re.search(r"\b(?:ai\s*(?:and|&)?\s*ml|artificial\s+intelligence)\b", query):
        branches.append("AIML")
    if re.search(r"\belectrical(?:\s+engineering)?\b", query):
        branches.append("EEE")

    # 2. Unambiguous 3-4 letter acronyms (case-insensitive)
    if re.search(r"\bcse\b", query) and "CS" not in branches:
        branches.append("CS")
    if re.search(r"\bise\b", query) and "IS" not in branches:
        branches.append("IS")
    if re.search(r"\bece\b", query) and "EC" not in branches:
        branches.append("EC")
    if re.search(r"\bmech\b", query) and "ME" not in branches:
        branches.append("ME")
    if re.search(r"\bcivil\b", query) and "CV" not in branches:
        branches.append("CV")
    if re.search(r"\baiml\b", query) and "AIML" not in branches:
        branches.append("AIML")
    if re.search(r"\beee\b", query) and "EEE" not in branches:
        branches.append("EEE")

    # 3. 2-letter non-conflicting branch codes (case-insensitive)
    if re.search(r"\bcs\b", query) and "CS" not in branches:
        branches.append("CS")
    if re.search(r"\bec\b", query) and "EC" not in branches:
        branches.append("EC")
    if re.search(r"\bcv\b", query) and "CV" not in branches:
        branches.append("CV")

    # 4. Potentially conflicting words: 'me' and 'is'
    # 'me' branch only if explicitly 'me branch' / 'branch me' or uppercase 'ME' in student/branch/sem context
    if "ME" not in branches:
        if re.search(r"\bme\s+(?:branch|dept|department|stream)\b|\b(?:branch|dept|department|stream)\s+me\b", query):
            branches.append("ME")
        elif re.search(r"\bME\b", text) and not re.search(r"\b(?:give|show|tell|find|get|list|let|help|for|to|with)\s+ME\b", text, re.I):
            if re.search(r"\bME\s+(?:students?|student|branch|sem|semester)\b|\b(?:sem|semester)\s+\d+\s+ME\b", text):
                branches.append("ME")

    # 'is' branch only if explicitly 'is branch' / 'branch is' or uppercase 'IS' in student/branch/sem context
    if "IS" not in branches:
        if re.search(r"\bis\s+(?:branch|dept|department|stream)\b|\b(?:branch|dept|department|stream)\s+is\b", query):
            branches.append("IS")
        elif re.search(r"\bIS\b", text) and not re.search(r"\b(?:which|what|who|where|how|there|this|that|he|she|it)\s+IS\b", text, re.I):
            if re.search(r"\bIS\s+(?:students?|student|branch|sem|semester)\b|\b(?:sem|semester)\s+\d+\s+IS\b", text):
                branches.append("IS")

    # Deduplicate while preserving order
    branches = list(dict.fromkeys(branches))

    # ── Branch filtering ──────────────────────────────────────────────────────
    # Use authoritative branch extraction output (_tbr) from rag_sql_generator
    # rather than re-extracting inline. This keeps normalization rules (CS↔CSE,
    # IS↔ISE, homograph disambiguation for "is"/"me", etc.) in ONE place.
    branches = list(_tbr) if _tbr else []

    if branches:
        branch_conditions = []
        for branch in branches:
            aliases = _rag_normalize_branch(branch) or branch_aliases.get(branch, (branch,))
            aliases = tuple(dict.fromkeys(a for a in aliases if a))
            branch_expression = (
                "UPPER(COALESCE(NULLIF(TRIM(s.branch), ''), "
                + _USN_BRANCH_CODE_SQL + ", ''))"
            )
            branch_conditions.append((
                branch_expression + " IN (" + ", ".join(["%s"] * len(aliases)) + ")",
                aliases,
            ))

        branch_sql = " OR ".join(condition for condition, _ in branch_conditions)
        branch_params = [value for _, values in branch_conditions for value in values]
        if len(branch_conditions) == 1:
            branch_sql = branch_conditions[0][0]
        else:
            branch_sql = "(" + branch_sql + ")"
        add_filter_condition("branch", "IN", branches, branch_sql, branch_params)

        if "s.branch" not in selected_fields:
            selected_fields.append("s.branch")

    # ── Semester filtering (EXACT equality, authoritative from _tsem) ─────────
    target_semester = _tsem
    _sgpa_metric = bool(re.search(r"\bsgpa\b", query))
    _cgpa_metric = bool(re.search(r"\bcgpa\b", query))
    # When the query asks for a SPECIFIC-semester SGPA, that semester names the
    # marks semester, not the student's current semester. Forcing current_sem to
    # it over-constrains the result (e.g. a 2023 cohort is no longer IN its 3rd
    # semester, yet still HAS 3rd-semester marks). CGPA/ordinary "in Nth sem"
    # queries keep the current_sem filter.
    if target_semester is not None and not (_sgpa_metric and not _cgpa_metric):
        current_sem_sql, _ = _current_academic_fields_sql()
        add_filter_condition("current_sem", "EQUALS", target_semester, f"({current_sem_sql}) = %s", [target_semester])
        selected_fields = [field for field in selected_fields if field != "s.current_sem"]
        selected_fields.append(f"{current_sem_sql} AS current_sem")

    if target_year is not None:
        _, current_year_sql = _current_academic_fields_sql()
        add_filter_condition("current_year", "EQUALS", target_year, f"({current_year_sql}) = %s", [target_year])
        selected_fields = [field for field in selected_fields if field != "s.current_year"]
        selected_fields.append(f"{current_year_sql} AS current_year")

    # ── SGPA vs CGPA detection ────────────────────────────────────────────────
    sgpa_explicit = bool(re.search(r"\bsgpa\b", query))
    cgpa_explicit = bool(re.search(r"\bcgpa\b", query))
    gpa_context = bool(re.search(r"\b(?:cgpa|sgpa|gpa)\b", query))
    sem_sgpa_context = bool(target_semester is not None and sgpa_explicit)
    age_context = bool(
        re.search(r"\bage(?:d|s)?\b|years?\s+old|year[- ]old|older|younger|ವರ್ಷದ", query)
    )
    # "How many students are 21?" — bare "<verb> <number>" age, only when no other
    # numeric field (semester/cgpa/dob/batch) is the subject of the query.
    bare_age = bool(re.search(r"\b(?:are|is|were|was)\s+\d{1,3}\b", query)) and not re.search(
        r"\b(?:semester|sem|cgpa|sgpa|gpa|section|division|born|batch)\b", query)
    age_context = age_context or bare_age
    age_expression = "TIMESTAMPDIFF(YEAR, s.dob, CURDATE())"
    age_range = re.search(r"\bbetween\s+(\d{1,3})\s+(?:and|to|-)\s+(\d{1,3})\b", query)
    age_or = re.search(r"\b(\d{1,3})\s+or\s+(\d{1,3})\b", query) if age_context else None
    age_operator = _comparison_match(query, r"age(?:d|s)?|years?\s+old") if age_context else None
    age_value = re.search(r"\b(?:age|aged)\s*(?:is|=|of)?\s*(\d{1,3})\b", query) if age_context else None
    if not age_value and age_context:
        age_value = re.search(r"\b(\d{1,3})\s*(?:-?years?\s+old|-year-old)\b", query)
    if not age_value and bare_age:
        age_value = re.search(r"\b(?:are|is|were|was)\s+(\d{1,3})\b", query)

    if age_range and not gpa_context and (age_context or re.search(r"\bstudents?\b", query)):
        low, high = sorted((int(age_range.group(1)), int(age_range.group(2))))
        add_filter_condition("age", "BETWEEN", [low, high], f"{age_expression} BETWEEN %s AND %s", [low, high])
        selected_fields.append(f"{age_expression} AS age")
    elif age_or:
        ages = sorted({int(age_or.group(1)), int(age_or.group(2))})
        add_filter_condition("age", "IN", ages, f"{age_expression} IN ({', '.join(['%s'] * len(ages))})", ages)
        selected_fields.append(f"{age_expression} AS age")
    elif age_operator:
        operator, raw, match = age_operator
        age = int(raw)
        # "aged 18 or older" carries no operator before the number; the linking
        # words after it decide whether the bound is inclusive.
        following = query[match.end():match.end() + 24]
        if operator == "=":
            if re.search(r"\b(?:or|and)\s+(?:above|older|over|more|greater|less)\b", following):
                operator = ">="
            elif re.search(r"\b(?:or|and)\s+(?:below|younger|under|less|fewer)\b", following):
                operator = "<="
        if operator == "NOT_EQUALS":
            operator = "!="
        if operator not in (">", ">=", "<", "<=", "=", "!="):
            operator = "="
        age_name = {">": "GREATER_THAN", ">=": "GREATER_EQUAL", "<": "LESS_THAN",
                    "<=": "LESS_EQUAL", "=": "EQUALS", "!=": "NOT_EQUALS"}[operator]
        add_filter_condition("age", age_name, age, f"{age_expression} {operator} %s", [age])
        selected_fields.append(f"{age_expression} AS age")
    elif age_value:
        age = int(age_value.group(1))
        following_text = query[age_value.end():age_value.end() + 24]
        operator = ">=" if re.search(r"\b(?:or\s+)?(?:above|older|over)\b", following_text) else "="
        add_filter_condition("age", "GREATER_EQUAL" if operator == ">=" else "EQUALS", age, f"{age_expression} {operator} %s", [age])
        selected_fields.append(f"{age_expression} AS age")

    # Semester-specific SGPA expression (per-semester marks.sgpa for target_semester)
    if sem_sgpa_context and target_semester is not None:
        sgpa_per_sem_expression = (
            "(SELECT m.sgpa FROM marks m WHERE m.usn=s.usn "
            "AND m.semester=%s AND m.sgpa IS NOT NULL LIMIT 1)"
        )
    else:
        sgpa_per_sem_expression = None

    cgpa_missing = bool(
        re.search(
            r"\b(?:without|no|missing|not\s+have)\s+(?:any\s+|a\s+)?(?:cgpa|cumulative\s+gpa)\b|"
            r"\b(?:cgpa|cumulative\s+gpa)\s+(?:is\s+)?(?:missing|unavailable|null|not\s+entered)\b",
            query,
        )
    )
    if cgpa_missing:
        add_filter_condition("cgpa", "MISSING", None, f"{cgpa_compared} IS NULL")
        selected_fields.append(f"ROUND({cgpa_expression}, 2) AS cgpa")
    elif gpa_context:
        # Decide which GPA metric to filter on
        use_per_sem_sgpa = bool(sem_sgpa_context)
        use_cgpa_only = bool(cgpa_explicit) or (not sgpa_explicit and not use_per_sem_sgpa)

        gpa_between = re.search(
            r"\b(?:cgpa|sgpa|gpa)\b\s+between\s+(\d+(?:\.\d+)?)\s+(?:and|to)\s+(\d+(?:\.\d+)?)",
            query,
        )
        if gpa_between:
            low, high = sorted((float(gpa_between.group(1)), float(gpa_between.group(2))))
            if use_per_sem_sgpa and target_semester is not None:
                sgpa_sql = (
                    f"(EXISTS (SELECT 1 FROM marks m WHERE m.usn=s.usn AND m.semester=%s AND m.sgpa IS NOT NULL) "
                    f"AND {sgpa_per_sem_expression} BETWEEN %s AND %s)"
                )
                add_filter_condition("sgpa", "BETWEEN", [low, high], sgpa_sql, [target_semester, target_semester, low, high])
                selected_fields.append(f"ROUND({sgpa_per_sem_expression % (target_semester,)}, 2) AS sgpa")
            else:
                add_filter_condition("cgpa", "BETWEEN", [low, high], f"{cgpa_compared} BETWEEN %s AND %s", [low, high])
                selected_fields.append(f"ROUND({cgpa_expression}, 2) AS cgpa")
        else:
            # Reusable comparison layer. A numeric threshold may be phrased either
            # field-first ("cgpa above 8", "cgpa > 8") or value-first
            # ("more than 8 cgpa", "exceeds 9 sgpa"), with or without a linking
            # verb ("cgpa is at least 7"). Both orders share the module's one
            # operator table so no connecting word is ever mistaken for a field.
            comparison = _comparison_match(query, r"cgpa|sgpa|gpa")
            if comparison and not (0 <= comparison[1] <= 10):
                comparison = None
            if comparison:
                operator, raw, _match = comparison
                value = float(raw)
                if operator == "NOT_EQUALS":
                    raise HTTPException(
                        400,
                        "CGPA cannot be filtered as 'not equal to' a single score. "
                        "Please ask for above or below a value.",
                    )
                operator_name = {">": "GREATER_THAN", ">=": "GREATER_EQUAL",
                                 "<": "LESS_THAN", "<=": "LESS_EQUAL",
                                 "=": "EQUALS"}[operator]
                if use_per_sem_sgpa and target_semester is not None:
                    sgpa_sql = (
                        f"(EXISTS (SELECT 1 FROM marks m WHERE m.usn=s.usn AND m.semester=%s AND m.sgpa IS NOT NULL) "
                        f"AND {sgpa_per_sem_expression} {operator} %s)"
                    )
                    add_filter_condition("sgpa", operator_name, value, sgpa_sql,
                                         [target_semester, target_semester, value])
                    selected_fields.append(f"ROUND({sgpa_per_sem_expression % (target_semester,)}, 2) AS sgpa")
                else:
                    add_filter_condition("cgpa", operator_name, value,
                                         f"{cgpa_compared} {operator} %s", [value])
                    selected_fields.append(f"ROUND({cgpa_expression}, 2) AS cgpa")
            elif re.search(rf"\b(?:cgpa|sgpa|gpa)\s*{_COPULA}(?:not\s+)?{_OP_WORD}\s*\d", query):
                # An operator word and a score are both present but the parse above
                # found no usable threshold. Answering with unfiltered rows would be
                # worse than asking, so say which part was not understood.
                raise HTTPException(400, "could not map: the grade threshold in this question")

    # ── Place filters ─────────────────────────────────────────────────────────
    # Staff name a place with or without a preposition ("from Haveri",
    # "Hassan taluk", "Belur village"), list several at once ("Haveri or Dharwad
    # district"), and negate them ("not from Haveri"). Every form has to compile
    # to the matching SQL: the list tail and the word "not" used to be discarded,
    # which answered a subset request as if it were the whole answer and a
    # "not from" request with exactly the rows the staff member excluded.
    _DISTRICT_WORDS = r"(?:district|distict|distrct|distric|ditrict|zilla|jilla)"
    _PLACE_NOUNS = (
        ("district", rf"(?:{_DISTRICT_WORDS})s?"),
        ("taluk", r"(?:taluk|taluka|tehsil|tahsil)s?"),
        ("village", r"(?:village|habli)s?"),
        ("state", r"(?:state)s?"),
    )
    _skip_locations = {
        "rural", "urban", "the", "a", "an", "rural area", "urban area",
        "rural areas", "urban areas", "rural region", "urban region",
    }
    # Repeatedly strip trailing generic geographic noise words so phrases like
    # "rural areas" / "urban region" collapse to the bare classifier and get
    # skipped instead of becoming a failing LIKE '%rural areas%' filter.
    _noise_suffix = re.compile(
        rf"\s+(?:{_DISTRICT_WORDS}|taluk|taluka|tehsil|tahsil|village|habli|state"
        rf"|city|town|area|areas|region|regions|side|sides|part|parts"
        rf"|locality|localities|place|places)(?:s|es)?$"
    )
    # A negation counts only when it is the words typed directly before the
    # place, so "not having backlogs from Haveri" stays a positive Haveri filter.
    _NEGATED_PREPOSITION = re.compile(
        r"^(?:not|except|excluding|exclude|other\s+than|leaving\s+out|leave\s+out)\b",
        re.I)
    _NEGATED_BEFORE_NOUN = re.compile(
        r"\b(?:not|except|excluding|exclude|other\s+than|leaving\s+out|leave\s+out)\s*$",
        re.I)

    def _clean_place_value(raw: str) -> str:
        value = re.sub(r"\s+", " ", (raw or "").strip()).strip(" ,.'-")
        while True:
            stripped = _noise_suffix.sub("", value).strip()
            if stripped == value:
                return stripped
            value = stripped

    def _add_place_condition(column: str, values: list, negated: bool) -> None:
        """Compile one or several place values against one column (or the
        address blob when no place noun was typed)."""
        _has_branch_filter = any(condition["field"] == "branch"
                                 for condition in filter_conditions)

        def _is_branch_text(value: str) -> bool:
            words = re.findall(r"[a-z]+", value.lower())
            return bool(words) and set(words) <= _branch_vocab

        values = [v for v in (str(value).strip().lower() for value in values)
                  if v and v not in _skip_locations
                  and v.upper() not in branch_aliases
                  and not (_has_branch_filter and _is_branch_text(v))]
        if not values:
            return
        op = "NOT LIKE" if negated else "LIKE"
        joiner = " AND " if negated else " OR "
        if column == "location":
            haystack = ("LOWER(CONCAT_WS(' ', COALESCE(s.address,''), COALESCE(s.village,''), "
                        "COALESCE(s.taluk,''), COALESCE(s.district,'')))")
            fields = ("s.address", "s.village", "s.taluk", "s.district")
        else:
            col = _safe_column_name(column)
            haystack = f"LOWER(TRIM(COALESCE(s.{col}, '')))"
            fields = (f"s.{col}",)
        parts = [f"{haystack} {op} %s" for _ in values]
        sql = "(" + joiner.join(parts) + ")" if len(parts) > 1 else parts[0]
        add_filter_condition(column, "NOT_CONTAINS" if negated else "CONTAINS",
                             values[0] if len(values) == 1 else values,
                             sql, [f"%{value}%" for value in values])
        if len(values) > 1:
            filter_conditions[-1]["any_of"] = values
        for field in fields:
            if field not in selected_fields:
                selected_fields.append(field)

    location_match = re.search(
        r"\b((?:(?:not|except\s+those|except|excluding|exclude|other\s+than|"
        r"leaving\s+out|leave\s+out)\s+)?(?:from|in|at|near))\s+"
        r"(?!(?:least|most|best|first|second|third|fourth|fifth|"
        r"sixth|seventh|eighth|ninth|tenth|last|worst|highest|lowest|"
        r"maximum|minimum|equal|exactly|greater|less|above|below|over|under)\b)"
        r"([a-z][a-z .,'-]*?)"
        r"(?=\s+(?:with|who|whose|which|aged?|age|branch|department|semester|sem|cgpa|sgpa|gpa|"
        r"blood|father|mother|students?|student|phone|mobile|email|gender|male|female|"
        r"boys?|girls?|rural|urban|having|has|have|without|within|missing|no|not|but|"
        r"living|lives|live|residing|staying|studying|backlog|backlogs|arrear|arrears|"
        r"fee|fees|paid|unpaid|pending|lateral|regular|active|dropout|graduat\w*)\b|[?.;!]|$)",
        query,
    )
    if location_match:
        raw_clause = (location_match.group(2) or "").strip()
        negated = bool(_NEGATED_PREPOSITION.match(location_match.group(1)))
        clause = _clean_place_value(raw_clause)
        # Meta-questions like "total number of students in the database/system"
        # would otherwise become LIKE '%the database%' and match zero real
        # addresses. A "in semester three" phrase is an academic filter, not a
        # place either — it must not mask the real current_sem filter.
        _loc_core = re.sub(r"^(?:the|a|an)\s+", "", clause.lower()).strip()
        _is_sem_phrase = bool(re.match(r"(?:sem|semester|semesters)\b", _loc_core)) or bool(
            re.match(r"[1-8](?:st|nd|rd|th)?[-\s]*(?:sem|semester)\b", _loc_core)
        ) or bool(re.match(
            r"(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)"
            r"(?:[-\s]+(?:sem|semester))?\b", _loc_core
        ))
        if _is_sem_phrase or _loc_core in {
            "database", "db", "system", "table", "tables", "record", "records",
            "list", "college", "school", "institute", "university", "department",
            "data",
            # "top 5 students in cgpa" uses "in" where the parser expects a place;
            # the word is the sort key, so it must never filter the rows away.
            "cgpa", "sgpa", "gpa", "marks", "percentage", "percent",
        }:
            clause = ""
        if clause:
            # The place noun is detected on the raw clause because the value
            # cleanup removes it: "from Haveri district" filters the district
            # column, "from Hassan taluk" the taluk column.
            column = "location"
            for candidate, noun_pattern in _PLACE_NOUNS:
                if re.search(rf"(?:{noun_pattern})\b", raw_clause, re.I):
                    column = candidate
                    break
            # "Haveri or Dharwad district" / "A, B and C districts" — every value
            # in the list is a filter, never only the first one.
            values = [_clean_place_value(part) for part in re.split(
                r"\s*,\s*|\s+or\s+|\s+and\s+", raw_clause)]
            _add_place_condition(column, [v for v in values if v], negated)

    # A place can be named without a preposition ("students hassan distict",
    # "list students of Hassan taluk"). When no location filter was added above,
    # resolve "<value> <place noun>" against that column so the condition is
    # neither dropped nor routed to an unmapped-field error. The word must be a
    # real value of that column (or a near-miss of one): otherwise the noun is a
    # requested column name ("show village and district") and must not filter.
    if not any(condition["field"] in {"district", "taluk", "village", "state", "location"}
               for condition in filter_conditions):
        for candidate, noun_pattern in _PLACE_NOUNS:
            noun_match = re.search(
                rf"\b(?!(?:of|from|in|at|the|a|an|and|or|to|for|with|without|is|are|near|"
                rf"show|list|display|give|get|whose|which|who|students?|their|his|her)\b)"
                rf"([a-z][a-z']{{2,28}})\s+(?:{noun_pattern})\b"
                rf"|\b(?:{noun_pattern})\s+([a-z][a-z']{{2,28}})\b",
                query,
            )
            if not noun_match:
                continue
            value = (noun_match.group(1) or noun_match.group(2) or "").strip().lower()
            if (not value or value in _skip_locations
                    or value.upper() in branch_aliases
                    or re.fullmatch(rf"(?:{_DISTRICT_WORDS})s?", value)):
                continue
            if _best_value_match(candidate, value)[1] < 0.8:
                continue
            _add_place_condition(
                candidate, [value],
                bool(_NEGATED_BEFORE_NOUN.search(
                    query[max(0, noun_match.start() - 30):noun_match.start()])),
            )
            break

    # ── "<field> contains <value>": substring search on a text column ────────
    # The word "contains" used to carry no meaning here: "whose name contains Ra"
    # was read either as "name is available" (the whole batch) or as a lookup for
    # one person literally named "contains Ra" (no rows at all). Staff type part
    # of a name, village or address, so this has to search inside the column.
    _CONTAINS_COLUMNS = (
        (r"\bfather(?:['’]s)?\s+names?\b", ("father_name",)),
        (r"\bmother(?:['’]s)?\s+names?\b", ("mother_name",)),
        (r"\b(?:permanent|home)\s+address(?:es)?\b", ("permanent_address",)),
        (r"\b(?:current|local|present)\s+address(?:es)?\b", ("current_address",)),
        (r"\baddress(?:es)?\b", ("address", "permanent_address", "current_address",
                                 "village", "taluk")),
        (r"\bvillages?\b|\bnative\s+place\b", ("village",)),
        (r"\btaluks?\b|\btehsils?\b|\bmandals?\b", ("taluk",)),
        (r"\bdistricts?\b", ("district",)),
        (r"\bstates?\b", ("state",)),
        (r"\breligions?\b|\brelegions?\b", ("religion",)),
        (r"\bcastes?\b", ("caste",)),
        (r"\bsub[\s-]*castes?\b", ("sub_caste",)),
        (r"\bblood\s+(?:group|type)s?\b", ("blood_group",)),
        (r"\b(?:phone|mobile)(?:\s+numbers?)?\b", ("phone", "emergency_contact_number")),
        (r"\b(?:emails?|mails?)\b", ("email",)),
        (r"\badmission\s+year\b|\byear\s+of\s+joining\b", ("year_of_joining",)),
        (r"\bpin\s*codes?\b", ("pin_code",)),
        (r"\bpost\s+offices?\b", ("post_office",)),
        (r"\bnames?\b", ("name",)),
    )
    _CONTAINS_STOP = (
        r"(?=\s+(?:students?|who|whose|which|that|from|in|with|having|and|or|but|"
        r"branch|department|semester|sem|cgpa|sgpa|gpa|age|aged|years?\s+old|gender|"
        r"blood|religion|caste|category|district|taluk|village|state|phone|mobile|email|"
        r"male|female|rural|urban|lateral|active|graduat\w*|show|list|count)\b|[?.!,;]|$)"
    )
    for _op_match in re.finditer(r"\b(?:contains?|containing|includes?|including)\b",
                                 query, re.I):
        _before = query[:_op_match.start()].strip()
        _field_text = " ".join(re.findall(r"[A-Za-z][A-Za-z'’]*", _before)[-3:]).casefold()
        _negated = bool(re.search(
            r"\b(?:not|without|except|excluding|doesn'?t|don'?t)\s*$", _before, re.I))
        if not _field_text:
            continue
        _value_match = re.match(
            r"\s*(?:of\s+|the\s+|is\s+|as\s+)?"
            r"([A-Za-z0-9][A-Za-z0-9 .'\-]{0,40}?)" + _CONTAINS_STOP,
            query[_op_match.end():], re.I)
        if not _value_match:
            continue
        _needle = _value_match.group(1).strip(" .'-")
        if not _needle or _needle.casefold() in {
                "not", "no", "none", "missing", "null", "empty", "blank", "available",
                "present", "entered", "recorded", "his", "her", "their"}:
            continue
        _columns = next((cols for pat, cols in _CONTAINS_COLUMNS
                         if re.search(pat, _field_text)), None)
        if not _columns or any(condition["field"] in _columns
                               for condition in filter_conditions):
            continue
        _parts = [f"LOWER(TRIM(COALESCE(s.`{_col}`, ''))) "
                  f"{'NOT LIKE' if _negated else 'LIKE'} %s" for _col in _columns]
        _joiner = " AND " if _negated else " OR "
        _contains_sql = ("(" + _joiner.join(_parts) + ")") if len(_parts) > 1 else _parts[0]
        add_filter_condition(
            _columns[0], "NOT_CONTAINS" if _negated else "CONTAINS", _needle,
            _contains_sql, [f"%{_needle.lower()}%"] * len(_columns))
        filter_conditions[-1]["row_fields"] = list(_columns)
        for _col in _columns:
            item = f"s.`{_col}`"
            if item not in selected_fields:
                selected_fields.append(item)

    for column, pattern in requested_data_fields:
        if any(condition["field"] == column for condition in filter_conditions):
            continue
        matches = list(re.finditer(pattern, query, re.I))
        if not matches:
            continue
        if column == "phone" and re.search(r"emergency\s*$", query[:matches[0].start()], re.I):
            continue
        field_match = matches[-1]
        prefix = query[max(0, field_match.start() - 40):field_match.start()]
        suffix = query[field_match.end():field_match.end() + 35]
        is_missing = bool(re.search(
            r"\b(?:without|no|missing|does\s+not\s+have|do\s+not\s+have|don't\s+have|"
            r"doesn.t\s+have|has\s+no|not\s+entered|null|empty|blank|not\s+having|"
            r"haven'?t|hasn'?t|not\s+available|unavailable|absent)\b[^,;.!?]*$",
            prefix, re.I,
        ))
        is_present = bool(
            re.search(r"\b(?:available|present|entered|recorded|provided)\b", suffix, re.I)
            or re.search(r"\b(?:have|has|with|whose)\b[^,;.!?]*$", prefix, re.I)
        )
        if not is_missing and not is_present:
            continue
        if column in {"cgpa", "sgpa"}:
            if column == "cgpa":
                field_sql = (
                    "(NOT EXISTS (SELECT 1 FROM marks m WHERE m.usn=s.usn AND m.sgpa IS NOT NULL) "
                    "AND s.cgpa IS NULL)" if is_missing else
                    "(EXISTS (SELECT 1 FROM marks m WHERE m.usn=s.usn AND m.sgpa IS NOT NULL) "
                    "OR s.cgpa IS NOT NULL)"
                )
                select_sql = f"ROUND({cgpa_expression}, 2) AS cgpa"
            else:
                field_sql = (
                    "NOT EXISTS (SELECT 1 FROM marks m WHERE m.usn=s.usn AND m.sgpa IS NOT NULL)"
                    if is_missing else
                    "EXISTS (SELECT 1 FROM marks m WHERE m.usn=s.usn AND m.sgpa IS NOT NULL)"
                )
                select_sql = (
                    "(SELECT AVG(m.sgpa) FROM marks m WHERE m.usn=s.usn AND m.sgpa IS NOT NULL) AS sgpa"
                )
        else:
            field_sql = _build_missing_sql(column) if is_missing else _build_present_sql(column)
            select_sql = f"s.`{column}`"
        add_filter_condition(column, "MISSING" if is_missing else "PRESENT", None, field_sql)
        selected_fields.append(select_sql)

    # ── Generic field-value filter: "students whose <field> is <value>" ──────
    # Handles any text field not already filtered above.
    # Matches patterns like: "father name is Rudrappa", "village is Belur",
    #   "region is rural", "blood group O+", "branch not CSE", etc.
    _FIELD_VALUE_PATTERN = re.compile(
        r"\b(?:whose|with|having)\s+"
        r"(?P<field>(?:father(?:'s)?\s+)?name|(?:mother(?:'s)?\s+)?name|father|mother|"
        r"village|region|area|district|state|taluk|division|section|domain|roll\s*number|status)\b"
        r"\s*(?:is|=|named|called|equals?)?\s*"
        r"(?P<value>[A-Za-z0-9][A-Za-z0-9 .'-]{0,40}?)"
        r"(?=\s+(?:students?|and|or|from|in|with|without|missing|no|$)|[?.!,;]|$)",
        re.I,
    )
    for fv_match in _FIELD_VALUE_PATTERN.finditer(text):
        raw_field = fv_match.group("field").strip().casefold()
        raw_value = fv_match.group("value").strip(" .'-")
        if not raw_value or raw_value.casefold() in {
            "is", "the", "a", "an", "of", "missing", "null", "empty",
            "available", "present", "entered", "recorded", "not",
        }:
            continue
        # Map field names to DB columns
        _FVMAP = {
            "father name": "father_name", "father's name": "father_name", "father": "father_name",
            "mother name": "mother_name", "mother's name": "mother_name", "mother": "mother_name",
            "village": "village", "region": "region", "area": "area",
            "district": "district", "state": "state", "taluk": "taluk",
            "division": "division", "section": "division", "domain": "domain",
            "roll number": "roll_number", "status": "status",
        }
        db_col = _FVMAP.get(raw_field)
        if not db_col:
            continue
        if any(c["field"] == db_col for c in filter_conditions):
            continue
        # Detect negation: "not from ...", "whose village is not ..."
        neg_ctx = text[max(0, fv_match.start()-20):fv_match.start()]
        is_negated = bool(re.search(r"\b(?:not|without|no|don't|doesn't)\b", neg_ctx, re.I))
        if is_negated:
            sql_expr = f"(LOWER(TRIM(COALESCE(s.`{db_col}`, ''))) != LOWER(TRIM(%s)) OR s.`{db_col}` IS NULL)"
            add_filter_condition(db_col, "NOT_EQUALS", raw_value, sql_expr, [raw_value])
        else:
            sql_expr = f"LOWER(TRIM(COALESCE(s.`{db_col}`, ''))) = LOWER(TRIM(%s))"
            add_filter_condition(db_col, "EQUALS", raw_value, sql_expr, [raw_value])
        selected_fields.append(f"s.`{db_col}`")

    # ── "<value> students": the leading word names a column, not a person ─────
    # "show details of Vokkaliga students" produced no condition at all, so the
    # LLM searched student *names* for "vokkaliga" and answered with zero rows.
    # Only runs when nothing else was captured and the word is the exact value of
    # exactly one column, so genuine name lookups keep their own path.
    if not filter_conditions:
        _value_led = re.match(
            r"^\s*(?:(?:show|list|display|give|fetch|print|get|tell|me|all|the|only|"
            r"complete|full|details|detail|information|info|record|records|profile|"
            r"data|of|for|about)\s+)*"
            r"(?P<value>[a-z][a-z' .-]{2,40}?)\s+students\s*[?.!]*\s*$",
            query, re.I,
        )
        if _value_led:
            _led_text = re.sub(r"\s+", " ", _value_led.group("value")).strip(" .'-")
            _led_hits: dict[str, str] = {}
            for _led_col in sorted(_FUZZY_VALUE_COLUMNS):
                if _led_col == "branch":
                    continue  # branch has its own canonicalisation path
                for _known in _column_values(_led_col):
                    if _known.casefold() == _led_text.casefold():
                        _led_hits.setdefault(_led_col, _known)
                        break
            if _led_hits:
                # A place name usually lives in village and taluk at once, so the
                # request means "any of these columns holds this value".
                _led_parts = [
                    f"LOWER(TRIM(COALESCE(s.`{_col}`, ''))) = LOWER(TRIM(%s))"
                    for _col in _led_hits
                ]
                _led_sql = ("(" + " OR ".join(_led_parts) + ")"
                            if len(_led_parts) > 1 else _led_parts[0])
                _led_col, _led_value = next(iter(_led_hits.items()))
                add_filter_condition(
                    _led_col,
                    "IN" if len(_led_hits) > 1 else "EQUALS",
                    _led_value, _led_sql, list(_led_hits.values()))
                if len(_led_hits) > 1:
                    filter_conditions[-1]["or_fields"] = list(_led_hits)
                for _col in _led_hits:
                    if f"s.`{_col}`" not in selected_fields:
                        selected_fields.append(f"s.`{_col}`")

    requested_filter_fields = set()
    if lateral_requested:
        requested_filter_fields.add("student_type")
    if target_semester is not None and not (_sgpa_metric and not _cgpa_metric):
        requested_filter_fields.add("current_sem")
    if branches:
        requested_filter_fields.add("branch")
    if blood_values:
        requested_filter_fields.add("blood_group")
    if missing_request and requested_data_field and requested_data_field[0] == "blood_group":
        requested_filter_fields.add("blood_group")
    if re.search(r"\b(?:rural|urban)\b", query):
        requested_filter_fields.add("rural_status")
    if missing_request and requested_data_field and requested_data_field[0] == "emergency_contact_number":
        requested_filter_fields.add("emergency_contact_number")
    if age_context and any(condition["field"] == "age" for condition in filter_conditions):
        requested_filter_fields.add("age")
    requested_comparison_fields = {
        condition["field"] for condition in filter_conditions
        if condition["field"] in {"cgpa", "sgpa"}
    }
    requested_filter_fields.update(requested_comparison_fields)
    generated_filter_fields = {condition["field"] for condition in filter_conditions}
    missing_filter_fields = requested_filter_fields - generated_filter_fields
    if missing_filter_fields:
        raise ValueError(
            "Unable to preserve requested filters: " + ", ".join(sorted(missing_filter_fields))
        )
    unmapped_clause = _unmapped_filter_clause(text)
    if unmapped_clause and where_clauses:
        # The builder already captured other conditions deterministically; delegating
        # now would silently drop the unrecognized filter. Reject instead of inventing
        # or discarding a user-requested condition.
        raise HTTPException(400, f"could not map: {unmapped_clause}")
    if unmapped_clause:
        return None

    if not where_clauses:
        # A filter-less count ("total number of students in the database") must
        # return a real COUNT(*) deterministically; otherwise it falls to the LLM,
        # which re-injects a bogus "location" filter from the filler phrase and
        # answers 0.
        if is_count and not count_and_list:
            return {
                "operation": "select",
                "sql": "SELECT COUNT(*) AS total_students FROM students s",
                "params": [],
                "ast": {"intent": "COUNT", "conditions": [], "logical_operator": "AND"},
            }
        # A ranking request with no other filter ("top 5 by CGPA") has no WHERE
        # condition, but must NOT fall through to the non-deterministic LLM (which
        # mis-parses "top" as a student name). Handle it deterministically with a
        # neutral predicate so the ORDER BY / LIMIT / NULL-exclusion below applies.
        if _detect_rank_limit(query) is None:
            return None
        where_clauses.append("1=1")

    if is_count and not count_and_list:
        _count_note = _correction_message()
        return {
            "operation": "select",
            "sql": "SELECT COUNT(*) AS total_students FROM students s WHERE " + " AND ".join(where_clauses),
            "params": params,
            **({"message": _count_note} if _count_note else {}),
            "ast": {"intent": "COUNT", "conditions": filter_conditions, "logical_operator": "AND"},
        }

    selected_fields = list(dict.fromkeys(selected_fields))
    if is_count and count_and_list:
        selected_fields.insert(0, "COUNT(*) OVER() AS total_count")

    # ── Order-by resolution: sgpa/cgpa/name/usn sort requests ────────────────
    usn_sort_expr = (
        "(CASE WHEN UPPER(s.usn) REGEXP '^[0-9][A-Z]{2,3}[0-9]{2}[A-Z]{2,4}[0-9]{2,3}' "
        "THEN CAST(SUBSTRING(s.usn, 4, 2) AS UNSIGNED) - "
        "IF(CAST(RIGHT(s.usn, 3) AS UNSIGNED) >= 400, 1, 0) "
        "ELSE 999 END) ASC, s.usn"
    )
    sort_by = f"ORDER BY {usn_sort_expr} ASC"
    explicit_sort = None
    sort_by_match = re.search(
        r"\border\s+(?:by|on)?\s+(?:the\s+)?(?:basis\s+of\s+)?(sgpa|cgpa|gpa|name|usn)\b|"
        r"\b(sgpa|cgpa|gpa)\s+(?:wise|based|order|sort|sorted|ranked|ranking|descending|ascending|highest|lowest|top)\b|"
        r"\b(sort|order|rank|arrange|list)\s+(?:the\s+)?students?\s+(?:by|on|based\s+on|according\s+to)\s+(?:the\s+)?(sgpa|cgpa|gpa|name|usn)\b|"
        r"\btop\s+\d+\s+(?:students?\s+)?(?:with|by|in|of|for|having)?\s*(sgpa|cgpa|gpa)\b|"
        r"\b(sgpa|cgpa|gpa)\s+wise\b",
        query, re.I
    )
    if not sort_by_match:
        if sgpa_explicit and target_semester is not None:
            explicit_sort = "sgpa_per_sem"
        elif sgpa_explicit and target_semester is None:
            explicit_sort = "sgpa_aggregate"
        elif cgpa_explicit or (gpa_context and not sgpa_explicit):
            explicit_sort = "cgpa"
        elif re.search(r"\bname\s+wise\b|\balphabetical", query, re.I):
            explicit_sort = "name"
    else:
        all_groups = sort_by_match.groups()
        matched_word = next((g.upper() if g else None for g in all_groups if g), None)
        if matched_word == "SGPA":
            explicit_sort = "sgpa_per_sem" if target_semester is not None else "sgpa_aggregate"
        elif matched_word == "CGPA" or matched_word == "GPA":
            explicit_sort = "cgpa"
        elif matched_word == "NAME":
            explicit_sort = "name"
        else:
            explicit_sort = "usn"

    desc = bool(re.search(
        r"\b(descending|desc|highest|top|best|greatest|maximum|max|decreasing|high)\b|"
        r"\b(sgpa|cgpa|gpa)\s+(?:highest|toppers?|top|maximum|max|best|greatest)\b",
        query, re.I
    ))
    direction = "DESC" if desc else "ASC"

    # Ranking compares the precise average, not the 2-decimal display value:
    # two students showing 9.02 must still come out in score order.
    if explicit_sort == "cgpa":
        sort_by = f"ORDER BY {cgpa_expression} {direction}, {usn_sort_expr} ASC"
    elif explicit_sort == "sgpa_aggregate":
        sort_by = f"ORDER BY {cgpa_expression} {direction}, {usn_sort_expr} ASC"
    elif explicit_sort == "sgpa_per_sem" and target_semester is not None:
        sem_sgpa_expr_clean = (
            "(SELECT m.sgpa FROM marks m WHERE m.usn=s.usn "
            f"AND m.semester={target_semester} AND m.sgpa IS NOT NULL LIMIT 1)"
        )
        sort_by = f"ORDER BY {sem_sgpa_expr_clean} {direction}, {usn_sort_expr} ASC"
    elif explicit_sort == "name":
        sort_by = f"ORDER BY s.name ASC, {usn_sort_expr} ASC"

    # A query that ranks students by an academic metric must return that metric,
    # even when no threshold condition referenced it (e.g. "top 10 by cgpa").
    # Only add it if a condition handler did not already project the column.
    if explicit_sort in ("cgpa", "sgpa_aggregate", "sgpa_per_sem"):
        _already_sgpa = any(f.endswith(" AS sgpa") for f in selected_fields)
        _already_cgpa = any(f.endswith(" AS cgpa") for f in selected_fields)
        if explicit_sort == "cgpa" and not _already_cgpa:
            selected_fields.append(f"ROUND({cgpa_expression}, 2) AS cgpa")
        elif explicit_sort == "sgpa_aggregate" and not _already_sgpa:
            selected_fields.append(
                "(SELECT AVG(m.sgpa) FROM marks m WHERE m.usn=s.usn AND m.sgpa IS NOT NULL) AS sgpa"
            )
        elif explicit_sort == "sgpa_per_sem" and target_semester is not None and not _already_sgpa:
            selected_fields.append(
                f"ROUND({sgpa_per_sem_expression % (target_semester,)}, 2) AS sgpa"
            )
            # The SGPA shown is a single semester's; the cumulative CGPA is a
            # different number (average over ALL semesters). Project it explicitly
            # so the results table never has to reconstruct CGPA from one SGPA
            # value (which would wrongly render CGPA == SGPA).
            if not _already_cgpa:
                selected_fields.append(f"ROUND({cgpa_expression}, 2) AS cgpa")
            selected_fields.append(f"{target_semester} AS semester")

    # A top/last-N ranking by CGPA/SGPA must exclude students whose computed value
    # is NULL (no marks recorded). Otherwise MySQL sorts the NULL rows first for an
    # ASCENDING 'last/bottom N' ranking and returns students who have no result at all.
    _rank_n = _detect_rank_limit(query)
    if _rank_n is not None and not is_count:
        if explicit_sort == "cgpa" or explicit_sort == "sgpa_aggregate":
            where_clauses.append(f"{cgpa_expression} IS NOT NULL")
        elif explicit_sort == "sgpa_per_sem" and target_semester is not None:
            where_clauses.append(
                "(SELECT m.sgpa FROM marks m WHERE m.usn=s.usn "
                f"AND m.semester={target_semester} AND m.sgpa IS NOT NULL LIMIT 1) IS NOT NULL")

    # Tell the staff member what a mistyped value was read as, instead of
    # silently answering for a different district/caste/village than the one they
    # typed. The substituted value is always one that exists in their own data.
    _note = _correction_message()

    sql = (
        "SELECT " + ", ".join(selected_fields) + " FROM students s WHERE "
        + " AND ".join(where_clauses) + " " + sort_by
    )
    if _rank_n is not None and not is_count:
        sql += f" LIMIT {int(_rank_n)}"
    return {
        "operation": "select",
        "sql": sql,
        "params": params,
        **({"message": _note} if _note else {}),
        "ast": {
            "intent": "COUNT" if is_count else ("TOP" if _rank_n is not None else "SEARCH"),
            "conditions": filter_conditions,
            "logical_operator": "AND",
        },
    }


def _classify_residence(address: str, area_type: str | None, region: str | None) -> str | None:
    for value in (area_type, region):
        normalized = str(value or "").strip().upper()
        if normalized in {"RURAL", "URBAN"}:
            return normalized
    if re.search(r"\bvillage\b|\(\s*v\s*\)", str(address or ""), re.I):
        return "RURAL"
    return None


def _row_satisfies_filter_ast(row: dict, ast: dict) -> bool:
    """Reject a deterministic result row that violates any compiled core filter."""
    try:
        from graduation_manager import parse_usn_full
        parsed_usn = parse_usn_full(str(row.get("usn") or "")) or {}
    except Exception:
        parsed_usn = {}

    for condition in ast.get("conditions", []):
        field = condition["field"]
        expected = condition["value"]
        if field == "fee_status":
            # The USN list was built from student_fees with the reports' own
            # status normaliser, which a students row cannot show.
            continue
        or_fields = condition.get("or_fields")
        if or_fields:
            # The SQL ORs the value across several columns (a place name lives in
            # both village and taluk), so re-check every column, not one.
            wanted = {str(v).strip().casefold()
                      for v in ([expected] if isinstance(expected, str)
                                else (expected or []))}
            if not any(str(row.get(f) or "").strip().casefold() in wanted
                       for f in or_fields):
                return False
            continue
        if field == "student_type":
            actual = row.get("student_type")
            if actual is None or not str(actual).strip():
                actual = parsed_usn.get("student_type")
            matched = str(actual or "").strip().upper().replace(" ", "") in (
                "LATERAL", "LATERALENTRY")
        elif field in ("current_sem", "current_year"):
            actual = row.get(field)
            if condition["operator"] == "PRESENT":
                matched = actual is not None and str(actual).strip() != ""
            elif condition["operator"] == "MISSING":
                matched = actual is None or str(actual).strip() == ""
            else:
                if actual is None:
                    actual = parsed_usn.get(field)
                try:
                    matched = int(float(actual)) == int(float(expected))
                except (TypeError, ValueError):
                    matched = False
        elif field == "backlogs":
            # Rows carry no backlog column: the EXISTS subquery in the SQL is the
            # authority for this filter, so nothing to re-check here.
            matched = True
        elif field == "branch":
            actual = row.get("branch") or parsed_usn.get("branch")
            actual = _canonical_branch_code(actual)
            matched = actual in {_canonical_branch_code(value) for value in expected}
        elif field == "blood_group":
            actual = re.sub(r"\s+", "", str(row.get("blood_group") or "").upper())
            actual = actual.replace("POSITIVE", "+").replace("NEGATIVE", "-")
            if condition["operator"] == "MISSING":
                matched = not actual
            elif condition["operator"] == "PRESENT":
                matched = bool(actual)
            elif condition["operator"] == "NOT_IN":
                matched = bool(actual) and actual not in expected
            else:
                matched = actual in expected
        elif field == "rural_status":
            address = " ".join(str(row.get(key) or "") for key in ("address", "village"))
            residence = _classify_residence(address, row.get("area_type"), row.get("region"))
            status_matches = residence == expected
            matched = not status_matches if condition["operator"] == "NOT_EQUALS" else status_matches
        elif field == "emergency_contact_number":
            matched = not str(row.get("emergency_contact_number") or "").strip()
        elif field in {"cgpa", "sgpa"}:
            actual = row.get(field)
            if condition["operator"] == "MISSING":
                matched = actual is None
            elif condition["operator"] == "PRESENT":
                matched = actual is not None
            else:
                try:
                    actual_value = float(actual)
                    # The projected value is rounded to 2 decimals while the SQL
                    # filter used the unrounded expression. Rows are already
                    # filtered by SQL, so tolerate the rounding delta instead of
                    # rejecting valid rows whose raw score sat just past a strict
                    # threshold (e.g. 7.0008 rounds to 7.0 but satisfies >7).
                    eps = 0.01
                    if condition["operator"] == "BETWEEN":
                        matched = float(expected[0]) - eps <= actual_value <= float(expected[1]) + eps
                    elif condition["operator"] == "GREATER_THAN":
                        matched = actual_value > float(expected) - eps
                    elif condition["operator"] == "GREATER_EQUAL":
                        matched = actual_value >= float(expected) - eps
                    elif condition["operator"] == "LESS_THAN":
                        matched = actual_value < float(expected) + eps
                    elif condition["operator"] == "LESS_EQUAL":
                        matched = actual_value <= float(expected) + eps
                    else:
                        matched = abs(actual_value - float(expected)) <= eps
                except (TypeError, ValueError):
                    matched = False
        elif field == "age":
            try:
                actual = int(row.get("age"))
                if condition["operator"] == "BETWEEN":
                    matched = int(expected[0]) <= actual <= int(expected[1])
                elif condition["operator"] == "IN":
                    matched = actual in expected
                elif condition["operator"] == "GREATER_THAN":
                    matched = actual > int(expected)
                elif condition["operator"] == "GREATER_EQUAL":
                    matched = actual >= int(expected)
                elif condition["operator"] == "LESS_THAN":
                    matched = actual < int(expected)
                elif condition["operator"] == "LESS_EQUAL":
                    matched = actual <= int(expected)
                else:
                    matched = actual == int(expected)
            except (TypeError, ValueError):
                matched = False
        elif field == "location" or condition.get("row_fields"):
            # Must mirror the SQL's column list exactly: leaving taluk out
            # rejected rows that only matched through the taluk column.
            keys = condition.get("row_fields") or (
                "address", "village", "taluk", "district")
            actual = " ".join(str(row.get(key) or "") for key in keys)
            wanted = condition.get("any_of") or [expected]
            hit = any(str(value).casefold() in actual.casefold() for value in wanted)
            matched = not hit if condition["operator"] == "NOT_CONTAINS" else hit
        elif field == "dob":
            try:
                date_text = str(row.get("dob"))[:10]
                dob = datetime.strptime(date_text, "%Y-%m-%d")
                actual = dob.year
                if condition["operator"] == "YEAR_BETWEEN":
                    matched = int(expected[0]) <= actual <= int(expected[1])
                elif condition["operator"] == "YEAR_EQUALS":
                    matched = actual == int(expected)
                elif condition["operator"] == "YEAR_GREATER_THAN":
                    matched = actual > int(expected)
                elif condition["operator"] == "YEAR_LESS_THAN":
                    matched = actual < int(expected)
                else:
                    matched = dob.month == int(expected)
            except (TypeError, ValueError):
                matched = False
        else:
            actual = row.get(field)
            operator = condition["operator"]
            if operator == "MISSING":
                matched = actual is None or not str(actual).strip()
            elif operator == "PRESENT":
                matched = actual is not None and bool(str(actual).strip())
            elif operator == "EQUALS":
                matched = str(actual).upper() == str(expected).upper()
            elif operator == "NOT_EQUALS":
                matched = str(actual).upper() != str(expected).upper()
            elif operator == "IN":
                matched = str(actual).strip().upper() in {
                    str(value).strip().upper() for value in (expected or [])}
            elif operator == "NOT_IN":
                matched = str(actual).strip().upper() not in {
                    str(value).strip().upper() for value in (expected or [])}
            elif operator == "CONTAINS":
                any_of = condition.get("any_of")
                if any_of:
                    hay = str(actual or "").casefold()
                    matched = any(str(v).casefold() in hay for v in any_of)
                else:
                    matched = str(expected).casefold() in str(actual or "").casefold()
            elif operator == "NOT_CONTAINS":
                hay = str(actual or "").casefold()
                wanted = condition.get("any_of") or [expected]
                matched = not any(str(v).casefold() in hay for v in wanted)
            else:
                matched = False
        if not matched:
            return False
    return True


def _public_query_ast(ast: dict | None) -> dict | None:
    if not ast:
        return None
    return {
        "intent": ast.get("intent"),
        "logical_operator": ast.get("logical_operator", "AND"),
        "conditions": [
            {key: condition[key] for key in ("field", "operator", "value") if key in condition}
            for condition in ast.get("conditions", [])
        ],
    }


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
    import json
    clean = {}
    for k, v in row.items():
        if k == 'dynamic_data' and isinstance(v, str):
            try:
                clean[k] = json.loads(v)
            except Exception:
                clean[k] = {}
        elif v is None:
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


# ── Multi-record filter intent detection ─────────────────────────────────────
# Queries that ask for ALL students matching a condition (missing data, value
# match, specific group) should NEVER be treated as single-student lookups.
_MULTI_RECORD_FILTER_RE = re.compile(
    r"\b(?:without|no|missing|does\s+not\s+have|do\s+not\s+have|don'?t\s+have|"
    r"hasn'?t|haven'?t|has\s+no|have\s+no|not\s+entered|not\s+available|absent)"
    r"\s+(?:a\s+|an\s+|any\s+)?(?:"
    r"address|phone|mobile|email|blood\s*group|father\s*name|mother\s*name|"
    r"emergency\s*contact|cgpa|sgpa|dob|village|region|area|district|state|taluk|"
    r"aadhar|gender|religion|caste|division|domain|status|usn|name|roll)\b|"
    r"\b(?:students?|student)\s+(?:without|with\s+no|missing|who\s+(?:have|has)\s+no|who\s+don'?t\s+have)\b|"
    r"\b(?:list|show|find|display|get)\s+(?:all\s+)?students?\b|"
    r"\b(?:how\s+many|count|number\s+of)\s+students?\b",
    re.IGNORECASE,
)


# ── Lifecycle intent detection (spec §9) ─────────────────────────────────────
# Detects dropout / discontinued / readmission / rejoin / status-history
# questions so downstream post-processing does not treat them as single-student
# profile queries or personal/academic lists.
_LIFECYCLE_INTENT_RE = re.compile(
    r"\b(?:drop\s*outs?|dropped\s+out|discontinu\w*|re-?admission|readmission|"
    r"re-?join\w*|status\s+history|lifecycle|left\s+(?:the\s+)?(?:college|course|studies))\b|"
    r"\bleft\b[^.]*\bnot\s+returned\b|\bstopped\s+(?:studies|college|course)\b|"
    r"\b(?:complete|full|academic|status)\s+history\b",
    re.IGNORECASE,
)


def _detect_intent(nq: str) -> str:
    """
    Returns one of: 'personal', 'academic', 'complete_profile', 'scalar_number',
    'girls_names', 'rural_search', 'urban_search', 'location_search',
    'specific_field', 'multi_record_filter', or 'full'.

    'multi_record_filter' — user asks for ALL students matching a condition.
    'specific_field' — user asks for exactly one named attribute of a single student.
    """
    # Lifecycle questions win over every other intent (spec §9) so a phrase like
    # "history of USN 4HG24CS007" is not replaced by a generic complete_profile,
    # and "readmission pending" is not treated as a scalar-number fee count.
    if _LIFECYCLE_INTENT_RE.search(nq):
        return 'lifecycle'

    # Scalar counts
    if re.search(r'\b(?:how\s+many|count|number\s+of|estimated?)\b.*\b(?:rural|urban)\b', nq, re.I):
        return 'scalar_number'
    if re.search(r'\bhow\s+many\s+students\b|\bcount\b.*\bcgpa\b|\bnumber\s+of\s+students\b|\bcount\b.*\bstudents?\b', nq, re.I):
        return 'scalar_number'

    # Rural / urban list queries
    if re.search(r'\brural\b', nq, re.I):
        return 'rural_search'
    if re.search(r'\burban\b', nq, re.I):
        return 'urban_search'

    # Location search
    if re.search(r'\b(?:students?|student records?)\b.*\b(?:from|in|at|near)\b', nq, re.I):
        return 'location_search'

    # Girls names
    if re.search(r'\b(?:give|show|list|get)?\s*only\s*(?:girls?|female|women)\s*names?\b|\b(?:girls?|female)\s*names?\s*only\b|\bgirls?\s*names?\b', nq, re.I):
        return 'girls_names'

    # Complete profile (check before specific-field so "complete information" wins)
    if is_complete_profile_intent(nq) or _COMPLETE_PROFILE_RE.search(nq):
        return 'complete_profile'

    # Multi-record filter: "students without X", "list students with X", etc.
    # Must be detected BEFORE specific_field to avoid misclassification.
    if _MULTI_RECORD_FILTER_RE.search(nq):
        return 'multi_record_filter'

    # Specific single-field queries: "show <name>'s <field>" / "what is <name>'s <field>"
    _SPECIFIC_FIELD_RE = re.compile(
        r'\b(?:show|give|display|what\s+is|get)\b.{0,40}'
        r'(?:\'s|s\'|\s+of|\s+for)?\s+'
        r'(?:phone|mobile|contact|emergency\s*contact|email|address|permanent\s+address|'
        r'current\s+address|village|area\s+type|area|region|taluk|district|state|'
        r'father\s*name|mother\s*name|blood\s*group|dob|date\s+of\s+birth|'
        r'current\s+sem(?:ester)?|branch|gender|aadhar|cgpa|sgpa)\b',
        re.I
    )
    if _SPECIFIC_FIELD_RE.search(nq):
        # Make sure it's not a bulk query
        if not re.search(r'\ball\s+students\b|\blist\b|\bevery\b', nq, re.I):
            return 'specific_field'

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
    """
    Keep narrow single-field requests narrow even if the LLM adds extra identity fields.
    Only strips columns when the user clearly asked for exactly one specific field.
    Never strips for complete-profile, bulk, or multi-field queries.
    """
    if query_dict.get('operation', '').lower() != 'select':
        return query_dict
    # Lifecycle queries already project a deliberate, fixed column set
    # (status, semester, scheme, reason, cgpa…) — never narrow them to one field.
    if query_dict.get('lifecycle'):
        return query_dict
    # The intent-field resolver already picked the ACTUAL contact column and
    # labeled it honestly (e.g. parents_phone AS parent_contact_number for a
    # mother-phone request with no mother column). Narrowing on the word "phone"
    # here would swap in the student's own number under a "Parent Contact" label —
    # a data-integrity/spec violation — so leave that projection intact.
    if query_dict.get('intent_contact'):
        return query_dict
    if _COMPLETE_PROFILE_RE.search(nq) or is_complete_profile_intent(nq):
        return query_dict
    # Never strips for bulk/list queries — rural/urban/complete/all need all their columns
    if re.search(r'\ball\s+students\b|\blist\s+all\b|\bevery\s+student\b|\brural\b|\burban\b', nq, re.I):
        return query_dict

    field_patterns = [
        (r'\bphone\s*(?:number|no)?\b|\bmobile\s*(?:number|no)?\b|\bcontact\s*(?:number|no)?\b', 'phone'),
        (r'\bemergency\s*(?:contact|number|phone)\s*(?:number|no)?\b', 'emergency_contact_number'),
        (r'\bemail\b|\bmail\b', 'email'),
        (r'\bpermanent\s+address\b', 'permanent_address'),
        (r'\bcurrent\s+address\b', 'current_address'),
        (r'\baddress\b', 'address'),
        (r'\bvillage\b', 'village'),
        (r'\barea\s+type\b|\brural\s*urban\b', 'area_type'),
        (r'\barea\b|\blocality\b', 'area'),
        (r'\bregion\b', 'region'),
        (r'\btaluk\b', 'taluk'),
        (r'\bdistrict\b', 'district'),
        (r'\bstate\b(?!\s+of\s+the\s+art)', 'state'),
        (r'\bfather\s*(?:\'s)?\s*name\b|\bdad(?:dy)?(?:\'s)?\s*name\b', 'father_name'),
        (r'\bmother\s*(?:\'s)?\s*name\b|\bmom(?:my)?(?:\'s)?\s*name\b', 'mother_name'),
        (r'\bblood\s+group\b', 'blood_group'),
        (r'\b(?:date\s+of\s+birth|dob|birth\s+date)\b', 'dob'),
        (r'\bbranch\b|\bdepartment\b', 'branch'),
        (r'\bcurrent\s+sem(?:ester)?\b', 'current_sem'),
        (r'\bgender\b|\bsex\b', 'gender'),
        (r'\baadhar\b', 'aadhar_no'),
        (r'\breligion\b', 'religion'),
        (r'\bcaste\b', 'caste'),
        # name only when explicitly asked alone (not "student name" in a broader query)
        (r'(?:show|give|display|get|what\s+is)\s+(?:\w+\s+){0,3}(?:\'s\s+)?(?:student\s+)?name\b', 'name'),
    ]

    requested = [col for pat, col in field_patterns if re.search(pat, nq, re.I)]

    # Only enforce narrow select when exactly ONE field was requested
    if len(requested) != 1:
        return query_dict

    sql = query_dict.get('sql', '')
    # Never narrow an aggregate query — rewriting COUNT(*)/SUM/AVG into a column
    # list would destroy the aggregation (e.g. "how many ..." count queries).
    if re.search(r'(?i)\b(?:COUNT|SUM|AVG|MIN|MAX)\s*\(', sql) or \
       re.search(r'(?i)\bAS\s+(?:total_students|total_count)\b', sql):
        return query_dict
    # A location filter matches across address/village/district via CONCAT_WS.
    # Narrowing the SELECT to a single column would drop the others that the
    # post-query result validator re-checks, falsely rejecting rows that matched
    # via a column we removed (→ spurious "results did not satisfy filter" 500).
    if re.search(r"CONCAT_WS\([^)]*\baddress\b", sql, re.I):
        return query_dict
    # Same reason for a multi-column substring filter ("address contains X" searches
    # address, permanent_address, current_address, village and taluk): dropping the
    # extra columns made the validator reject rows that matched through them.
    if any(condition.get("row_fields")
           for condition in ((query_dict.get("ast") or {}).get("conditions") or [])):
        return query_dict
    match = re.match(r'(?is)^\s*SELECT\s+(.*?)\s+FROM\s+', sql)
    if not match:
        return query_dict

    col = requested[0]
    items = _split_select_items(match.group(1))
    # Find existing column reference in SELECT list
    col_match = next(
        (item for item in items if re.search(
            rf'(?i)(?:\b\w+\.)?`?{re.escape(col)}`?(?:\s+AS\s+\w+)?\s*$', item
        )),
        None,
    )
    col_expr = col_match or f's.`{col}`'

    # Always keep usn + name for identification alongside the single field
    usn_expr = next((i for i in items if re.search(r'(?i)(?:\b\w+\.)?`?usn`?', i)), 's.usn')
    name_expr = next((i for i in items if re.search(r'(?i)(?:\b\w+\.)?`?name`?(?:\s|$)', i)), 's.name')

    # Don't restructure CGPA window-function queries — leave the LLM SQL intact
    if col in ('cgpa', 'sgpa') or 'AVG(' in sql.upper() or 'OVER(' in sql.upper():
        return query_dict

    query_dict = dict(query_dict)
    # A filter column must survive the narrowing: "female students from Haveri
    # district" requests only the district, and dropping s.gender from the
    # projection made the result validator reject every row it re-checked
    # ("results did not satisfy every requested filter", HTTP 500).
    kept = [usn_expr, name_expr, col_expr]
    for condition in ((query_dict.get("ast") or {}).get("conditions") or []):
        field = str(condition.get("field") or "")
        if not field or field == col or not re.fullmatch(r"[a-z_][a-z0-9_]*", field):
            continue
        item = next((i for i in items if re.search(
            rf'(?i)^(?:\w+\.)?`?{re.escape(field)}`?(?:\s+AS\s+\w+)?$', i)), None)
        if item and item not in kept:
            kept.append(item)
    query_dict['sql'] = (
        f"SELECT {', '.join(kept)} "
        f"FROM {sql[match.end():]}"
    )
    return query_dict


def _requested_specific_columns(natural_query: str) -> set[str]:
    """Resolve the exact student/academic columns asked for in a narrow query."""
    requested = set()
    for pattern, column in (
        (r'\bphone\s*(?:number|no)?\b|\bmobile\s*(?:number|no)?\b|\bcontact\s*(?:number|no)?\b', 'phone'),
        (r'\bemergency\s*(?:contact|number|phone)\s*(?:number|no)?\b', 'emergency_contact_number'),
        (r'\bemail\b|\bmail\b', 'email'),
        (r'\bpermanent\s+address\b', 'permanent_address'),
        (r'\bcurrent\s+address\b', 'current_address'),
        (r'\baddress\b', 'address'),
        (r'\bvillage\b', 'village'),
        (r'\barea\s+type\b', 'area_type'),
        (r'\barea\b|\blocality\b', 'area'),
        (r'\bregion\b', 'region'),
        (r'\btaluk\b', 'taluk'),
        (r'\bdistrict\b', 'district'),
        (r'\bstate\b(?!\s+of\s+the\s+art)', 'state'),
        (r"\bfather(?:[\'']s)?\s*name\b|\bdad(?:dy)?(?:[\'']s)?\s*name\b", 'father_name'),
        (r"\bmother(?:[\'']s)?\s*name\b|\bmom(?:my)?(?:[\'']s)?\s*name\b", 'mother_name'),
        (r'\bblood\s+group\b', 'blood_group'),
        (r'\b(?:date\s+of\s+birth|dob|birth\s+date)\b', 'dob'),
        (r'\bbranch\b|\bdepartment\b', 'branch'),
        (r'\bcurrent\s+sem(?:ester)?\b', 'current_sem'),
        (r'\bgender\b|\bsex\b', 'gender'),
        (r'\baadhar\b', 'aadhar_no'),
        (r'\breligion\b', 'religion'),
        (r'\bcaste\b', 'caste'),
        (r'\bcgpa\b', 'cgpa'),
        (r'\bsgpa\b', 'sgpa'),
        (r'\busn\b|\bstudent\s+(?:id|number)\b', 'usn'),
        (r'(?:show|give|display|get|what\s+is)\s+(?:\w+\s+){0,3}(?:\'s\s+)?(?:student\s+)?name\b', 'name'),
    ):
        if re.search(pattern, natural_query, re.I):
            requested.add(column)
    return requested


def _filter_by_intent(rows: list[dict], intent: str, natural_query: str | None = None) -> list[dict]:
    """
    Post-process result rows based on query intent.
    - specific_field: keep only requested field(s) + usn + name for identity
    - girls_names: return only name
    - personal with specific requested fields: return only those fields + usn + name
    - everything else: pass through unchanged
    """
    if not rows:
        return rows

    def _keep_with_contact(keep: set[str]) -> set[str]:
        """A contact need may resolve to a column the projection names
        parent_contact_number / mothers_phone / emergency_contact (the intent
        layer labels it honestly). Keep any such projected contact column so the
        narrow-scope filter never strips the very answer that was requested."""
        contact_keys = {k for r in rows for k in r
                        if re.search(r'phone|contact|mobile|mahati', str(k), re.I)}
        return keep | contact_keys

    # Girls names only
    if intent == 'girls_names' or (natural_query and re.search(
        r'\b(?:give|show|list|get|display)?\s*only\s*(?:girls?|female)\s*names?\b', natural_query, re.I
    )):
        return [{'name': r.get('name')} for r in rows if r.get('name')]

    # Exact single-field scope — strip injected extras (e.g. current_sem)
    if intent == 'specific_field' and natural_query:
        requested = _requested_specific_columns(natural_query)
        if requested:
            keep = set(requested)
            keep.update({'usn', 'name', 'dynamic_data'})
            keep = _keep_with_contact(keep)
            # Preserve semester when SGPA was asked in an academic row
            if 'sgpa' in requested:
                keep.add('semester')
            return [{k: v for k, v in row.items() if k in keep} for row in rows]
        return rows

    # These intents: SQL already selected exactly what was needed - pass through
    if intent in ('rural_search', 'urban_search', 'location_search',
                  'scalar_number', 'complete_profile', 'full', 'academic',
                  'multi_record_filter', 'lifecycle'):
        return rows

    # Personal intent: filter to only the explicitly requested fields
    if intent == 'personal' and natural_query:
        requested = set()
        for pattern, column in (
            (r'\b(?:usn|student\s+number)\b', 'usn'),
            (r'\b(?:student\s+)?name\b', 'name'),
            (r'\bphone\s*(?:number|no)?\b|\bmobile\b|\bcontact\s+number\b', 'phone'),
            (r'\bemergency\s*(?:contact|number|phone)\b', 'emergency_contact_number'),
            (r'\bemail\b|\bmail\b', 'email'),
            (r'\bpermanent\s+address\b', 'permanent_address'),
            (r'\bcurrent\s+address\b', 'current_address'),
            (r'\baddress\b', 'address'),
            (r'\bvillage\b', 'village'),
            (r'\barea\s+type\b', 'area_type'),
            (r'\barea\b|\blocality\b', 'area'),
            (r'\bdistrict\b', 'district'),
            (r'\bstate\b', 'state'),
            (r'\bregion\b', 'region'),
            (r'\btaluk\b', 'taluk'),
            (r"\bfather(?:[\'']s)?\s*name\b|\bdad(?:dy)?(?:[\'']s)?\s*name\b", 'father_name'),
            (r"\bmother(?:[\'']s)?\s*name\b|\bmom(?:my)?(?:[\'']s)?\s*name\b", 'mother_name'),
            (r'\bblood\s+group\b', 'blood_group'),
            (r'\b(?:date\s+of\s+birth|dob|birth\s+date)\b', 'dob'),
            (r'\bage\b', 'age'),
            (r'\bgender\b', 'gender'),
            (r'\breligion\b', 'religion'),
            (r'\bcaste\b', 'caste'),
            (r'\bbranch\b|\bdepartment\b', 'branch'),
            (r'\baadhar\b', 'aadhar_no'),
            (r'\bcurrent\s+sem(?:ester)?\b', 'current_sem'),
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
            requested.update({'usn', 'name'})
            return [{k: v for k, v in row.items() if k in requested} for row in rows]

    return rows

def _apply_dynamic_student_fields(rows: list[dict], intent: str | None = None,
                                  semester_filtered: bool = False) -> list[dict]:
    """Replace persisted semester metadata with the current value derived from each USN.

    For specific_field intent: never inject extra academic metadata (e.g. current_sem)
    that the user did not ask for — only refresh current_sem if it was already selected.
    """
    from graduation_manager import parse_usn_full

    # Exact single-field answers must stay narrow
    if intent == 'specific_field':
        enriched = []
        for row in rows:
            updated = dict(row)
            updated.pop('estimated_semester', None)
            usn = updated.get('usn')
            if usn:
                calculated = parse_usn_full(usn)
                if calculated:
                    if 'current_sem' in updated and not (semester_filtered and updated.get('current_sem')):
                        updated['current_sem'] = calculated.get('current_sem')
                    if 'branch' in updated and not updated.get('branch'):
                        updated['branch'] = calculated.get('branch')
            enriched.append(updated)
        return enriched

    enriched = []
    for row in rows:
        updated = dict(row)
        updated.pop('estimated_semester', None)
        usn = updated.get('usn')
        calculated = parse_usn_full(usn) if usn else None

        # Ensure address, branch, year_of_joining fallbacks are present
        if 'address' in updated and not updated.get('address'):
            updated['address'] = updated.get('permanent_address') or updated.get('current_address')
        if 'branch' in updated and not updated.get('branch') and calculated:
            updated['branch'] = calculated.get('branch')
        if 'year_of_joining' in updated and not updated.get('year_of_joining') and calculated:
            updated['year_of_joining'] = calculated.get('admission_batch')

        if not calculated:
            enriched.append(updated)
            continue
        for key in (
            'student_type', 'admission_batch', 'current_year', 'current_sem',
            'graduation_year', 'graduation_status',
        ):
            if key == 'current_sem' and semester_filtered and updated.get('current_sem'):
                # The query filtered on the stored semester; keep that value so the
                # displayed semester never contradicts the filter the user asked for.
                continue
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
        rows = [{**profile, **row} for row in academic]
        _attach_lifecycle_to_rows(usn, rows)
        return _apply_dynamic_student_fields(rows)
    # Personal-only student (no marks yet)
    if not profile:
        return []
    rows = [profile]
    _attach_lifecycle_to_rows(usn, rows)
    return _apply_dynamic_student_fields(rows)


def _attach_lifecycle_to_rows(usn: str, rows: list[dict]) -> None:
    """Attach current lifecycle status + audited history to profile rows so the
    complete-profile view (and its exports) show lifecycle without extra calls."""
    try:
        with db_conn() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT current_status, effective_date, last_enrolled_semester, "
                "last_enrolled_academic_year, scheme, reason, document_ref, updated_by "
                "FROM student_lifecycle_status WHERE usn=%s", (usn,))
            lc = cur.fetchone()
            cur.execute(
                "SELECT event_type, from_status, to_status, effective_date, "
                "requested_semester, approved_semester, rejoin_date, scheme, reason, "
                "approval_ref, remarks, actor_username, created_at "
                "FROM student_lifecycle_events WHERE usn=%s ORDER BY created_at ASC, id ASC",
                (usn,))
            events = cur.fetchall()
            cur.close()
        for row in rows:
            if lc:
                # The register is authoritative for a student's current status;
                # students.lifecycle_status is only the fallback when no register
                # row exists, so the profile and the Lifecycle tab never disagree.
                row["lifecycle_status"] = (lc.get("current_status")
                                           or row.get("lifecycle_status"))
                row["lifecycle_effective_date"] = str(lc.get("effective_date") or "")
                row["last_enrolled_semester"] = lc.get("last_enrolled_semester")
                row["lifecycle_scheme"] = lc.get("scheme")
                row["lifecycle_reason"] = lc.get("reason")
            if events:
                row["lifecycle_history"] = [
                    {k: (str(v) if hasattr(v, "isoformat") else v) for k, v in e.items()}
                    for e in events
                ]
    except Exception:
        pass


def _check_ambiguity(data: list[dict], nq: str, sql: str = "") -> dict | None:
    """
    If SQL returns multiple DISTINCT students by USN, and they share
    a similar name → return an ambiguity suggestion so user can choose.
    Returns None if no ambiguity (single student or genuinely different query).
    """
    if not data:
        return None

    # Identity disambiguation only makes sense for a lookup BY identity. When the
    # executed SQL filters on any student attribute (branch, district, cgpa, ...),
    # several students are the correct answer and must not be collapsed into a
    # "which student do you mean?" prompt that throws the whole result away.
    _where = sql.upper().find("WHERE")
    if _where != -1 and re.search(r"\bs\.(?!usn\b|name\b)[a-z_]+", sql[_where:], re.I):
        return None

    if re.search(r'\brural\b|\burban\b|\b(?:students?|student records?)\b.*\b(?:from|in|at|near)\b', nq, re.I):
        return None

    # CRITICAL: Never trigger ambiguity for multi-record filter queries.
    # These are intentionally supposed to return ALL matching students.
    if _MULTI_RECORD_FILTER_RE.search(nq):
        return None

    # Never trigger ambiguity for explicit list/filter queries
    _explicit_list_re = re.compile(
        r"\b(?:without|missing|no\s+(?:address|phone|email|blood|father|mother|cgpa|sgpa|village|emergency|aadhar|dob))\b|"
        r"\b(?:students?\s+(?:with|who\s+have|whose|having)\b)|"
        r"\b(?:list|show|display|find|get)\s+(?:all\s+)?students?\b|"
        r"\b(?:how\s+many|count\s+(?:of\s+)?students?)\b|"
        r"\b(?:born\s+in|admitted\s+in|joined\s+in|batch\s+of)\b|"
        r"\b(?:father|mother)\s+(?:name|is)\s+\S+\b|"
        r"\b(?:village|region|area|district)\s+(?:is\s+)?\S+\b",
        re.IGNORECASE,
    )
    if _explicit_list_re.search(nq):
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
        r'\b(all|every|list|top\s+\d+|show\s+all|display\s+all|compare|semester\s+\d|girls?|female|cgpa|how\s+many|count|village|branch|batch|year|without|missing|no\s+\w+)\b',
        re.IGNORECASE
    )
    if bulk_patterns.search(nq):
        return None

    # CRITICAL: Check if there is an exact name match with the search term
    term_upper = term.upper().strip()
    exact_matches = [r for r in data if (r.get("name") or "").upper().strip() == term_upper]
    if exact_matches:
        exact_usns = list(dict.fromkeys(r.get("usn", "") for r in exact_matches if r.get("usn")))
        if len(exact_usns) == 1:
            # UNIQUE EXACT MATCH! Filter data in-place to keep ONLY this student and return None!
            data[:] = [r for r in data if r.get("usn") == exact_usns[0]]
            return None

    # Build suggestion cards for each unique USN with real similarity scores
    from fuzzy_search import match_student
    suggestions = []
    for usn in usns[:6]:
        rows_for_usn = [r for r in data if r.get("usn") == usn]
        name = rows_for_usn[0].get("name", usn) if rows_for_usn else usn
        score = match_student(term, name)
        pct = round(score * 100)
        profile = get_student_profile(usn) or {}
        acad    = get_student_data(usn) or []
        enriched = [{**profile, **row} for row in acad] if acad else [profile]
        suggestions.append({
            "usn":     usn,
            "name":    name,
            "score":   score,
            "pct":     pct,
            "data":    enriched,
            "profile": profile,
        })

    suggestions.sort(key=lambda s: s["score"], reverse=True)

    return {
        "type":           "multiple_match",
        "search_term":    term,
        "confidence":     round(suggestions[0]["score"], 4) if suggestions else 1.0,
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
    Full profile queries combine the personal profile with academic data.
    """
    if intent != 'complete_profile':
        return data

    usns = list(dict.fromkeys(r.get("usn", "") for r in data if r.get("usn")))
    if len(usns) != 1:
        return data  # multi-student result — don't over-enrich

    usn = usns[0]
    return _build_full_profile_row(usn)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/suggest")
def suggest_students(q: str, current_user: dict = Depends(get_current_user)):
    """
    Live search suggestions for the frontend dropdown.
    Returns top-5 closest matches with score and match_type label.
    Never returns empty for partial inputs ≥ 2 chars if any match exists.
    """
    from fuzzy_search import get_live_suggestions, _normalize
    q = q.strip()
    # The search box sends the last word being typed. A Kannada request word is
    # not a name, so suggesting students for it only misleads staff.
    if kn_is_structural_word(q):
        return []
    suggestions = get_live_suggestions(q, limit=5)

    # Annotate each suggestion with a human-readable match_type
    q_norm = _normalize(q)
    for s in suggestions:
        name_norm = _normalize(s.get('name', ''))
        score = s.get('score', 0)
        if name_norm == q_norm or s.get('usn', '').lower() == q.lower():
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
    debug_enabled = bool(
        request.debug
        and os.getenv("APP_ENV", "development").casefold() not in {"production", "prod"}
    )
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

    normalized_nq, _ = kn_normalize_query(nq)
    security_query = " ".join((original_query, nq, normalized_nq))
    role = str(current_user.get("role", "")).strip().casefold()

    # Block TRUNCATE and DROP commands explicitly (with or without the TABLE keyword).
    if re.search(r'\bTRUNCATE\b', security_query, re.I) or re.search(r'\bDROP\s+(?:TABLE|DATABASE)\b', security_query, re.I) or re.search(r'\bDROP\s+TABLE\b', security_query, re.I):
        message = "This operation is permanently blocked. Destructive SQL commands are not allowed."
        _log_blocked_query(current_user, "BLOCKED_SQL_COMMAND", original_query)
        raise HTTPException(403, message)

    if is_delete_all_request(security_query):
        message = (
            "Delete permission is available only to Admin. Deleting all records is permanently blocked."
            if role == "staff"
            else "This operation is permanently blocked. Deleting the complete database is not allowed."
        )
        _log_blocked_query(current_user, "BLOCKED_DELETE_ALL", original_query)
        raise HTTPException(403, message)
    if role == "staff" and is_delete_request(security_query):
        _log_blocked_query(current_user, "BLOCKED_DELETE", original_query)
        raise HTTPException(
            403,
            "You are not allowed to perform this operation. Admin permission is required for deletion.",
        )

    # A request with no searchable content at all ("???", ".--", a stray space)
    # has nothing for the deterministic engine to parse, so it would reach the
    # LLM — which may answer it with an unfiltered SELECT and silently return
    # every student. Refuse locally instead. Deliberately Unicode-aware: Kannada
    # words are content, and a single-token query is still valid (it may be a
    # name or village), so only content-free input is rejected here.
    if not re.search(r"\w", security_query, re.UNICODE):
        raise HTTPException(
            400,
            "I couldn't find anything to search for in that request. Please "
            "type a USN, a name, or what you want to see — for example "
            '"top 5 students by cgpa".',
        )

    # Sprint 2: Detect language BEFORE intent check (for response labeling)
    # Use response_language from request if provided
    if not response_language or response_language == 'english':
        response_language = kn_detect_language(original_query)

    # Sprint 2: Normalize Kannada/mixed queries for intent detection
    # (This is now redundant if translation happened, but kept for backward compat)
    # Use normalized query for intent detection (keeps existing engine intact)
    intent = _detect_intent(normalized_nq)
    # Also check original query for Kannada complete-profile phrases
    if intent != 'complete_profile' and is_complete_profile_intent(original_query):
        intent = 'complete_profile'

    # Fee updates are checked FIRST and route to the dedicated, Admin-confirmed
    # fee editor. This gate is independent of _build_update_request (below) on
    # purpose: that students-column parser mis-glues a "USN year N" phrase into a
    # single USN token and 404s on fee phrasing like "update VTU fee of X year 1
    # to Paid". The fee detector is narrow — it needs an update imperative AND the
    # word "fee" AND a known fee type (VTU/PD/IDP/tuition) — so reads and ordinary
    # students-column edits are never captured.
    if re.match(r'^\s*(?:update|mark|set|change|record)\b', nq, re.I):
        from routes_update import prepare_fee_preview, is_fee_command
        if is_fee_command(nq):
            fee_preview = prepare_fee_preview(nq, current_user.get("username", ""))
            # A fee command is always claimed here — confirmed edits (Admin), an
            # ambiguous student, or a phrasing that still needs a year all return
            # an actionable message rather than silently mis-executing.
            if fee_preview.get("action_required") in ("confirm", "select_student", "no_record", "clarify"):
                return fee_preview

    # Lifecycle RECORD commands typed into the main search bar are routed to the
    # audited lifecycle preview (Staff may preview; only Admin confirms), so a
    # "discontinue / mark dropout / rejoin USN …" from here never becomes a read.
    # We require an explicit record imperative OR a concrete USN so that plain
    # reads ("discontinued students", "students who rejoined") stay reads.
    _record_text = next((t for t in (nq, normalized_nq)
                         if _is_searchbar_lifecycle_record(t)), None)
    if _record_text is not None:
        from routes_lifecycle import _prepare_lifecycle_payload
        preview = _prepare_lifecycle_payload(
            original_query, language, None, current_user.get("username", ""))
        preview = dict(preview)
        preview["action_type"] = "LIFECYCLE"
        preview["confirm_endpoint"] = "/api/lifecycle/nl/confirm"
        if preview.get("action_required") == "confirm":
            preview["role_restricted"] = "Admin"
        return preview

    partial_update = (_build_update_request(nq)
                      if _UPDATE_INTENT_RE.match(nq) else None)
    if partial_update and partial_update.get("action_required") == "select_student":
        return {"action_required": "select_student", "suggestions": partial_update["suggestions"], "message": partial_update["message"]}

    # Deterministic single-student ADD (does not depend on the LLM being reachable).
    insert_request = _build_insert_request(nq)
    if insert_request and insert_request.get("action_required") == "select_student":
        return {
            "action_required": "select_student",
            "suggestions": insert_request.get("suggestions", []),
            "message": insert_request.get("message", ""),
        }

    # Admin targeted delete → resolve to a single USN-scoped DELETE for confirmation.
    # (Staff deletes and delete-all are already blocked above.)
    delete_request = None
    if role == "admin" and is_delete_request(security_query):
        delete_request = _build_delete_request(nq)
        if delete_request and delete_request.get("action_required") == "select_student":
            return {
                "action_required": "select_student",
                "suggestions": delete_request.get("suggestions", []),
                "message": delete_request.get("message", ""),
            }

    deterministic_query = build_deterministic_student_query(normalized_nq)

    # Cache lookup (SELECT only)
    cached_sql, cached_result = _get_cache(nq) if not deterministic_query else (None, None)
    if cached_sql and cached_result is not None:
        if cached_sql.strip().upper().startswith("SELECT"):
            cached_result = _apply_dynamic_student_fields(cached_result, intent=intent)
            cached_result = _filter_by_intent(cached_result, intent, nq)
            count_and_list = bool(re.search(
                r"COUNT\(\*\)\s+OVER\s*\(\s*\)\s+AS\s+total_count", cached_sql, re.I
            ))
            total_count = None
            if count_and_list:
                total_count = cached_result[0].get("total_count", len(cached_result)) if cached_result else 0
                cached_result = [
                    {key: value for key, value in row.items() if key != "total_count"}
                    for row in cached_result
                ]
            is_scalar = (
                not count_and_list and (intent == 'scalar_number' or
                (len(cached_result) == 1 and len(cached_result[0]) == 1 and
                 (isinstance(list(cached_result[0].values())[0], (int, float)) or
                 re.search(r'\bhow\s+many\b|\bcount\b', nq, re.I))))
            )
            scalar_val = list(cached_result[0].values())[0] if (is_scalar and cached_result) else None
            return {
                "action_required": "none",
                "query": cached_sql if debug_enabled else None,
                "data": mask_rows_for_role(cached_result, current_user["role"]),
                "execution_time": round(time.time() - start, 4),
                "cached": True,
                "intent": intent,
                "is_scalar_number": is_scalar,
                "scalar_value": scalar_val,
                "total_count": total_count,
            }


    if partial_update:
        result = {"success": True, "query_dict": partial_update}
    elif insert_request:
        result = {"success": True, "query_dict": insert_request}
    elif delete_request:
        result = {"success": True, "query_dict": delete_request}
    else:
        result = (
            {"success": True, "query_dict": deterministic_query}
            if deterministic_query
            else generate_sql_query(nq, current_user["role"])
        )
    if not result["success"]:
        error_message = str(result.get("error_msg", ""))
        if error_message.startswith("ERROR:"):
            raise HTTPException(
                503,
                "AI service temporarily unavailable. This query could not be safely resolved locally.",
            )
        raise HTTPException(400, "Could not generate a safe database query.")

    query_dict = _enforce_specific_select(nq, result["query_dict"])
    # A structured update skips the SQL-shape validation below, so the role rule
    # is checked here instead: a reader must not be handed a confirm button for
    # a change the server is only going to refuse after they press it.
    if str(query_dict.get('operation', '')).lower() in {'insert', 'update', 'delete'} \
            and str(current_user.get('role', '')).strip().casefold() not in {'admin', 'staff'}:
        raise HTTPException(403, "Only Staff and Admin can change student records.")
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
            if str(query_dict.get("operation", "")).casefold() == "delete":
                if role == "staff":
                    raise HTTPException(403, "Delete permission is available only to Admin.")
                raise HTTPException(403, "Delete-all operation is permanently blocked or the target is invalid.")
            # Non-delete failure: the generated plan could not be mapped safely to
            # the schema. This is a query-understanding problem, not a permission
            # one, so ask for a simpler phrasing rather than reporting "invalid
            # student data" (which mis-attributes it to the user's records).
            raise HTTPException(
                400,
                "I could not understand that request safely. Please try a simpler "
                "wording, for example \"students whose father is a farmer\".",
            )

    op = query_dict.get("operation", "").lower()

    if op in {"insert", "delete"} or (op == "update" and query_dict.get('executions')):
        response = {
            "action_required": "confirm",
            "action_type": op.upper(),
            "query": query_dict.get("sql", ""),
            "query_dict": query_dict,
            "original_query": nq,
            "data": [],
            "execution_time": 0,
            # INSERT/UPDATE previews carry a human sentence naming the student and
            # the values about to change; staff confirm on that, not on SQL.
            **({"message": query_dict["message"]} if query_dict.get("message") else {}),
        }
        if op == "delete":
            response["confirmation_token"] = create_confirmation_token(
                query_dict, current_user["username"]
            )
            response["message"] = query_dict.get(
                "message",
                "Warning: This will permanently remove the selected student data. Do you want to continue?",
            )
            response["student_name"] = query_dict.get("student_name")
            response["student_usn"] = query_dict.get("student_usn")
        return response

    try:
        count_and_list = bool(re.search(
            r"COUNT\(\*\)\s+OVER\s*\(\s*\)\s+AS\s+total_count",
            query_dict.get("sql", ""),
            re.I,
        ))
        data = _run_query(query_dict)
        query_ast = query_dict.get("ast") if deterministic_query else None
        total_count = None
        if count_and_list:
            total_count = data[0].get("total_count", len(data)) if data else 0
            data = [
                {key: value for key, value in row.items() if key != "total_count"}
                for row in data
            ]
        if query_ast and (query_ast.get("intent") != "COUNT" or count_and_list):
            if any(not _row_satisfies_filter_ast(row, query_ast) for row in data):
                raise HTTPException(500, "Database results did not satisfy every requested filter.")
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
            # Check if this is a father name query (which should use fuzzy fallback)
            is_father_query = bool(re.search(r"\b(?:father(?:['’]s)?|dad(?:['’]s)?)\s+name\b", nq, re.I))

            if deterministic_query and not is_father_query or intent in {'location_search', 'rural_search', 'urban_search', 'scalar_number'}:
                response = {
                    "action_required": "none",
                    "query": query_dict["sql"] if debug_enabled else None,
                    "data": [],
                    "execution_time": round(elapsed, 4),
                    "cached": False,
                    "intent": intent,
                    "no_match_message": (
                        query_dict["message"] if query_dict.get("message") else
                        (f"No students matched all {len(query_ast['conditions'])} requested conditions."
                         if query_ast else "No students matched the requested filters.")
                    ),
                    "query_ast": _public_query_ast(query_ast),
                    **({"query_debug": {
                        "original_query": original_query,
                        "normalized_query": normalized_nq,
                        "intent": intent,
                        "conditions": query_ast["conditions"] if query_ast else [],
                        "sql": query_dict["sql"],
                        "parameters": query_dict.get("params", []),
                        "execution_time": round(elapsed, 4),
                        "returned_row_count": 0,
                        "validation": "PASS",
                    }} if debug_enabled else {}),
                }
                if count_and_list:
                    response["total_count"] = 0
                return response

            suggestion = smart_fallback(nq)
            stype = suggestion.get('type', 'no_match')

            if stype == 'no_match' or not suggestion.get('suggestions'):
                return {
                    "action_required": "none",
                    "query": query_dict["sql"] if debug_enabled else None,
                    "data": [],
                    "execution_time": round(elapsed, 4),
                    "cached": False,
                    "no_match_message": suggestion.get('message', 'No matching records available.'),
                }

            if suggestion.get('auto_corrected'):
                top_data = []
                for s in suggestion['suggestions']:
                    if 'father_name' in s:
                        top_data.append({
                            'usn': s['usn'],
                            'name': s['name'],
                            'father_name': s['father_name']
                        })
                    else:
                        top_data.extend(_filter_by_intent(s.get('data', []), intent, nq))

                return {
                    "action_required": "none",
                    "query": query_dict["sql"] if debug_enabled else None,
                    "data": top_data,
                    "execution_time": round(elapsed, 4),
                    "cached": False,
                    "auto_corrected": True,
                    "correction_message": suggestion['message'],
                    "suggestion": suggestion,
                    "intent": intent,
                }

            # suggestion | possible_matches | multiple_match
            # For father name possible_matches, also show the suggestions
            if stype == 'possible_matches' and suggestion.get('suggestions'):
                # Format suggestions for father name queries
                formatted_suggestions = []
                for s in suggestion.get('suggestions', []):
                    formatted_suggestions.append({
                        'usn': s['usn'],
                        'name': s['name'],
                        'father_name': s.get('father_name', ''),
                        'score': s['score']
                    })
                return {
                    "action_required": "none",
                    "query": query_dict["sql"] if debug_enabled else None,
                    "data": [],
                    "execution_time": round(elapsed, 4),
                    "cached": False,
                    "suggestion": {
                        **suggestion,
                        'suggestions': formatted_suggestions
                    },
                    "intent": intent,
                }

            return {
                "action_required": "none",
                "query": query_dict["sql"] if debug_enabled else None,
                "data": [],
                "execution_time": round(elapsed, 4),
                "cached": False,
                "suggestion": suggestion,
                "intent": intent,
            }

        # Keep calculated academic metadata current — but never inject extras
        # into narrow single-field answers.
        _exec_sql = (query_dict or {}).get("sql", "") if isinstance(query_dict, dict) else ""
        _sem_filtered = bool(re.search(r"current_sem\s*(?:=|!=|<>|>=|<=|>|<)", _exec_sql, re.I))
        data = _apply_dynamic_student_fields(data, intent=intent, semester_filtered=_sem_filtered)

        # ── Multi-student ambiguity check (SQL returned > 1 student) ─────────
        # Structured attribute-filter queries (blood group, age, branch, semester,
        # area, missing-data, OR/negation, ...) are explicit list queries, not
        # identity lookups. Multiple rows are the expected result, so they must
        # never be collapsed into a "which student?" disambiguation prompt.
        ambiguity = None if deterministic_query else _check_ambiguity(
            data, nq, (query_dict or {}).get("sql", ""))
        if ambiguity:
            return {
                "action_required": "none",
                "query": query_dict["sql"] if debug_enabled else None,
                "data": [],
                "execution_time": round(elapsed, 4),
                "cached": False,
                "suggestion": ambiguity,
                "intent": intent,
            }

        # ── Single student full-profile enrichment ────────────────────────────
        data = _enrich_with_profile(data, nq, intent)

        # ── Intent-based column filtering (exact scope last) ──────────────────
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

        is_scalar = not count_and_list and (
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
            "query": query_dict["sql"] if debug_enabled else None,
            # The cache keeps the real rows (an Admin may answer the same question
            # next); the answer this caller gets is masked for their role.
            "data": mask_rows_for_role(data, current_user["role"]),
            "execution_time": round(elapsed, 4),
            "cached": False,
            "intent": intent,
            "response_language": response_language,
            "is_scalar_number": is_scalar,
            "scalar_value": scalar_val,
            "total_count": total_count,
            "query_ast": _public_query_ast(query_ast),
            **({"message": query_dict["message"]} if query_dict.get("message") else {}),
            **({"query_debug": {
                "original_query": original_query,
                "normalized_query": normalized_nq,
                "intent": intent,
                "conditions": query_ast["conditions"] if query_ast else [],
                "sql": query_dict["sql"],
                "parameters": query_dict.get("params", []),
                "execution_time": round(elapsed, 4),
                "returned_row_count": len(data),
                "validation": "PASS" if query_ast else "NOT_APPLICABLE",
            }} if debug_enabled else {}),
        }


    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        elapsed = time.time() - start
        suggestion = smart_fallback(nq)
        stype = suggestion.get('type', 'no_match') if suggestion else 'no_match'

        _actionable = {'suggestion', 'possible_matches', 'multiple_match'}
        if suggestion and stype in _actionable and suggestion.get('suggestions'):
            if suggestion.get('auto_corrected'):
                top_data = []
                for s in suggestion['suggestions']:
                    if 'data' in s:
                        top_data.extend(_filter_by_intent(s['data'], intent, nq))
                    elif 'father_name' in s:
                        top_data.append({
                            'usn': s['usn'],
                            'name': s['name'],
                            'father_name': s['father_name']
                        })

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


def _sync_backlogs_from_column(cur, conn, usns: list) -> None:
    """Keep the structured `student_backlogs` table consistent with the free
    text `students.backlogs` column that a natural-language update just wrote.

    The update engine sets `students.backlogs` directly, which historically left
    `student_backlogs` stale — so a backlog the staff marked 'cleared'/'no' still
    appeared in reports. This runs in the SAME transaction as the update (so it
    is covered by the undo snapshot) and, per student:
      - no-backlog text ("cleared", "none", "0", ...)  -> mark rows cleared=1
      - descriptive text (subjects/sem/year or a count) -> replace rows
      - empty text                                      -> leave rows untouched
    """
    if not usns:
        return
    from routes_files import _is_no_backlog, _upsert_backlogs
    placeholders = ",".join(["%s"] * len(usns))
    cur.execute(
        f"SELECT usn, backlogs FROM students WHERE usn IN ({placeholders})",
        tuple(usns),
    )
    rows = cur.fetchall()
    # The caller's cursor may be a plain tuple cursor; normalise to (usn, text).
    pairs = []
    for r in rows:
        if isinstance(r, dict):
            pairs.append((r.get("usn"), r.get("backlogs")))
        else:
            pairs.append((r[0], r[1]))
    for usn, text in pairs:
        if not usn:
            continue
        cleaned = "" if text is None else str(text).strip()
        if cleaned == "":
            continue
        if _is_no_backlog(cleaned):
            cur.execute(
                "UPDATE student_backlogs SET cleared=1 WHERE usn=%s AND cleared=0",
                (usn,),
            )
        else:
            cur.execute("DELETE FROM student_backlogs WHERE usn=%s", (usn,))
            _upsert_backlogs(cur, usn, cleaned)


@router.post("/execute")
def execute_confirmed(
    request: ExecuteRequest,
    current_user: dict = Depends(require_roles("Admin", "Staff")),
):

    op  = request.query_dict.get("operation", "").lower()
    sql = request.query_dict.get("sql", "")
    if op == 'update' and request.query_dict.get('executions'):
        update_error = _validate_structured_update(request.query_dict)
        if update_error:
            raise HTTPException(400, update_error)
    else:
        validation = validate_sql_query(request.query_dict, current_user["role"])
        if not validation["is_valid"]:
            if op == "delete" and current_user["role"].strip().casefold() != "admin":
                raise HTTPException(403, "Delete permission is available only to Admin.")
            if op == "delete":
                raise HTTPException(403, "Delete-all operation is permanently blocked or the target is invalid.")
            raise HTTPException(403, "Invalid student data.")

    if op == "delete":
        if current_user["role"].strip().casefold() != "admin":
            raise HTTPException(403, "Delete permission is available only to Admin.")
        if not request.confirmed:
            raise HTTPException(400, "Please confirm deletion.")
        if not request.confirmation_token or not verify_confirmation_token(
            request.confirmation_token, request.query_dict, current_user["username"]
        ):
            raise HTTPException(403, "Delete confirmation is invalid or expired. Please submit the query again.")

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
                # The client posts this SQL verbatim, so the identity column the
                # whole record hangs on is re-checked here, not only in /generate.
                from routes_files import _valid_usn
                if not _valid_usn(str(usn).strip()):
                    raise HTTPException(400, "Invalid USN format.")
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
                        # A deleted student must not leave orphaned child rows:
                        # fee and backlog aggregates read those tables directly,
                        # and provenance rows would name a source file for a
                        # student that no longer exists.
                        cur.execute(f"DELETE FROM marks WHERE usn IN ({placeholders})", tuple(affected_usns))
                        cur.execute(f"DELETE FROM student_fees WHERE usn IN ({placeholders})", tuple(affected_usns))
                        cur.execute(f"DELETE FROM student_backlogs WHERE usn IN ({placeholders})", tuple(affected_usns))
                        cur.execute(f"DELETE FROM student_field_sources WHERE usn IN ({placeholders})", tuple(affected_usns))

                if op == "update" and request.query_dict.get('executions'):
                    for creation in { (c['table'], c['column']): c for c in request.query_dict.get('column_creations', []) }.values():
                        _create_column_if_missing(cur, conn, creation['table'], creation['column'], creation['data_type'])
                    affected_rows = 0
                    for execution in request.query_dict.get('executions', []):
                        cur.execute(execution['sql'], tuple(execution['params']))
                        affected_rows += cur.rowcount
                    touched_backlogs = any(
                        "students" in e["sql"].lower() and "backlogs" in e["sql"].lower()
                        for e in request.query_dict.get('executions', [])
                    )
                    if touched_backlogs:
                        _sync_backlogs_from_column(cur, conn, request.query_dict.get('affected_usns', []))
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
def sync_vtu(current_user: dict = Depends(require_roles("Admin", "Staff"))):
    # A bulk rewrite of every student's current semester. The role used to be
    # checked here with a `return {"success": False}`, which answered HTTP 200 to
    # a refusal — the caller could not tell a denied request from a completed sync.
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
    # A saved question is itself data: "students of X with Y" names a student.
    # Before, only Staff was filtered and everyone else — Viewer included — read
    # the whole table, i.e. the Admins' and Staffs' questions.
    #
    # `query_history` records `user_role` and no `username`, so the strongest
    # isolation the stored schema allows is by role. Per-person history needs a
    # column, which is a schema change the owner has not authorised.
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        if str(current_user["role"]).strip().casefold() == "admin":
            cur.execute(
                "SELECT * FROM query_history ORDER BY timestamp DESC LIMIT %s", (limit,)
            )
        else:
            cur.execute(
                "SELECT * FROM query_history WHERE user_role=%s "
                "ORDER BY timestamp DESC LIMIT %s",
                (current_user["role"], limit)
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

        cur.execute("SELECT COUNT(*) AS total FROM uploaded_files WHERE trashed_at IS NULL")
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


# Declared before /profile/{usn}: FastAPI matches routes in declaration order,
# so a later static path under the same prefix would be swallowed by the dynamic
# one and this door would be unreachable (D60).
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

    # Serialize dates / decimals, masked for the role that asked. A profile card
    # is the most PII-dense screen in the app, so it follows the same policy as
    # the reports: only Admin sees an identity number in full.
    personal = _serialize_row(mask_rows_for_role(personal_row, current_user["role"]))

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


# ── Student Fees endpoint ──────────────────────────────────────────────────────

@router.get("/students/{usn}/fees")
def get_student_fees(usn: str, current_user: dict = Depends(get_current_user)):
    """Return all fee records for a student from student_fees table."""
    normalized = _normalize_usn(usn)
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        # Try exact USN first, then normalised
        cur.execute(
            "SELECT sf.* FROM student_fees sf "
            "JOIN students s ON UPPER(REPLACE(REPLACE(REPLACE(s.usn,' ',''),'-',''),'.','')) = %s "
            "WHERE sf.usn = s.usn "
            "ORDER BY sf.fee_type, sf.year",
            (normalized,)
        )
        rows = cur.fetchall()
        cur.close()
    for r in rows:
        if r.get('updated_at'):
            r['updated_at'] = str(r['updated_at'])
    return rows


# ── Student Backlogs endpoint ──────────────────────────────────────────────────

@router.get("/students/{usn}/backlogs")
def get_student_backlogs(usn: str, current_user: dict = Depends(get_current_user)):
    """Return the active (uncleared) backlog records for a student.

    Honors both signals that a backlog is gone: the structured `cleared` flag and
    the free-text `students.backlogs` column a natural-language update writes
    (e.g. 'cleared'/'none'), so a cleared backlog stops showing immediately.
    """
    normalized = _normalize_usn(usn)
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT sb.*, s.backlogs AS backlog_text FROM student_backlogs sb "
            "JOIN students s ON UPPER(REPLACE(REPLACE(REPLACE(s.usn,' ',''),'-',''),'.','')) = %s "
            "WHERE sb.usn = s.usn AND sb.cleared = 0 "
            "ORDER BY sb.semester, sb.subject",
            (normalized,)
        )
        rows = cur.fetchall()
        cur.close()
    import report_service
    if rows and report_service._text_is_no_backlog(rows[0].get("backlog_text")):
        rows = []
    for r in rows:
        r.pop("backlog_text", None)
        if r.get('updated_at'):
            r['updated_at'] = str(r['updated_at'])
    return rows
