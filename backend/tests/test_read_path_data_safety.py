"""Read endpoints must never mutate student data (master QA, Phase 1 finding).

A search used to begin by "reconciling trashed file data", which swept away
every student whose ``source_file`` had no matching ``uploaded_files`` row.
Any row not created through the upload UI — script-seeded, restored from a
backup, or imported before upload tracking existed — was therefore deleted the
moment someone typed anything into the search box, with no audit and no undo.

These tests pin both halves of the fix:
  * searching is provably non-destructive, and
  * a file the college actually purged from Trash still retires only *its*
    students, and does so undoably and with an audit record.
"""
import os
import sys
import unittest
from unittest.mock import patch

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from fastapi import HTTPException

import routes_files
from database import db_conn
from routes_query import QueryRequest, generate_query

ADMIN = {"username": "qa_admin", "role": "Admin"}
GHOST_USN = "9ZZQNOS001"          # source_file that was never registered
PURGE_A, PURGE_B = "9ZZQPRG001", "9ZZQPRG002"
LIVE_USN = "9ZZQLIV001"
PURGE_FILE = "qa_purge_me.xlsx"
LIVE_FILE = "qa_keep_me.xlsx"
PURGE_USNS = (PURGE_A, PURGE_B)


def _exec(sql, params=()):
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, list(params))
        row = cur.fetchone()
        conn.commit()
        cur.close()
    return row


def _count(table, where="", params=()):
    return _exec(f"SELECT COUNT(*) FROM {table} {where}", params)[0]


def _add_student(usn, source_file, with_marks=True):
    _exec("DELETE FROM marks WHERE usn=%s", (usn,))
    _exec("DELETE FROM students WHERE usn=%s", (usn,))
    _exec("INSERT INTO students (usn,name,current_sem,status,lifecycle_status,source_file) "
          "VALUES (%s,%s,4,'ACTIVE','Active',%s)", (usn, f"QA {usn}", source_file))
    if with_marks:
        _exec("INSERT INTO marks (usn,semester,sgpa) VALUES (%s,1,7.50)", (usn,))


class SearchNeverDeletesTests(unittest.TestCase):
    """The bug fired on *any* search, junk or well-formed."""

    @classmethod
    def setUpClass(cls):
        _exec("DELETE FROM uploaded_files WHERE filename IN (%s,%s)", (PURGE_FILE, LIVE_FILE))
        _add_student(GHOST_USN, "file_that_does_not_exist.xlsx")

    @classmethod
    def tearDownClass(cls):
        _exec("DELETE FROM marks WHERE usn=%s", (GHOST_USN,))
        _exec("DELETE FROM students WHERE usn=%s", (GHOST_USN,))

    def test_searching_keeps_students_without_registered_source_file(self):
        before = _count("students")
        for query in ["show all students", "???", "who not paid fees", "top 5 students by cgpa"]:
            try:
                generate_query(QueryRequest(natural_query=query, language="en",
                                            response_language="en", debug=False),
                               current_user=ADMIN)
            except HTTPException:
                pass  # a safe clarification is fine; deletion is not.
        self.assertEqual(_count("students"), before,
                         f"a search changed the student count ({query!r})")
        self.assertEqual(_count("students", "WHERE usn=%s", (GHOST_USN,)), 1,
                         "search deleted the student whose source file is unregistered")
        self.assertEqual(_count("marks", "WHERE usn=%s", (GHOST_USN,)), 1,
                         "search deleted the marks of that student")

    def test_analytics_and_generate_are_not_reconciling(self):
        # Tripwire: if a read endpoint reaches for the Trash sweep again, fail loudly.
        with patch.object(routes_files, "_reconcile_orphaned_source_records",
                          side_effect=AssertionError("read path swept student data")), \
             patch.object(routes_files, "_reconcile_trashed_file_records",
                          side_effect=AssertionError("read path reconciled trash")):
            for query in ["show all students", "active students"]:
                try:
                    generate_query(QueryRequest(natural_query=query, language="en",
                                                response_language="en", debug=False),
                                   current_user=ADMIN)
                except HTTPException:
                    pass
        self.assertEqual(_count("students", "WHERE usn=%s", (GHOST_USN,)), 1)


class PurgedFileRetirementTests(unittest.TestCase):
    """The legitimate purpose of the sweep, exercised at the right moment."""

    @classmethod
    def setUpClass(cls):
        _add_student(PURGE_A, PURGE_FILE)
        _add_student(PURGE_B, PURGE_FILE)
        _add_student(LIVE_USN, LIVE_FILE)
        _exec("INSERT INTO uploaded_files (filename,file_type,uploaded_by,db_status,trashed_at) "
              "VALUES (%s,'xlsx','qa_admin','completed',DATE_SUB(NOW(),INTERVAL 31 DAY))",
              (PURGE_FILE,))
        _exec("INSERT INTO uploaded_files (filename,file_type,uploaded_by,db_status) "
              "VALUES (%s,'xlsx','qa_admin','completed')", (LIVE_FILE,))

    @classmethod
    def tearDownClass(cls):
        for usn in PURGE_USNS + (LIVE_USN,):
            _exec("DELETE FROM marks WHERE usn=%s", (usn,))
            _exec("DELETE FROM students WHERE usn=%s", (usn,))
        _exec("DELETE FROM uploaded_files WHERE filename IN (%s,%s)", (PURGE_FILE, LIVE_FILE))
        _exec("DELETE FROM global_undo_snapshots WHERE description LIKE 'Purged %QA student(s)%'")
        _exec("DELETE FROM audit_log WHERE username=%s", ("qa_admin",))

    def test_purge_removes_only_that_files_students_and_stays_undoable(self):
        ph = ",".join(["%s"] * len(PURGE_USNS))
        self.assertEqual(_count("students", f"WHERE usn IN ({ph})", PURGE_USNS), 2)

        with db_conn() as conn:
            cur = conn.cursor(dictionary=True)
            purged = routes_files._purge_expired_trash(cur)
            self.assertIn(PURGE_FILE, purged, "expired trash entry was not purged")
            changed = routes_files._reconcile_orphaned_source_records(
                cur, purged, "qa_admin", conn)
            conn.commit()
            cur.close()
        self.assertTrue(changed)

        self.assertEqual(_count("students", f"WHERE usn IN ({ph})", PURGE_USNS), 0,
                         "purged file's students must be retired")
        self.assertEqual(_count("marks", f"WHERE usn IN ({ph})", PURGE_USNS), 0,
                         "purged file's marks must be retired")
        self.assertEqual(_count("students", "WHERE usn=%s", (LIVE_USN,)), 1,
                         "a live file's student must not be touched")

        audit = _exec("SELECT COUNT(*) FROM audit_log WHERE action='FILE_DATA_PURGE' "
                      "AND username='qa_admin'")
        self.assertGreaterEqual(audit[0], 1, "bulk retirement must leave an audit record")
        snap = _exec("SELECT COUNT(*) FROM global_undo_snapshots WHERE operation_type='DELETE' "
                     "AND performed_by='qa_admin'")
        self.assertGreaterEqual(snap[0], 1, "bulk retirement must be undoable")


if __name__ == "__main__":
    unittest.main(verbosity=2)
