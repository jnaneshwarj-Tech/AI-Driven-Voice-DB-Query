import os, sys
sys.path.insert(0, os.getcwd())
from database import db_conn
from auth import verify_password
with db_conn() as conn:
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT username, password_hash FROM users WHERE username IN ('admin','staff')")
    rows = cur.fetchall()
    cur.close()
print(rows)
for row in rows:
    print(row['username'], 'admin password', verify_password('Admin@123', row['password_hash']))
    print(row['username'], 'staff password', verify_password('Staff@123', row['password_hash']))
