import os, sys, json
sys.path.insert(0, os.getcwd())
from routes_query import _extract_target_and_field, _parse_update_assignments
cases = [
    '4HG23CS032 sgpa',
    '4HG23CS032 cgpa',
    '4HG23CS032 emergency contact number',
    '4HG23CS032 sem 5 sgpa',
    '4HG23CS032 sem 7 cgpa',
    'MANOJ J R blood group',
]
for case in cases:
    try:
        target, field = _extract_target_and_field(case)
        print('CASE:', case)
        print('  target=', repr(target))
        print('  field=', repr(field))
    except Exception as e:
        print('CASE:', case, 'ERROR', type(e).__name__, e)
print('--- parse examples ---')
for q in [
    'update 4HG23CS032 emergency contact number to 9876543210',
    'update 4HG23CS032 sem 5 sgpa to 8.5',
    'update 4HG23CS032 sem 7 cgpa to 8.7',
    'update 4HG23CS032 sgpa to 8.9',
]:
    try:
        parsed = _parse_update_assignments(q)
        print('QUERY:', q)
        print(json.dumps(parsed, indent=2))
    except Exception as e:
        print('QUERY:', q, 'ERROR', type(e).__name__, e)
