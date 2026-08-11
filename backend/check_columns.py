from database import db_conn

try:
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SHOW COLUMNS FROM students")
        cols = cur.fetchall()
        print("=== CURRENT students TABLE COLUMNS ===")
        for c in cols:
            print(c)
        cur.close()
except Exception as e:
    print(f"Error: {e}")
