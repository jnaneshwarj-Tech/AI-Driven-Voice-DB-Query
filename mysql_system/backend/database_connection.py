"""
database_connection.py
MySQL connection pool using mysql-connector-python.
"""
import mysql.connector
from mysql.connector import pooling
from config import settings

_pool = None

def get_pool():
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name="college_pool",
            pool_size=5,
            host=settings.MYSQL_HOST,
            port=settings.MYSQL_PORT,
            user=settings.MYSQL_USER,
            password=settings.MYSQL_PASSWORD,
            database=settings.MYSQL_DB,
            autocommit=True,
        )
    return _pool

def get_connection():
    return get_pool().get_connection()

def execute_query(sql: str, params: tuple = None) -> list[dict]:
    """Execute a SELECT query and return list of dicts."""
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, params or ())
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

def execute_write(sql: str, params: tuple = None) -> int:
    """Execute INSERT/UPDATE/DELETE and return affected rows."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params or ())
        conn.commit()
        return cursor.rowcount
    finally:
        cursor.close()
        conn.close()

def execute_many(sql: str, data: list[tuple]) -> int:
    """Bulk insert."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.executemany(sql, data)
        conn.commit()
        return cursor.rowcount
    finally:
        cursor.close()
        conn.close()

def init_db():
    """Create tables if they don't exist (reads schema.sql)."""
    import os
    schema_path = os.path.join(os.path.dirname(__file__), '..', 'database', 'schema.sql')
    if not os.path.exists(schema_path):
        print("[DB] schema.sql not found, skipping init.")
        return
    conn = mysql.connector.connect(
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
    )
    cursor = conn.cursor()
    with open(schema_path, 'r') as f:
        statements = [s.strip() for s in f.read().split(';') if s.strip()]
    for stmt in statements:
        try:
            cursor.execute(stmt)
        except Exception as e:
            print(f"[DB] Schema stmt warning: {e}")
    conn.commit()
    cursor.close()
    conn.close()
    print("[DB] Schema initialized.")
