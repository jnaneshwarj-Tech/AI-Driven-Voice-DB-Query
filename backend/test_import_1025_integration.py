"""
Full integration test for the 1025-row import bug fix + semantic mapping.
Uses MySQL. Only touches USNs matching the test prefix 4HG25CS / 4HGTEST.
"""
import sys
sys.path.insert(0, '.')
import io
import pandas as pd
from database import init_pool, db_conn
from file_parser import parse_file
from canonical_fields import map_columns
from routes_files import (
    _save_upload_cache, update_database, _remove_upload_cache, _file_cache
)

TEST_PREFIX = '4HG25CS'
FILENAME = '_test_1025_import.csv'

def make_1025_csv() -> bytes:
    cols = [
        'Name', 'USN', 'Semester', 'SGPA', 'Branch Name',
        'student_name', 'student_usn', 'sem', 'branch_name',
        'admission_year', 'sgpa_sem3', 'email_id', 'father', 'mother',
    ]
    rows = []
    for i in range(1, 1025):
        # Avoid colliding with alternate USN 4HG25CS999
        usn_num = i if i != 999 else 9980
        rows.append({
            'Name': f'Student {i}',
            'USN': f'{TEST_PREFIX}{usn_num:03d}' if usn_num < 1000 else f'{TEST_PREFIX}{usn_num}',
            'Semester': 3,
            'SGPA': 8.0 + (i % 10) * 0.1,
            'Branch Name': 'CSE',
            'student_name': None, 'student_usn': None, 'sem': None,
            'branch_name': None, 'admission_year': None, 'sgpa_sem3': None,
            'email_id': None, 'father': None, 'mother': None,
        })
    rows.append({
        'Name': None, 'USN': None, 'Semester': None, 'SGPA': None, 'Branch Name': None,
        'student_name': 'Column Mapping Test Student',
        'student_usn': f'{TEST_PREFIX}999',
        'sem': 3,
        'branch_name': 'ISE',
        'admission_year': 2025,
        'sgpa_sem3': 8.5,
        'email_id': 'maptest@example.com',
        'father': 'Test Father',
        'mother': 'Test Mother',
    })
    return pd.DataFrame(rows, columns=cols).to_csv(index=False).encode()


def cleanup_test_data():
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM marks WHERE usn LIKE %s OR usn LIKE %s",
                    (f'{TEST_PREFIX}%', '4HGTEST%'))
        cur.execute("DELETE FROM students WHERE usn LIKE %s OR usn LIKE %s",
                    (f'{TEST_PREFIX}%', '4HGTEST%'))
        cur.execute("DELETE FROM uploaded_files WHERE filename=%s", (FILENAME,))
        conn.commit()
        cur.close()


def count_test():
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT COUNT(*) AS c FROM students WHERE usn LIKE %s", (f'{TEST_PREFIX}%',))
        s = cur.fetchone()['c']
        cur.execute("SELECT COUNT(*) AS c FROM marks WHERE usn LIKE %s", (f'{TEST_PREFIX}%',))
        m = cur.fetchone()['c']
        cur.execute("SELECT usn, name, branch, father_name, mother_name, email FROM students WHERE usn=%s",
                    (f'{TEST_PREFIX}999',))
        alt = cur.fetchone()
        cur.close()
    return s, m, alt


def fake_user():
    return {'username': 'test_staff', 'role': 'Staff'}


