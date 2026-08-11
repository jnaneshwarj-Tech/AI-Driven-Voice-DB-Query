from db import get_connection

def get_full_schema():
    """Return all table schemas from schema_metadata."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT table_name, column_name, data_type FROM schema_metadata ORDER BY table_name, column_name")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    schema = {}
    for row in rows:
        t = row["table_name"]
        if t not in schema:
            schema[t] = []
        schema[t].append({"column": row["column_name"], "type": row["data_type"]})
    return schema

def register_column(table_name: str, column_name: str, data_type: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO schema_metadata (table_name, column_name, data_type)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE data_type = VALUES(data_type)
    """, (table_name, column_name, data_type))
    conn.commit()
    cursor.close()
    conn.close()

def get_schema_prompt():
    """Build a text description of the schema for the AI prompt."""
    schema = get_full_schema()
    lines = ["Available MySQL tables and columns:"]
    for table, cols in schema.items():
        col_str = ", ".join(f"{c['column']} ({c['type']})" for c in cols)
        lines.append(f"  Table `{table}`: {col_str}")
    return "\n".join(lines)
