import os
import re
import json
from schema_memory import get_schema_prompt
from cache import get_cached, store_cache
from db import get_connection

# Lazy-init client — supports both OpenAI (sk-...) and NVIDIA (nvapi-...) keys
_client = None

def get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set. Add it to start_backend.bat and restart.")
        if api_key.startswith("nvapi-"):
            # NVIDIA NIM — OpenAI-compatible endpoint
            _client = OpenAI(
                api_key=api_key,
                base_url="https://integrate.api.nvidia.com/v1",
            )
        else:
            _client = OpenAI(api_key=api_key)
    return _client

def get_model() -> str:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key.startswith("nvapi-"):
        return "meta/llama-3.1-8b-instruct"
    return "gpt-3.5-turbo"

CHART_KEYWORDS = ["top", "trend", "compare", "distribution", "average", "rank", "best", "worst", "lowest", "highest"]
CHART_TYPE_MAP = {
    "top": "bar", "best": "bar", "rank": "bar", "highest": "bar",
    "trend": "line", "over time": "line", "semester": "line",
    "distribution": "pie", "compare": "bar", "worst": "bar", "lowest": "bar",
    "average": "bar",
}

def detect_chart_type(query: str) -> str | None:
    q = query.lower()
    for kw, ctype in CHART_TYPE_MAP.items():
        if kw in q:
            return ctype
    return None

def nl_to_sql(user_query: str) -> str:
    schema_info = get_schema_prompt()
    system_prompt = f"""You are a MySQL SQL generator. Convert natural language to valid MySQL SELECT queries.
RULES:
- Output ONLY the SQL query, no explanation, no markdown, no backticks.
- Use only MySQL syntax. NEVER use MongoDB or NoSQL syntax.
- Use JOIN when data spans multiple tables.
- Always use table aliases for clarity.
- Use LIMIT 500 unless user specifies otherwise.
- For CGPA/SGPA queries, check both students_dynamic and semester_data tables.
- Column names use snake_case.

{schema_info}

Examples:
User: show all students -> SELECT * FROM students_dynamic LIMIT 500;
User: show cgpa of Sudeep -> SELECT name, cgpa FROM students_dynamic WHERE name LIKE '%Sudeep%';
User: top 10 students by cgpa -> SELECT name, usn, cgpa FROM students_dynamic ORDER BY cgpa DESC LIMIT 10;
User: graduated students -> SELECT * FROM students_dynamic WHERE status = 'GRADUATED';
User: semester wise sgpa of 1RV20CS001 -> SELECT semester, sgpa, cgpa FROM semester_data WHERE usn = '1RV20CS001' ORDER BY semester;
"""
    response = get_client().chat.completions.create(
        model=get_model(),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query},
        ],
        temperature=0,
        max_tokens=300,
    )
    sql = response.choices[0].message.content.strip()
    # Strip markdown if present
    sql = re.sub(r"```sql|```", "", sql).strip()
    return sql

def execute_sql(sql: str) -> list:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(sql)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def run_ai_query(user_query: str, role: str = "staff") -> dict:
    # Check cache first
    cached_sql, cached_result = get_cached(user_query)
    if cached_result is not None:
        chart_type = detect_chart_type(user_query)
        return {
            "sql": cached_sql,
            "data": cached_result,
            "from_cache": True,
            "chart_type": chart_type,
            "chart_data": build_chart_data(cached_result, chart_type),
        }

    sql = nl_to_sql(user_query)

    # Strip markdown if present
    sql = re.sub(r"```sql|```", "", sql).strip()

    # Role enforcement on generated SQL
    destructive = ["INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER"]
    sql_upper = sql.upper()
    if any(kw in sql_upper for kw in destructive):
        if role == "admin":
            raise ValueError("Admins are not allowed to modify data.")
        # Staff: only SELECT allowed from AI (destructive must go through confirm flow)
        raise ValueError("Only SELECT queries are allowed from AI engine.")

    if not sql.strip().upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed.")

    data = execute_sql(sql)
    store_cache(user_query, sql, data)

    chart_type = detect_chart_type(user_query)
    return {
        "sql": sql,
        "data": data,
        "from_cache": False,
        "chart_type": chart_type,
        "chart_data": build_chart_data(data, chart_type),
    }

def build_chart_data(data: list, chart_type: str | None) -> dict | None:
    if not chart_type or not data:
        return None

    # Try to find a label column and a numeric column
    if not data:
        return None

    keys = list(data[0].keys())
    label_col = None
    value_col = None

    for k in keys:
        if k in ("name", "usn", "branch", "department", "semester", "status", "section"):
            label_col = k
            break
    if not label_col:
        label_col = keys[0]

    for k in keys:
        if k in ("cgpa", "sgpa", "marks", "percentage", "attendance", "count", "cnt", "avg_cgpa"):
            value_col = k
            break
    if not value_col:
        for k in keys:
            if k != label_col:
                try:
                    float(str(data[0][k]))
                    value_col = k
                    break
                except (ValueError, TypeError):
                    pass

    if not value_col:
        return None

    labels = [str(row.get(label_col, "")) for row in data]
    values = []
    for row in data:
        try:
            values.append(float(str(row.get(value_col, 0) or 0)))
        except (ValueError, TypeError):
            values.append(0)

    return {
        "type": chart_type,
        "labels": labels,
        "values": values,
        "label_col": label_col,
        "value_col": value_col,
    }
