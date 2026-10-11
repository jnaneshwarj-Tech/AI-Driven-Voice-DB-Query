"""
Data-integrity guard tests (Phase 3A / Phase 7B of the master brief).

These pin the *identity immutability* and *no-fabricated-column* rules at the
assignment-resolution layer, using synthetic students only:

  * An ordinary edit that tries to change a student's USN is rejected with 400
    BEFORE any SQL runs, so the stored row is provably unchanged.
  * A legitimate field edit only *builds* an assignment — it must not touch the
    database by itself.
  * A hostile / unknown header is never turned into a SQL identifier or column
    (defence against identifier injection); the students table still exists and
    the row is intact afterwards.

Teardown deletes every seeded row and asserts zero leakage. Production rows are
never read into expectations beyond a controlled SELECT of our own synthetic
USNs.
"""
import os
import sys
import unittest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from fastapi import HTTPException

from database import db_conn
from routes_query import _resolve_assignment

SEED_USN = "9ZZINT0001"
OTHER_USN = "9ZZINT0002"


def _exec(sql, params=()):
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, list(params))
        conn.commit()
        cur.close()


def _one(sql, params=()):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, list(params))
        row = cur.fetchone()
        cur.close()
    return row


class IntegrityGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _exec("DELETE FROM students WHERE usn IN (%s, %s)", (SEED_USN, OTHER_USN))
        _exec("INSERT INTO students (usn, name, phone) VALUES (%s, 'Integrity Seed', '9000000001')",
              (SEED_USN,))

    @classmethod
    def tearDownClass(cls):
        _exec("DELETE FROM students WHERE usn IN (%s, %s)", (SEED_USN, OTHER_USN))
        left = _one("SELECT COUNT(*) c FROM students WHERE usn LIKE '9ZZINT%'")["c"]
        assert left == 0, f"synthetic integrity rows leaked: {left}"

    def _student(self):
        return _one("SELECT * FROM students WHERE usn=%s", (SEED_USN,))

    def test_usn_edit_is_rejected_and_row_unchanged(self):
        before = self._student()
        with db_conn() as conn:
            with self.assertRaises(HTTPException) as ctx:
                _resolve_assignment(conn, before,
                                    {"field_text": "usn", "value_text": OTHER_USN})
        self.assertEqual(ctx.exception.status_code, 400)
        after = self._student()
        self.assertEqual(after["usn"], SEED_USN, "USN must not change")
        self.assertEqual(after["name"], before["name"], "row must be untouched")

    def test_usn_cannot_be_created_as_dynamic_column(self):
        # A differently-worded identity field must also not rewrite the USN.
        before = self._student()
        with db_conn() as conn:
            with self.assertRaises(HTTPException):
                _resolve_assignment(conn, before,
                                    {"field_text": "student id", "value_text": OTHER_USN})
        self.assertEqual(self._student()["usn"], SEED_USN)

    def test_legit_edit_builds_assignment_without_writing(self):
        before = self._student()
        with db_conn() as conn:
            built = _resolve_assignment(conn, before,
                                        {"field_text": "phone", "value_text": "9111111111"})
        # The function only computes the assignment; the DB is still the old value.
        self.assertEqual(self._student()["phone"], before["phone"],
                         "resolve must not persist the change itself")
        self.assertTrue(isinstance(built, dict) and built, "assignment dict expected")

    def test_injected_header_never_becomes_identifier(self):
        before = self._student()
        hostile = "name); DROP TABLE students;--"
        with db_conn() as conn:
            with self.assertRaises(HTTPException):
                _resolve_assignment(conn, before,
                                    {"field_text": hostile, "value_text": "x"})
        # Table and row both survived the attempted injection.
        self.assertIsNotNone(_one("SELECT usn FROM students WHERE usn=%s", (SEED_USN,)))


if __name__ == "__main__":
    unittest.main()
