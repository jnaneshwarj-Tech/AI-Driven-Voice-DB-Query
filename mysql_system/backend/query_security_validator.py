"""
query_security_validator.py
Blocks dangerous SQL operations before execution.
"""
import re

BLOCKED_PATTERNS = [
    r'\bDROP\b', r'\bTRUNCATE\b', r'\bALTER\b',
    r'\bCREATE\b', r'\bGRANT\b', r'\bREVOKE\b',
    r'--', r'/\*', r'\bEXEC\b', r'\bEXECUTE\b',
    r'\bxp_\w+', r'\bINTO\s+OUTFILE\b', r'\bLOAD\s+DATA\b',
]

def validate_sql(sql: str, user_role: str) -> dict:
    upper = sql.upper().strip()

    # Block dangerous patterns for everyone
    for pat in BLOCKED_PATTERNS:
        if re.search(pat, upper, re.IGNORECASE):
            return {"is_valid": False, "reason": f"Blocked pattern detected: {pat}"}

    # Admin can only SELECT
    if user_role == "Admin":
        if not upper.startswith("SELECT"):
            return {"is_valid": False, "reason": "Admin role: only SELECT queries allowed."}

    # DELETE without WHERE
    if re.search(r'\bDELETE\b', upper) and not re.search(r'\bWHERE\b', upper):
        return {"is_valid": False, "reason": "DELETE without WHERE clause is not allowed."}

    # UPDATE without WHERE
    if re.search(r'\bUPDATE\b', upper) and not re.search(r'\bWHERE\b', upper):
        return {"is_valid": False, "reason": "UPDATE without WHERE clause is not allowed."}

    return {"is_valid": True, "reason": ""}
