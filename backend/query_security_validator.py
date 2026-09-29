import re


_READ_OPERATIONS = {"SELECT"}
_WRITE_OPERATIONS = {"INSERT", "UPDATE", "DELETE"}
_ALLOWED_READ_TABLES = {"students", "marks", "uploaded_files"}
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
    if operation in _WRITE_OPERATIONS:
        shape_error = _validate_write_shape(sql, operation)
        if shape_error:
            return {"is_valid": False, "reason": shape_error}

    role = str(user_role).strip().lower()
    if role == "admin":
        if operation not in _READ_OPERATIONS:
            return {"is_valid": False, "reason": "Admin role is restricted to read operations only."}
    elif role == "staff":
        if operation not in _READ_OPERATIONS | _WRITE_OPERATIONS:
            return {"is_valid": False, "reason": f"Operation '{operation}' is not allowed."}
    else:
        return {"is_valid": False, "reason": f"Unknown role: {user_role}"}

    return {"is_valid": True, "reason": "Valid"}
