import os, sys, json
import requests
sys.path.insert(0, os.getcwd())
from database import db_conn

url = 'http://127.0.0.1:8000/api/query/generate'
payload = {'natural_query': 'update 4HG23CS032 blood group to o+'}
resp = requests.post(url, json=payload)
print('GENERATE STATUS', resp.status_code)
print('GENERATE BODY', resp.text)
if resp.status_code != 200:
    raise SystemExit(1)
body = resp.json()
if body.get('action_required') != 'confirm':
    print('Not confirm stage, no executable query.'); raise SystemExit(1)
exec_url = 'http://127.0.0.1:8000/api/query/execute'
resp2 = requests.post(exec_url, json={'query_dict': body['query_dict'], 'original_query': 'update 4HG23CS032 blood group to o+'})
print('EXECUTE STATUS', resp2.status_code)
print('EXECUTE BODY', resp2.text)
with db_conn() as conn:
    cur = conn.cursor(dictionary=True)
    cur.execute('SELECT blood_group FROM students WHERE usn=%s', ('4HG23CS032',))
    print('DB AFTER', cur.fetchone())
    cur.close()
