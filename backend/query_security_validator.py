import hashlib
import hmac
import json
import re
import time

from config import settings


_READ_OPERATIONS = {"SELECT"}
_WRITE_OPERATIONS = {"INSERT", "UPDATE", "DELETE"}
_ALLOWED_READ_TABLES = {
    "students", "marks", "uploaded_files",
    # New tables added for extended Google Form fields
    "student_fees", "student_backlogs",
    # Student Lifecycle Management (read-only through the NL query engine)
    "student_lifecycle_status", "student_lifecycle_events", "readmission_requests",
    # Subquery aliases and CTEs — these are virtual table names, not real tables
    "sub",
}
_LITERAL = re.compile(r'''(?:'(?:\\.|''|[^'\\])*'|"(?:\\.|""|[^"\\])*"|[-+]?\d+(?:\.\d+)?|NULL)''', re.I)
_USN_FILTER = re.compile(
    r"\s*(?:s\.)?`?usn`?\s*=\s*'(?:\\.|''|[^'\\])*'\s*",
    re.I,
)
_DANGEROUS_READS = re.compile(
    r"\bINTO\b|\bLOAD_FILE\s*\(|"
    r"\b(?:SLEEP|BENCHMARK|GET_LOCK|RELEASE_LOCK|IS_FREE_LOCK|IS_USED_LOCK)\s*\(|"
    r"\bFOR\s+UPDATE\b|\bLOCK\s+IN\s+SHARE\s+MODE\b",
    re.I,
)
_DELETE_ACTION = re.compile(
    r"\b(?:delete|remove|erase|clear|truncate|drop|wipe|clean|destroy|purge|nuke|obliterate|annihilate|scrub|zap)\b|"
    r"ಅಳಿಸ|ಡಿಲೀಟ್|ತೆಗೆದುಹಾಕ|ಕ್ಲಿಯರ್|ವಿನಾಶ|ಶುದ್ಧೀಕರಿಸ|పోగొట్టు|తొలగించు|విద్యార్థి.*అళిస",
    re.I,
)
_DELETE_NEGATION = re.compile(
    r"\b(?:do\s+not|don't|never|cancel|stop)\b.{0,32}\b"
    r"(?:delete|remove|erase|clear|truncate|drop|wipe)\b",
    re.I,
)
_DELETE_ALL_MARKER = re.compile(
    r"\b(?:all|every|everything|entire|whole|complete)\b|"
    r"ಎಲ್ಲಾ|ಎಲ್ಲ|ಸಂಪೂರ್ಣ|ಪೂರ್ಣ|అన్ని",
    re.I,
)
_DELETE_ENTITY = re.compile(
    r"\b(?:students?|records?|data|database|tables?|dataset|everything)\b|"
    r"ವಿದ್ಯಾರ್ಥಿ|ಡೇಟಾ|ದಾಖಲೆ|ಡೇಟಾಬೇಸ್|ಟೇಬಲ್|విద్యార్థి|డేటా|డేటాబేస్",
    re.I,
)
_GLOBAL_DELETE_TARGET = re.compile(
    r"\b(?:database|tables?|dataset)\b|ಡೇಟಾಬೇಸ್|ಟೇಬಲ್|డేటాబేస్",
    re.I,
)
# A raw "DELETE FROM <table>" with no WHERE clause wipes the whole table.
_RAW_DELETE_NO_WHERE = re.compile(
    r"\bdelete\s+from\s+`?(?:students?|marks|uploaded_files|student_db)`?\b(?!\s+where\b)",
    re.I,
)
# TRUNCATE TABLE command also wipes the whole table
_RAW_TRUNCATE = re.compile(
    r"\btruncate\s+table\s+`?(?:students?|marks|uploaded_files|student_db)`?\b",
    re.I,
)
# Raw SQL DELETE with a WHERE clause that matches every row (tautology/broad wildcard).
_RAW_DELETE_BROAD_WHERE = re.compile(
    r"\bdelete\s+from\s+`?(?:students?|marks|uploaded_files|student_db)`?\b\s+where\b.*?"
    r"(?:\b1\s*=\s*1\b|\btrue\b|\b(?:or|and)\s+1\b|\b(?:or|and)\s+true\b|"
    r"like\s*['\"][%_]['\"]|\bis\s+not\s+null\b|\busn\s+like\b|"
    r"\btrue\b.*?\bor\b|\bor\b.*?\btrue\b|"
    r"\b1\b.*?\bor\b|\bor\b.*?\b1\b)",
    re.I | re.S,
)


