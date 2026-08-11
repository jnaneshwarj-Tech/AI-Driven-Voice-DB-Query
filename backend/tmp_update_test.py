import os, sys, json
sys.path.insert(0, os.getcwd())
from routes_query import _build_update_request
queries = [
    'update 4HG23CS032 sgpa to 8.9',
    'update 4HG23CS032 cgpa to 8.12',
    'update 4HG23CS032 emergency contact number to 9876543210',
    'update MANOJ J R blood group to o+',
    'update 4HG23CS032 sem 5 sgpa to 8.5',
    'update 4HG23CS032 sem 7 cgpa to 8.7',
    'update 4HG23CS032 sem 5 cgpa to 7.8'
]
for q in queries:
    print('---')
    print('QUERY:', q)
    try:
        req = _build_update_request(q)
        print(json.dumps(req, indent=2, default=str))
    except Exception as e:
        print('ERROR:', type(e).__name__, e)
