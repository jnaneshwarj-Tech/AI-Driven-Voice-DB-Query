import sys
sys.path.insert(0, '.')
from db import get_connection
from models import MAIN_TABLE

conn = get_connection()
cursor = conn.cursor(dictionary=True)

try:
    cursor.execute(f"SHOW TABLES LIKE '{MAIN_TABLE}'")
    exists = cursor.fetchone()
    print("Exists:", exists)

    cursor.execute(f"SHOW COLUMNS FROM `{MAIN_TABLE}`")
    valid_cols = [r['Field'] for r in cursor.fetchall()]
    print("Cols count:", len(valid_cols))

    sort_by = "usn"
    cursor.execute(
        f"SELECT * FROM `{MAIN_TABLE}` ORDER BY `{sort_by}` ASC LIMIT 5 OFFSET 0"
    )
    data = cursor.fetchall()
    print("Rows:", len(data))

    cursor.execute(f"SELECT COUNT(*) as cnt FROM `{MAIN_TABLE}`")
    total = cursor.fetchone()["cnt"]
    print("Total:", total)

except Exception as e:
    import traceback
    traceback.print_exc()

cursor.close()
conn.close()
