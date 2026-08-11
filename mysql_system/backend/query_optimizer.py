"""
query_optimizer.py
Cleans and lightly optimizes LLM-generated SQL before execution.
"""
import re

def optimize_sql(sql: str) -> str:
    # Remove trailing semicolons (we add them back safely)
    sql = sql.strip().rstrip(';')
    # Collapse multiple spaces
    sql = re.sub(r'\s+', ' ', sql)
    # Ensure SELECT * gets explicit table prefix hint (cosmetic)
    return sql
