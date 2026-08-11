"""Remove the known dummy student with a rollback snapshot."""
from database import db_conn
from routes_undo import create_undo_snapshot, finalize_undo_snapshot

USN = "1DS20CS001"

with db_conn() as conn:
    conn.autocommit = False
    conn.start_transaction()
    cur = conn.cursor()
    try:
        token = create_undo_snapshot(
            "DELETE", [USN], "system:remove-dummy", "Removed dummy student", conn=conn
        )
        cur.execute("DELETE FROM marks WHERE usn=%s", (USN,))
        cur.execute("DELETE FROM students WHERE usn=%s", (USN,))
        finalize_undo_snapshot(token, [USN], conn)
        cur.execute(
            "INSERT INTO audit_log (username, role, action, target_table, target_id, summary, success) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            ("system:remove-dummy", "Staff", "DELETED", "students", USN, "Removed dummy student", 1),
        )
        conn.commit()
        print(f"Dummy data deleted. Undo token: {token}")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
