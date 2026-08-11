import sys
sys.path.insert(0, '.')
from db import get_connection
from auth import hash_password

conn = get_connection()
cur = conn.cursor()

# Check existing schema
cur.execute("DESCRIBE users")
cols = {r[0]: r for r in cur.fetchall()}
print("Existing cols:", list(cols.keys()))

# Rename old table if it has wrong schema
if "password" not in cols:
    cur.execute("RENAME TABLE users TO users_old_backup")
    conn.commit()
    print("Renamed old users table -> users_old_backup")
    cur.execute("""
        CREATE TABLE users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL UNIQUE,
            password VARCHAR(255) NOT NULL,
            role ENUM('admin','staff') DEFAULT 'staff',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    print("Created fresh users table")

# Seed demo accounts
hashed_admin = hash_password("admin123")
hashed_staff = hash_password("staff123")

cur.execute("""
    INSERT INTO users (name, email, password, role)
    VALUES (%s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE password=VALUES(password), role=VALUES(role), name=VALUES(name)
""", ("Admin User", "admin@sdms.com", hashed_admin, "admin"))

cur.execute("""
    INSERT INTO users (name, email, password, role)
    VALUES (%s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE password=VALUES(password), role=VALUES(role), name=VALUES(name)
""", ("Staff User", "staff@sdms.com", hashed_staff, "staff"))

conn.commit()
cur.close()
conn.close()
print("\nDemo accounts ready:")
print("  ADMIN -> admin@sdms.com  / admin123  (view-only)")
print("  STAFF -> staff@sdms.com  / staff123  (full access)")
