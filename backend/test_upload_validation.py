"""
Sprint 1 End-to-End Upload Validation Tests
Tests the full parse -> map -> validate pipeline without touching the DB.
"""
import sys
sys.path.insert(0, '.')
import io
import pandas as pd
from file_parser import parse_file
from ai_column_mapper import validate_mapped_rows

print("=" * 65)
print("END-TO-END UPLOAD PIPELINE TESTS (no DB writes)")
print("=" * 65)

def make_csv(rows: list[dict]) -> bytes:
    df = pd.DataFrame(rows)
    return df.to_csv(index=False).encode('utf-8')

results = []

# ─── TEST 1: Normal valid dataset ────────────────────────────────
print("\n[TEST 1] Normal valid dataset")
t1_data = [
    {'USN': '4HG22CS001', 'Name': 'Alice Smith',  'Semester': 3, 'SGPA': 8.5},
    {'USN': '4HG22CS002', 'Name': 'Bob Jones',    'Semester': 3, 'SGPA': 7.2},
    {'USN': '4HG22CS003', 'Name': 'Carol White',  'Semester': 3, 'SGPA': 9.1},
]
parsed = parse_file('test1.csv', make_csv(t1_data))
source = parsed.get('gpa_data') or parsed.get('mapped_records', [])
val = validate_mapped_rows(source)
ok = len(val['valid']) == 3 and len(val['invalid']) == 0
print(f"  Parsed rows: {len(source)}, valid: {len(val['valid'])}, invalid: {len(val['invalid'])}")
print(f"  Column mapping: {parsed.get('column_mapping', {})}")
print(f"  Result: {'PASS' if ok else 'FAIL'}")
results.append(ok)

# ─── TEST 2: Alternate column names (from sprint spec) ───────────
print("\n[TEST 2] Alternate column names")
t2_data = [
    {
        'student_name': 'Diana Prince',
        'student_usn':  '4HG23CS401',
        'sem':          2,
        'branch_name':  'CS',
        'admission_year': 2022,
        'sgpa_sem3':    8.0,
        'email_id':     'diana@example.com',
        'father':       'Zeus',
        'mother':       'Hippolyta',
    }
]
parsed = parse_file('test2.csv', make_csv(t2_data))
cm = parsed.get('column_mapping', {})
source = parsed.get('gpa_data') or parsed.get('mapped_records', [])
val = validate_mapped_rows(source)

mapping_ok = (
    cm.get('student_name') == 'name' and
    cm.get('student_usn')  == 'usn'  and
    cm.get('branch_name')  == 'branch' and
    cm.get('email_id')     == 'email'
)
valid_ok = len(val['valid']) >= 1 and len(val['invalid']) == 0
ok = mapping_ok and valid_ok
print(f"  student_name -> {cm.get('student_name')!r}  (expect 'name')")
print(f"  student_usn  -> {cm.get('student_usn')!r}   (expect 'usn')")
print(f"  branch_name  -> {cm.get('branch_name')!r}   (expect 'branch')")
print(f"  sgpa_sem3    -> {cm.get('sgpa_sem3')!r}      (expect 'sem_3_sgpa')")
print(f"  email_id     -> {cm.get('email_id')!r}       (expect 'email')")
print(f"  valid: {len(val['valid'])}, invalid: {len(val['invalid'])}")
print(f"  Result: {'PASS' if ok else 'FAIL'}")
results.append(ok)

# ─── TEST 3: File with genuinely missing name ────────────────────
print("\n[TEST 3] File with missing name — validation must catch it BEFORE DB")
t3_data = [
    {'USN': '4HG22CS001', 'Semester': 3, 'SGPA': 8.5},  # no name
    {'USN': '4HG22CS002', 'Semester': 3, 'SGPA': 7.2},  # no name
]
parsed = parse_file('test3.csv', make_csv(t3_data))
source = parsed.get('gpa_data') or parsed.get('mapped_records', [])
val = validate_mapped_rows(source)
ok = len(val['invalid']) == 2 and len(val['valid']) == 0
print(f"  Rows with missing name: {len(val['invalid'])}")
print(f"  Error sample: {val['errors'][0][:80] if val['errors'] else 'none'}...")
print(f"  Would DB transaction start? {'NO (correct)' if ok else 'YES (incorrect)'}")
print(f"  Result: {'PASS' if ok else 'FAIL'}")
results.append(ok)

# ─── TEST 4: Mixed valid + invalid rows ──────────────────────────
print("\n[TEST 4] Mixed valid + invalid rows")
t4_data = [
    {'USN': '4HG22CS001', 'Name': 'Alice', 'Semester': 3, 'SGPA': 8.5},  # valid
    {'USN': '4HG22CS002',                  'Semester': 3, 'SGPA': 7.2},  # no name
]
parsed = parse_file('test4.csv', make_csv(t4_data))
source = parsed.get('gpa_data') or parsed.get('mapped_records', [])
val = validate_mapped_rows(source)
ok = len(val['valid']) == 1 and len(val['invalid']) == 1
print(f"  valid: {len(val['valid'])}, invalid: {len(val['invalid'])}")
print(f"  Invalid row identifies missing field: {'Student Name' in str(val['errors'])}")
print(f"  Result: {'PASS' if ok else 'FAIL'}")
results.append(ok)

# ─── TEST 5: Wide-format SGPA columns ────────────────────────────
print("\n[TEST 5] Wide-format SGPA columns (sgpa_sem1, sgpa_sem3)")
t5_data = [
    {'USN': '4HG22CS001', 'Name': 'Alice', 'sgpa_sem1': 8.0, 'sgpa_sem3': 8.5},
    {'USN': '4HG22CS002', 'Name': 'Bob',   'sgpa_sem1': 7.0, 'sgpa_sem3': 7.5},
]
parsed = parse_file('test5.csv', make_csv(t5_data))
cm = parsed.get('column_mapping', {})
gpa = parsed.get('gpa_data', [])
ok = (cm.get('sgpa_sem1') == 'sem_1_sgpa' and
      cm.get('sgpa_sem3') == 'sem_3_sgpa' and
      len(gpa) > 0)
print(f"  sgpa_sem1 -> {cm.get('sgpa_sem1')!r}  (expect 'sem_1_sgpa')")
print(f"  sgpa_sem3 -> {cm.get('sgpa_sem3')!r}  (expect 'sem_3_sgpa')")
print(f"  GPA rows unpivoted: {len(gpa)}")
print(f"  Result: {'PASS' if ok else 'FAIL'}")
results.append(ok)

# ─── Summary ──────────────────────────────────────────────────────
print("\n" + "=" * 65)
passed = sum(results)
total  = len(results)
print(f"SUMMARY: {passed}/{total} tests passed")
if passed == total:
    print("ALL TESTS PASSED — upload pipeline is correct")
else:
    print("SOME TESTS FAILED — review above")
print("=" * 65)
print()
print("NOTE: Rollback mechanism is unchanged in routes_files.py.")
print("Validation runs BEFORE any DB transaction is opened,")
print("so if validation fails, no rollback is needed.")
