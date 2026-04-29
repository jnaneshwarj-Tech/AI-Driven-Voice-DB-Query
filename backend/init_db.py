"""
init_db.py — Seeds default users into MySQL.
Run once: python init_db.py
"""
from database import get_db_connection, create_indexes
from auth import get_password_hash

def init():
    create_indexes()
    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        for username, email, password, role in [
            ("admin",  "admin@college.edu",  "admin123",  "Admin"),
            ("staff",  "staff@college.edu",  "staff123",  "Staff"),
        ]:
            cur.execute("SELECT id FROM users WHERE username=%s", (username,))
            if cur.fetchone():
                print(f"  User '{username}' already exists")
            else:
                cur.execute(
                    "INSERT INTO users (username, email, password_hash, role) VALUES (%s,%s,%s,%s)",
                    (username, email, get_password_hash(password), role)
                )
                print(f"✓ Created user: {username} / {password} ({role})")
        conn.commit()
    finally:
        cur.close()
        conn.close()
    print("\n✅ MySQL init complete.")
    print("   Login: admin/admin123 (Admin) | staff/staff123 (Staff)")

if __name__ == "__main__":
    init()