def run():
    init_pool()
    print('=' * 70)
    print('INTEGRATION: 1025-row import + semantic mapping + re-upload')
    print('=' * 70)

    # Mapping sanity
    m = map_columns(['Branch Name', 'Father Name', 'Mother Name', 'Division Name', 'Domain Name'])
    assert m['Branch Name'] == 'branch'
    assert m['Father Name'] == 'father_name'
    assert m['Mother Name'] == 'mother_name'
    assert m['Division Name'] == 'division'
    assert m['Domain Name'] == 'domain'
    print('[PASS] Semantic conflict mappings')

    content = make_1025_csv()
    parsed = parse_file(FILENAME, content)
    assert parsed['row_count'] == 1025
    assert len(parsed['mapped_records']) == 1025
    nn = sum(1 for r in parsed['mapped_records'] if r.get('name'))
    assert nn == 1025, f'expected 1025 names, got {nn}'
    print(f'[PASS] Parse: row_count={parsed["row_count"]}, names={nn}, gpa={len(parsed["gpa_data"])}')

    cleanup_test_data()
    _save_upload_cache(FILENAME, content)

    # Patch Depends — call update_database directly with fake user via override
    # FastAPI Depends won't run when calling the function directly if we pass current_user
    result = update_database(FILENAME, current_user=fake_user())

    print('Import result:')
    for k in ('rows_parsed', 'students_added', 'students_updated', 'students_unchanged',
              'duplicate_rows', 'invalid_rows', 'students_saved', 'marks_saved',
              'total_accounted', 'reconciled'):
        print(f'  {k}: {result.get(k)}')

    assert result['rows_parsed'] == 1025
    assert result['reconciled'] is True
    assert result['students_added'] == 1025, f"expected 1025 added, got {result['students_added']}"
    assert result['marks_saved'] >= 1025
    assert result['invalid_rows'] == 0

    s, mcount, alt = count_test()
    print(f'DB verify: students={s}, marks={mcount}')
    print(f'Alt record: {alt}')
    assert s == 1025
    assert mcount >= 1025
    assert alt is not None
    assert alt['name'] == 'Column Mapping Test Student'
    assert alt['branch'] == 'ISE'
    assert alt['father_name'] == 'Test Father'
    assert alt['mother_name'] == 'Test Mother'
    assert alt['email'] == 'maptest@example.com'
    print('[PASS] TEST 1 empty-DB import')

    # TEST 2: re-upload → unchanged / no duplicates
    _save_upload_cache(FILENAME, content)
    result2 = update_database(FILENAME, current_user=fake_user())
    print('Re-import:', {k: result2.get(k) for k in
          ('students_added', 'students_updated', 'students_unchanged', 'students_saved', 'marks_saved')})
    s2, m2, _ = count_test()
    assert s2 == 1025, f'duplicate students created? count={s2}'
    assert result2['students_added'] == 0
    assert result2['students_unchanged'] + result2['students_updated'] == 1025
    print('[PASS] TEST 2 re-upload no duplicates')

    # TEST 5: missing name caught
    bad = pd.DataFrame([
        {'USN': '4HGTEST001', 'Semester': 1, 'SGPA': 8.0},
        {'USN': '4HGTEST002', 'Name': 'Ok', 'Semester': 1, 'SGPA': 8.0},
    ]).to_csv(index=False).encode()
    bad_name = '_test_missing_name.csv'
    _save_upload_cache(bad_name, bad)
    result3 = update_database(bad_name, current_user=fake_user())
    assert result3['invalid_rows'] >= 1
    assert result3['students_added'] >= 1
    print('[PASS] TEST 5/7 mixed valid+invalid (invalid counted, valid saved)')
    _remove_upload_cache(bad_name)

    # TEST 6: invalid SGPA
    bad_sgpa = pd.DataFrame([
        {'USN': '4HGTEST010', 'Name': 'Bad SGPA', 'Semester': 1, 'SGPA': 15.0},
    ]).to_csv(index=False).encode()
    fn = '_test_bad_sgpa.csv'
    _save_upload_cache(fn, bad_sgpa)
    result4 = update_database(fn, current_user=fake_user())
    # Student may still be saved; mark rejected
    assert result4['students_added'] + result4['students_updated'] + result4['students_unchanged'] >= 1
    print(f"[PASS] TEST 6 invalid SGPA handled (marks_rejected={result4.get('marks_rejected')}, marks_saved={result4.get('marks_saved')})")
    _remove_upload_cache(fn)

    # TEST 8: rollback on DB failure
    from routes_files import _upsert_student
    # Force failure mid-transaction by inserting a student then raising via bad SQL path
    # Simulate by calling update with a monkeypatch
    original = None
    import routes_files as rf
    calls = {'n': 0}
    real_upsert = rf._upsert_student

    def boom(cur, usn, row):
        calls['n'] += 1
        if calls['n'] > 3:
            raise RuntimeError('Forced DB failure for rollback test')
        return real_upsert(cur, usn, row)

    rf._upsert_student = boom
    rollback_file = '_test_rollback.csv'
    rb = pd.DataFrame([
        {'USN': f'4HGTEST1{i:02d}', 'Name': f'RB {i}', 'Semester': 1, 'SGPA': 7.0}
        for i in range(10)
    ]).to_csv(index=False).encode()
    # clean first
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM marks WHERE usn LIKE '4HGTEST1%'")
        cur.execute("DELETE FROM students WHERE usn LIKE '4HGTEST1%'")
        conn.commit(); cur.close()
    _save_upload_cache(rollback_file, rb)
    try:
        update_database(rollback_file, current_user=fake_user())
        print('[FAIL] TEST 8 expected HTTPException')
        sys.exit(1)
    except Exception as e:
        detail = getattr(e, 'detail', str(e))
        assert 'rolled back' in str(detail).lower() or 'rollback' in str(detail).lower() or 'Forced' in str(detail)
        print(f'[PASS] TEST 8 rollback message: {detail}')
    finally:
        rf._upsert_student = real_upsert
        _remove_upload_cache(rollback_file)

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT COUNT(*) AS c FROM students WHERE usn LIKE '4HGTEST1%'")
        leftover = cur.fetchone()['c']
        cur.close()
    assert leftover == 0, f'partial data remained after rollback: {leftover}'
    print('[PASS] TEST 8 no partial data after rollback')

    cleanup_test_data()
    # also cleanup 4HGTEST
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM marks WHERE usn LIKE '4HGTEST%'")
        cur.execute("DELETE FROM students WHERE usn LIKE '4HGTEST%'")
        conn.commit(); cur.close()

    print('=' * 70)
    print('ALL INTEGRATION TESTS PASSED')
    print('=' * 70)


if __name__ == '__main__':
    run()
