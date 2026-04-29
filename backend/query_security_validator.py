import re

FORBIDDEN_OPERATIONS = {"DROP", "TRUNCATE", "ALTER", "CREATE", "GRANT", "REVOKE", "EXEC", "EXECUTE"}

def validate_sql_query(query_dict, user_role: str) -> dict:
    # Handle both string (raw_sql) and dict (if wrapped inside query_dict)
    sql = query_dict if isinstance(query_dict, str) else str(query_dict.get("sql", query_dict.get("query_dict", "")))
    sql_upper = sql.upper().strip()

    # 1. Validation Layer (Step 7)
    if "$" in sql or "aggregate" in sql.lower() or "pipeline" in sql.lower():
        return {"is_valid": False, "reason": "MongoDB syntax ($/aggregate/pipeline) is strictly forbidden."}

    # 2. Block forbidden operations
    for op in FORBIDDEN_OPERATIONS:
        if re.search(rf'\b{op}\b', sql_upper):
            return {"is_valid": False, "reason": f"Forbidden SQL operation: {op}"}

    # 3. Role-based access
    op_match = re.match(r'^(\w+)', sql_upper)
    main_op = op_match.group(1) if op_match else ""

    read_ops = {"SELECT", "SHOW", "DESCRIBE"}
    write_ops = {"INSERT", "UPDATE", "DELETE"}
    
    if user_role == "Admin":
        if main_op not in read_ops:
            return {"is_valid": False, "reason": "Admin role is restricted to read operations only."}
    elif user_role == "Staff":
        if main_op not in read_ops | write_ops:
            return {"is_valid": False, "reason": f"Operation '{main_op}' is not allowed."}

        # 4. delete / update must have a non-empty filter
        if main_op in {"DELETE", "UPDATE"}:
            if not re.search(r'\bWHERE\b', sql_upper):
                return {"is_valid": False, "reason": f"{main_op} without WHERE clause is not allowed."}
    else:
        return {"is_valid": False, "reason": f"Unknown role: {user_role}"}

    return {"is_valid": True, "reason": "Valid"}
