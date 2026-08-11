import os, sys
sys.path.insert(0, os.getcwd())
from database import db_conn
with db_conn() as conn:
    cur = conn.cursor(dictionary=True)
    cur.execute('SELECT username, role, email FROM users LIMIT 20')
    users = cur.fetchall()
    cur.close()
print(users)
