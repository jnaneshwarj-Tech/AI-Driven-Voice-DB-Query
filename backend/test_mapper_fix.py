"""
Sprint 1 Bug Fix Verification — Column Mapper & Validation Tests
"""
import sys
sys.path.insert(0, '.')
from ai_column_mapper import map_columns, validate_mapped_rows

print("=" * 65)
print("TEST SUITE: AI COLUMN MAPPER + PRE-INSERT VALIDATION")
print("=" * 65)

# ─── Mapping tests ────────────────────────────────────────────────
test_cols = [
    'name', 'Name', 'student_name', 'student name', 'studentName',
    'full_name', 'full name', 'student_full_name',
    'USN', 'usn', 'student_usn', 'student usn', 'student_id',
    'branch', 'branch_name', 'branch name',
    'semester', 'sem', 'current_semester', 'current semester',
    'SGPA', 'sgpa', 'sgpa_sem1', 'sgpa_sem3',
    '1st_sem_sgpa', '1st semester SGPA',
    'admission_year', 'email_id', 'father', 'mother',
]

mapping = map_columns(test_cols)

checks = [
    ('student_usn',       'usn',             'student_usn  -> usn'),
    ('student usn',       'usn',             'student usn  -> usn'),
    ('branch_name',       'branch',          'branch_name  -> branch  (NOT name)'),
    ('branch name',       'branch',          'branch name  -> branch  (NOT name)'),
    ('sgpa_sem1',         'sem_1_sgpa',      'sgpa_sem1    -> sem_1_sgpa  (NOT semester)'),
    ('sgpa_sem3',         'sem_3_sgpa',      'sgpa_sem3    -> sem_3_sgpa  (NOT semester)'),
    ('1st_sem_sgpa',      'sem_1_sgpa',      '1st_sem_sgpa -> sem_1_sgpa'),
    ('1st semester SGPA', 'sem_1_sgpa',      '1st sem SGPA -> sem_1_sgpa'),
    ('student_name',      'name',            'student_name -> name'),
    ('full_name',         'name',            'full_name    -> name'),
    ('student_full_name', 'name',            'student_full_name -> name'),
    ('email_id',          'email',           'email_id     -> email'),
    ('admission_year',    'year_of_joining', 'admission_year -> year_of_joining'),
    ('father',            'father_name',     'father       -> father_name'),
    ('mother',            'mother_name',     'mother       -> mother_name'),
    ('sem',               'semester',        'sem          -> semester'),
    ('USN',               'usn',             'USN          -> usn'),
    ('student_id',        'usn',             'student_id   -> usn'),
    ('name',              'name',            'name         -> name'),
    ('branch',            'branch',          'branch       -> branch'),
]

print("\n[1] COLUMN MAPPING CHECKS")
all_pass = True
for raw, expected, desc in checks:
    got = mapping.get(raw, '???')
    ok = (got == expected)
    if not ok:
        all_pass = False
    print("  [{}] {}".format("PASS" if ok else "FAIL", desc) +
          ("" if ok else "  GOT: " + repr(got)))

# ─── Validation tests ─────────────────────────────────────────────
print("\n[2] VALIDATE_MAPPED_ROWS CHECKS")

# T1: All valid
t1 = [
    {'usn': '4HG22CS001', 'name': 'Alice', 'semester': 3, 'sgpa': 8.5},
    {'usn': '4HG22CS002', 'name': 'Bob',   'semester': 3, 'sgpa': 7.2},
]
r = validate_mapped_rows(t1)
ok = len(r['valid']) == 2 and len(r['invalid']) == 0
print("  [{}] T1 All valid: valid={}, invalid={}".format(
    "PASS" if ok else "FAIL", len(r['valid']), len(r['invalid'])))
if not ok: all_pass = False

# T2: Missing name
t2 = [{'usn': '4HG22CS001', 'semester': 3, 'sgpa': 8.5}]
r = validate_mapped_rows(t2)
ok = len(r['invalid']) == 1 and len(r['valid']) == 0
print("  [{}] T2 Missing name caught: invalid={}".format("PASS" if ok else "FAIL", len(r['invalid'])))
if r['errors']:
    print("       Error msg:", r['errors'][0][:90])
if not ok: all_pass = False

# T3: Missing USN
t3 = [{'name': 'Alice', 'semester': 3, 'sgpa': 8.5}]
r = validate_mapped_rows(t3)
ok = len(r['invalid']) == 1 and len(r['valid']) == 0
print("  [{}] T3 Missing USN caught: invalid={}".format("PASS" if ok else "FAIL", len(r['invalid'])))
if not ok: all_pass = False

# T4: Both missing
t4 = [{'semester': 3, 'sgpa': 8.5}]
r = validate_mapped_rows(t4)
ok = len(r['invalid']) == 1
print("  [{}] T4 Both missing caught: invalid={}".format("PASS" if ok else "FAIL", len(r['invalid'])))
if not ok: all_pass = False

# T5: Mixed valid + invalid
t5 = [
    {'usn': '4HG22CS001', 'name': 'Alice', 'semester': 3, 'sgpa': 8.5},  # valid
    {'usn': '4HG22CS002',                  'semester': 3, 'sgpa': 7.2},  # no name
    {                       'name': 'Eve',  'semester': 2, 'sgpa': 9.0},  # no usn
]
r = validate_mapped_rows(t5)
ok = len(r['valid']) == 1 and len(r['invalid']) == 2
print("  [{}] T5 Mixed: valid={}, invalid={}".format("PASS" if ok else "FAIL",
      len(r['valid']), len(r['invalid'])))
if not ok: all_pass = False

# ─── Alternate record test (from sprint spec) ─────────────────────
print("\n[3] ALTERNATE COLUMN NAMES TEST (Sprint spec record)")
alt_cols = ['student_name', 'student_usn', 'sem', 'branch_name',
            'admission_year', 'sgpa_sem3', 'email_id', 'father', 'mother']
alt_mapping = map_columns(alt_cols)
alt_checks = [
    ('student_name',  'name',             'student_name  -> name'),
    ('student_usn',   'usn',              'student_usn   -> usn'),
    ('sem',           'semester',         'sem           -> semester'),
    ('branch_name',   'branch',           'branch_name   -> branch'),
    ('admission_year','year_of_joining',  'admission_year -> year_of_joining'),
    ('sgpa_sem3',     'sem_3_sgpa',       'sgpa_sem3     -> sem_3_sgpa'),
    ('email_id',      'email',            'email_id      -> email'),
    ('father',        'father_name',      'father        -> father_name'),
    ('mother',        'mother_name',      'mother        -> mother_name'),
]
for raw, expected, desc in alt_checks:
    got = alt_mapping.get(raw, '???')
    ok = (got == expected)
    if not ok: all_pass = False
    print("  [{}] {}{}".format("PASS" if ok else "FAIL", desc,
          "" if ok else "  GOT: " + repr(got)))

print("\n" + "=" * 65)
print("RESULT:", "ALL TESTS PASSED" if all_pass else "SOME TESTS FAILED")
print("=" * 65)
