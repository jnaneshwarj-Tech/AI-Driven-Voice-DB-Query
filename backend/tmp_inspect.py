import os, sys, json
sys.path.insert(0, os.getcwd())
from database import db_conn
from config import settings
print('DB:', settings.MYSQL_DB)
with db_conn() as conn:
    cur = conn.cursor(dictionary=True)
    for table in ['students', 'marks']:
        print('TABLE', table)
        cur.execute(f'SHOW COLUMNS FROM `{table}`')
        print(json.dumps([{'Field': row['Field'], 'Type': row['Type'], 'Null': row['Null'], 'Key': row.get('Key', ''), 'Extra': row.get('Extra', '')} for row in cur.fetchall()], indent=2))
        print()
    queries = [
        "SELECT * FROM students WHERE LOWER(usn)=LOWER('4HG23CS032')",
        "SELECT * FROM marks WHERE LOWER(usn)=LOWER('4HG23CS032') ORDER BY semester"
    ]
    for q in queries:
        print('QUERY', q)
        cur.execute(q)
        print(json.dumps(cur.fetchall(), default=str, indent=2))
    cur.close()
