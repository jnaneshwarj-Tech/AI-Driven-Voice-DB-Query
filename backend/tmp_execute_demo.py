import os, sys, json
sys.path.insert(0, os.getcwd())
from routes_query import _build_update_request, execute_confirmed, ExecuteRequest
from database import db_conn

req = _build_update_request('update 4HG23CS032 blood group to o+')
print('BUILD REQ:', json.dumps(req, indent=2))
exec_req = ExecuteRequest(query_dict=req, original_query='update 4HG23CS032 blood group to o+')
user = {'username': 'admin', 'role': 'Staff'}
res = execute_confirmed(exec_req, current_user=user)
print('EXECUTE RESP:', json.dumps(res, indent=2, default=str))
with db_conn() as conn:
    cur = conn.cursor(dictionary=True)
    cur.execute('SELECT blood_group FROM students WHERE usn=%s', ('4HG23CS032',))
    print('AFTER DB:', cur.fetchone())
    cur.close()
