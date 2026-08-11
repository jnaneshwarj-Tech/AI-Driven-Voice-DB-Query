import sys
sys.path.insert(0, '.')
from db import get_connection
from models import MAIN_TABLE

conn = get_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute(f"SHOW TABLES LIKE '{MAIN_TABLE}'")
result = cursor.fetchone()
print("Table exists:", result)

if result:
    cursor.execute(f"SHOW COLUMNS FROM `{MAIN_TABLE}`")
    cols = cursor.fetchall()
    print("Columns:", [c['Field'] for c in cols])

cursor.close()
conn.close()
