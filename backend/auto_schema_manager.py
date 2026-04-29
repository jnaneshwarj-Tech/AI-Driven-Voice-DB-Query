"""
auto_schema_manager.py
Provides live schema context from students + marks tables for the LLM.
Column mapping is now handled directly in routes_files.py via alias sets.
"""
from database import get_db_connection


def build_schema_context() -> str:
    """Return a description of the live students + marks schema."""
    conn = get_db_connection()
    cursor = conn.cursor()
    context_lines = []

    for table in ("students", "marks"):
        try:
            cursor.execute(f"SHOW COLUMNS FROM {table}")
            cols = [row[0] for row in cursor.fetchall()]
            context_lines.append(f"\nTable: {table}")
            context_lines.extend([f"  - {c}" for c in cols])
        except Exception:
            context_lines.append(f"\nTable: {table} (not yet created)")

    cursor.close()
    conn.close()
    return "\n".join(context_lines)
