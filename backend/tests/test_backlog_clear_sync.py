"""
Backlog "cleared" consistency tests.

Two real-world bugs are pinned here:
  1. A natural-language update that sets students.backlogs to a cleared/none
     value left the structured student_backlogs rows untouched, so a cleared
     backlog kept appearing in reports.
  2. The report model surfaced student_backlogs rows regardless of the cleared
     flag or the students.backlogs text.

Rules honored:
  * Expected values are hand-computed from the synthetic rows we seed (DB
    truth), never from the code under test.
  * Synthetic USNs (9ZZBL…) only; every seeded row is deleted in teardown and
    zero leakage is asserted. Production students are never touched.
"""
import os
import sys
import unittest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import report_service
from database import db_conn
from routes_query import _sync_backlogs_from_column

CLEARED_USN = "9ZZBL0001"   # students.backlogs='cleared', one active table row
DESCRIBE_USN = "9ZZBL0002"  # students.backlogs='Physics, 4, 2024; DBMS, 4, 2024'
ADMIN = {"username": "bl_admin", "role": "Admin"}


def _exec(sql, params=()):
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, list(params))
        conn.commit()
        cur.close()


def _query(sql, params=()):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, list(params))
        rows = cur.fetchall()
        cur.close()
        return rows


def _cleanup():
    for usn in (CLEARED_USN, DESCRIBE_USN):
        _exec("DELETE FROM student_backlogs WHERE usn=%s", (usn,))
        _exec("DELETE FROM students WHERE usn=%s", (usn,))


class BacklogClearSyncTests(unittest.TestCase):
    def setUp(self):
        _cleanup()
        _exec("INSERT INTO students (usn, name, backlogs) VALUES (%s,'Cleared Kid','cleared')",
              (CLEARED_USN,))
        _exec("INSERT INTO student_backlogs (usn, subject, semester, year, cleared) "
              "VALUES (%s,'Cybersecurity',3,'2027',0)", (CLEARED_USN,))
        _exec("INSERT INTO students (usn, name, backlogs) "
              "VALUES (%s,'Describe Kid','Physics, 4, 2024; DBMS, 4, 2024')",
              (DESCRIBE_USN,))
        # A stale row that the descriptive text should replace entirely.
        _exec("INSERT INTO student_backlogs (usn, subject, semester, year, cleared) "
              "VALUES (%s,'Old Subject',1,'2023',0)", (DESCRIBE_USN,))

    def tearDown(self):
        _cleanup()
        leftover = _query(
            "SELECT usn FROM students WHERE usn IN (%s, %s)", (CLEARED_USN, DESCRIBE_USN))
        self.assertEqual(leftover, [], "synthetic rows leaked into production data")

    # ---- report model honesty --------------------------------------------
    def test_report_model_omits_cleared_backlog(self):
        # DB truth: student says 'cleared' yet a table row still says uncleared.
        model = report_service.build_report_model([{"usn": CLEARED_USN}], ADMIN)
        st = model["students"][0]
        self.assertEqual(st["backlogs"], [])

    def test_report_model_keeps_genuine_active_backlog(self):
        # Expected rows computed by hand from the seeded descriptive text:
        # exactly the two subjects named, nothing from the stale 'Old Subject'.
        _exec("DELETE FROM student_backlogs WHERE usn=%s", (DESCRIBE_USN,))
        _exec("INSERT INTO student_backlogs (usn, subject, semester, year, cleared) "
              "VALUES (%s,'Physics',4,'2024',0)", (DESCRIBE_USN,))
        _exec("INSERT INTO student_backlogs (usn, subject, semester, year, cleared) "
              "VALUES (%s,'DBMS',4,'2024',0)", (DESCRIBE_USN,))
        model = report_service.build_report_model([{"usn": DESCRIBE_USN}], ADMIN)
        st = model["students"][0]
        subjects = sorted(b["subject"] for b in st["backlogs"])
        self.assertEqual(subjects, ["DBMS", "Physics"])

    # ---- column -> table sync --------------------------------------------
    def test_sync_marks_rows_cleared_for_no_backlog_text(self):
        with db_conn() as conn:
            conn.autocommit = False
            cur = conn.cursor()
            _sync_backlogs_from_column(cur, conn, [CLEARED_USN])
            conn.commit()
            cur.close()
        rows = _query("SELECT cleared FROM student_backlogs WHERE usn=%s", (CLEARED_USN,))
        self.assertTrue(rows, "sync should not delete history, only flag cleared")
        self.assertTrue(all(r["cleared"] == 1 for r in rows))

    def test_sync_replaces_rows_for_descriptive_text(self):
        with db_conn() as conn:
            conn.autocommit = False
            cur = conn.cursor()
            _sync_backlogs_from_column(cur, conn, [DESCRIBE_USN])
            conn.commit()
            cur.close()
        rows = _query("SELECT subject, cleared FROM student_backlogs WHERE usn=%s",
                      (DESCRIBE_USN,))
        subjects = sorted(r["subject"] for r in rows)
        self.assertIn("Physics", subjects)
        self.assertIn("DBMS", subjects)
        self.assertNotIn("Old Subject", subjects, "stale row must be replaced")
        self.assertTrue(all(r["cleared"] == 0 for r in rows))

    def test_sync_leaves_empty_text_untouched(self):
        # An update that blanks the column must not silently clear real rows.
        _exec("UPDATE students SET backlogs='' WHERE usn=%s", (CLEARED_USN,))
        _exec("UPDATE student_backlogs SET cleared=0 WHERE usn=%s", (CLEARED_USN,))
        with db_conn() as conn:
            conn.autocommit = False
            cur = conn.cursor()
            _sync_backlogs_from_column(cur, conn, [CLEARED_USN])
            conn.commit()
            cur.close()
        rows = _query("SELECT cleared FROM student_backlogs WHERE usn=%s", (CLEARED_USN,))
        self.assertTrue(all(r["cleared"] == 0 for r in rows))

    def test_sync_ignores_unknown_usns(self):
        with db_conn() as conn:
            conn.autocommit = False
            cur = conn.cursor()
            _sync_backlogs_from_column(cur, conn, ["9ZZBL9999"])
            conn.commit()
            cur.close()  # no exception, no rows for an absent student


if __name__ == "__main__":
    unittest.main()