def is_delete_request(text: str) -> bool:
    normalized = str(text or "").strip()
    if _DELETE_NEGATION.search(normalized):
        return False
    return bool(_DELETE_ACTION.search(normalized))


def is_delete_all_request(text: str) -> bool:
    normalized = str(text or "").strip()
    if not is_delete_request(normalized):
        return False
    if _GLOBAL_DELETE_TARGET.search(normalized):
        return True
    if _RAW_DELETE_NO_WHERE.search(normalized):
        return True
    if _RAW_TRUNCATE.search(normalized):
        return True
    if _RAW_DELETE_BROAD_WHERE.search(normalized):
        return True
    return bool(_DELETE_ALL_MARKER.search(normalized) and _DELETE_ENTITY.search(normalized))


def create_confirmation_token(query_dict: dict, username: str, issued_at: int | None = None) -> str:
    timestamp = int(time.time()) if issued_at is None else int(issued_at)
    serialized_query = json.dumps(query_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    payload = f"{timestamp}\n{username}\n{serialized_query}".encode("utf-8")
    secret = str(settings.JWT_SECRET_KEY or "").encode("utf-8")
    if not secret:
        raise ValueError("Delete confirmations require a configured signing secret.")
    signature = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return f"{timestamp}.{signature}"


def verify_confirmation_token(
    token: str, query_dict: dict, username: str, now: int | None = None, max_age_seconds: int = 300
) -> bool:
    try:
        timestamp_text, supplied_signature = token.split(".", 1)
        timestamp = int(timestamp_text)
        current_time = int(time.time()) if now is None else int(now)
        if timestamp > current_time + 30 or current_time - timestamp > max_age_seconds:
            return False
        expected = create_confirmation_token(query_dict, username, timestamp).split(".", 1)[1]
        return hmac.compare_digest(supplied_signature, expected)
    except (AttributeError, TypeError, ValueError):
        return False


def _scan_sql(sql: str) -> tuple[str | None, str]:
    """Mask string literals and reject comments, unterminated quotes, and stacked statements."""
    masked = []
    quote = None
    index = 0
    while index < len(sql):
        char = sql[index]
        if quote:
            if char == "\\" and quote != "`":
                masked.extend("  ")
                index += 2
                continue
            if char == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    masked.extend("  ")
                    index += 2
                    continue
                quote = None
            masked.append(" " if quote != "`" else char)
            index += 1
            continue

        if char in ("'", '"', "`"):
            quote = char
            masked.append(" ")
            index += 1
            continue
        if sql.startswith("--", index) or sql.startswith("/*", index) or char == "#":
            return None, "SQL comments are not allowed."
        if char == ";":
            if sql[index + 1 :].strip(" ;\t\r\n") or ";" in sql[index + 1 :]:
                return None, "Only one SQL statement is allowed."
            index += 1
            continue
        masked.append(char)
        index += 1

    if quote:
        return None, "SQL contains an unterminated quoted value."
    return "".join(masked), ""


def _split_csv(expression: str) -> list[str] | None:
    values = []
    start = 0
    quote = None
    index = 0
    while index < len(expression):
        char = expression[index]
        if quote:
            if char == "\\" and quote != "`":
                index += 2
                continue
            if char == quote:
                if index + 1 < len(expression) and expression[index + 1] == quote:
                    index += 2
                    continue
                quote = None
        elif char in ("'", '"', "`"):
            quote = char
        elif char == ",":
            values.append(expression[start:index].strip())
            start = index + 1
        index += 1
    if quote:
        return None
    values.append(expression[start:].strip())
    return values


def _validate_write_shape(sql: str, operation: str) -> str | None:
    if operation == "UPDATE":
        match = re.fullmatch(
            r"(?is)\s*UPDATE\s+`?students`?\s+SET\s+(.+?)\s+WHERE\s+(.+?)\s*;?\s*",
            sql,
        )
        if not match or not _USN_FILTER.fullmatch(match.group(2)):
            return "UPDATE must target one student using an exact USN filter."
        assignments = _split_csv(match.group(1))
        if not assignments:
            return "UPDATE assignments are invalid."
        for assignment in assignments:
            item = re.fullmatch(r"\s*`?([A-Za-z_][A-Za-z0-9_]*)`?\s*=\s*(.+?)\s*", assignment, re.S)
            if not item or item.group(1).lower() in {"usn", "student_id"} or not _LITERAL.fullmatch(item.group(2)):
                return "UPDATE assignments must use simple columns and literal values."
        return None

    if operation == "DELETE":
        match = re.fullmatch(
            r"(?is)\s*DELETE\s+FROM\s+`?students`?\s+WHERE\s+(.+?)\s*;?\s*",
            sql,
        )
        if not match or not _USN_FILTER.fullmatch(match.group(1)):
            return "DELETE must target one student using an exact USN filter."
        return None

    if operation == "INSERT":
        match = re.fullmatch(
            r"(?is)\s*INSERT\s+INTO\s+`?students`?\s*\(([^)]+)\)\s*VALUES\s*\((.*)\)\s*;?\s*",
            sql,
        )
        if not match:
            return "INSERT is allowed only for literal student values."
        columns = _split_csv(match.group(1))
        values = _split_csv(match.group(2))
        if not columns or not values or len(columns) != len(values):
            return "INSERT columns and values do not match."
        normalized_columns = []
        for column in columns:
            item = re.fullmatch(r"\s*`?([A-Za-z_][A-Za-z0-9_]*)`?\s*", column)
            if not item:
                return "INSERT column names are invalid."
            normalized_columns.append(item.group(1).lower())
        if "usn" not in normalized_columns or len(set(normalized_columns)) != len(normalized_columns):
            return "INSERT must provide one unique student USN."
        if any(not _LITERAL.fullmatch(value) for value in values):
            return "INSERT values must be literals."
        return None
    return None


def validate_sql_query(query_dict, user_role: str) -> dict:
    if isinstance(query_dict, str):
        sql = query_dict
        declared_operation = None
    elif isinstance(query_dict, dict):
        sql = query_dict.get("sql", "")
        declared_operation = query_dict.get("operation")
    else:
        return {"is_valid": False, "reason": "Query must be SQL text or a query object."}

    if not isinstance(sql, str) or not sql.strip():
        return {"is_valid": False, "reason": "SQL query is empty or invalid."}
    if "$" in sql or re.search(r"\b(?:aggregate|pipeline)\b", sql, re.I):
        return {"is_valid": False, "reason": "MongoDB syntax is strictly forbidden."}

    masked_sql, scan_error = _scan_sql(sql)
    if scan_error:
        return {"is_valid": False, "reason": scan_error}

    operation_match = re.match(r"\s*(\w+)", sql)
    operation = operation_match.group(1).upper() if operation_match else ""
    if declared_operation and str(declared_operation).upper() != operation:
        return {"is_valid": False, "reason": "Declared operation does not match the SQL statement."}

    if operation == "SELECT":
        referenced_tables = re.findall(
            r"\b(?:FROM|JOIN)\s+`?([A-Za-z_][A-Za-z0-9_]*)`?",
            masked_sql,
            re.I,
        )
        if not referenced_tables or any(
            table.lower() not in _ALLOWED_READ_TABLES for table in referenced_tables
        ):
            return {"is_valid": False, "reason": "Queries may read only student, marks, and uploaded-file data."}

    if operation in _READ_OPERATIONS and _DANGEROUS_READS.search(masked_sql):
        return {"is_valid": False, "reason": "Unsafe read operation is not allowed."}
    role = str(user_role).strip().lower()
    if operation not in _READ_OPERATIONS | _WRITE_OPERATIONS:
        return {"is_valid": False, "reason": f"Operation '{operation}' is not allowed."}
    # A Viewer/Student is a reader, not a writer: their questions used to be
    # refused here with "Unknown role", which the route then reported as
    # "I could not understand that request" — a reading role was locked out of
    # the one feature the app exists for, and the message blamed their English.
    # Reads are open to any authenticated role; the PII each role may see is
    # decided by report_service.mask_for_role on the way out.
    if operation in _WRITE_OPERATIONS and role not in {"admin", "staff"}:
        return {"is_valid": False, "reason": f"Role {user_role} may not change student data."}
    if operation == "DELETE" and role != "admin":
        return {"is_valid": False, "reason": "Delete permission is available only to Admin."}

    if operation in _WRITE_OPERATIONS:
        shape_error = _validate_write_shape(sql, operation)
        if shape_error:
            return {"is_valid": False, "reason": shape_error}

    return {"is_valid": True, "reason": "Valid"}
