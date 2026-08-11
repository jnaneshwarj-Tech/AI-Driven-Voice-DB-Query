import os, sys, json
sys.path.insert(0, os.getcwd())
from routes_query import _parse_update_assignments, _build_update_request
queries = [
    'update 4HG23CS032 3rd sem sgpa to 8.5',
    'update 4HG23CS032 3rd semester sgpa to 8.5',
    'update 4HG23CS032 3rd sem cgpa to 8.5',
    'update 4HG23CS032 sem 3 sgpa to 8.5',
    'update 4HG23CS032 sem 3 cgpa to 8.5',
    'update 4HG23CS032 sgpa to 8.5',
]
for q in queries:
    print('---')
    print('QUERY:', q)
    try:
        parsed = _parse_update_assignments(q)
        print('PARSED:', json.dumps(parsed, indent=2))
        req = _build_update_request(q)
        print('REQ:', json.dumps(req, indent=2))
    except Exception as e:
        print('ERROR:', type(e).__name__, e)
