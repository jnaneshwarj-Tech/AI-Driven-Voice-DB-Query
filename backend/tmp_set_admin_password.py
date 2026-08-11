import os, sys
sys.path.insert(0, os.getcwd())
from auth import get_password_hash
from database import db_conn

pw = get_password_hash('Admin@123')
with db_conn() as conn:
    cur = conn.cursor()
    cur.execute("UPDATE users SET password_hash=%s WHERE username=%s", (pw, 'admin'))
    conn.commit()
    cur.close()
print('admin password reset to Admin@123')
