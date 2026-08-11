import requests

base = 'http://127.0.0.1:8000'
login = requests.post(base + '/api/auth/login', json={'username': 'admin', 'password': 'admin'})
print('LOGIN STATUS', login.status_code)
print('LOGIN BODY', login.text)
if login.status_code != 200:
    raise SystemExit(1)
token = login.json()['access_token']
headers = {'Authorization': f'Bearer {token}'}

gen = requests.post(base + '/api/query/generate', json={'natural_query': 'update 4HG23CS032 blood group to o+'}, headers=headers)
print('GENERATE', gen.status_code, gen.text)
if gen.status_code != 200:
    raise SystemExit(1)
if gen.json().get('action_required') != 'confirm':
    print('NOT CONFIRM', gen.json()); raise SystemExit(1)
exec_res = requests.post(base + '/api/query/execute', json={'query_dict': gen.json()['query_dict'], 'original_query': 'update 4HG23CS032 blood group to o+'}, headers=headers)
print('EXECUTE', exec_res.status_code, exec_res.text)
