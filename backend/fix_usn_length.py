from database import db_conn

queries = [
    "ALTER TABLE students MODIFY COLUMN usn VARCHAR(100);",
    "ALTER TABLE marks MODIFY COLUMN usn VARCHAR(100);",
    "ALTER TABLE students_personal MODIFY COLUMN usn VARCHAR(100);",
    "UPDATE schema_metadata SET data_type='VARCHAR(100)' WHERE column_name='usn';"
]

try:
    with db_conn() as conn:
        cur = conn.cursor()
        for q in queries:
            try:
                cur.execute(q)
                print(f"Success: {q}")
            except Exception as e:
                print(f"Skipped/Failed: {q} -> {e}")
        conn.commit()
        print("Database schema successfully updated!")
except Exception as e:
    print(f"Connection failed: {e}")
