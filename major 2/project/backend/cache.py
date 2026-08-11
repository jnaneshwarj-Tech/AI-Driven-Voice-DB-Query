import hashlib
import json
from db import get_connection

def _hash(query: str) -> str:
    return hashlib.sha256(query.strip().lower().encode()).hexdigest()

def get_cached(user_query: str):
    h = _hash(user_query)
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT sql_query, result_json FROM query_cache WHERE query_hash = %s", (h,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if row:
        return row["sql_query"], json.loads(row["result_json"])
    return None, None

def store_cache(user_query: str, sql_query: str, result: list):
    h = _hash(user_query)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO query_cache (user_query, query_hash, sql_query, result_json)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE sql_query = VALUES(sql_query), result_json = VALUES(result_json), created_at = CURRENT_TIMESTAMP
    """, (user_query.strip(), h, sql_query, json.dumps(result, default=str)))
    conn.commit()
    cursor.close()
    conn.close()

def clear_cache():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM query_cache")
    conn.commit()
    cursor.close()
    conn.close()
    print("[Cache] Cleared.")
