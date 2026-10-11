"""
Phase-4 regression: distance near/far/between + backlog academic projection.

Expected results are computed by hand-written authoritative SQL run directly
against MySQL (NOT the parser under test). The app runs in-process via
generate_query(). A test passes only when DB truth == app output.
"""
import os
import sys
import unittest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from database import db_conn
from routes_query import QueryRequest, generate_query
from routes_files import _upsert_backlogs, _is_no_backlog

ADMIN = {"username": "admin", "role": "Admin"}
NOTNULL = "s.distance_from_college IS NOT NULL AND TRIM(s.distance_from_college) <> ''"
CAST = "CAST(s.distance_from_college AS UNSIGNED)"


def _exp(sql, params=()):
    with db_conn() as c:
        cur = c.cursor(dictionary=True)
        cur.execute(sql, list(params))
        rows = cur.fetchall()
        cur.close()
    return rows


class DistanceAndBacklogTests(unittest.TestCase):
    def _run(self, q):
        resp = generate_query(
            QueryRequest(natural_query=q, language="en",
                         response_language="en", debug=True),
            current_user=ADMIN,
        )
        self.assertIsNone(resp.get("error"), resp.get("error"))
        return resp, [r.get("usn") for r in (resp.get("data") or [])]

    def test_near_to_college_lt50(self):
        exp = _exp(f"SELECT s.usn FROM students s WHERE {NOTNULL} AND {CAST} < 50")
        _, got = self._run("students who are near to college")
        self.assertEqual(sorted(got), sorted(r["usn"] for r in exp))
        self.assertGreater(len(got), 0, "near must return rows, not 0")

    def test_far_from_college_gt100(self):
        exp = _exp(f"SELECT s.usn FROM students s WHERE {NOTNULL} AND {CAST} > 100")
        _, got = self._run("students far from college")
        self.assertEqual(sorted(got), sorted(r["usn"] for r in exp))

    def test_between_distance(self):
        exp = _exp(f"SELECT s.usn FROM students s WHERE {NOTNULL} AND {CAST} BETWEEN 30 AND 60")
        _, got = self._run("students distance between 30 and 60 km")
        self.assertEqual(sorted(got), sorted(r["usn"] for r in exp))

    def test_explicit_less_than_still_works(self):
        exp = _exp(f"SELECT s.usn FROM students s WHERE {NOTNULL} AND {CAST} < 20")
        _, got = self._run("students whose distance from college is less than 20 km")
        self.assertEqual(sorted(got), sorted(r["usn"] for r in exp))

    def test_backlog_list_projects_academic_and_subject(self):
        # DB truth: the set of *students* holding an active (uncleared) backlog.
        # This is a student listing, so only backlogs whose USN still resolves to
        # an existing students row are shown — orphan backlog rows (historical
        # data for removed/non-imported students) must not appear, matching the
        # engine's INNER JOIN students.
        exp = _exp(
            "SELECT sb.usn, sb.subject, sb.semester FROM student_backlogs sb "
            "JOIN students s ON s.usn = sb.usn WHERE sb.cleared=0")
        resp, got = self._run("list students with backlogs details")
        self.assertEqual(sorted(got), sorted(r["usn"] for r in exp))
        rows = resp.get("data") or []
        self.assertGreater(len(rows), 0)
        for row in rows:
            self.assertTrue(row.get("subject"), "backlog subject blank")
            self.assertIn("cgpa", row, "cgpa column missing")
            # Sem must never be blank: stored value, else parsed from the subject
            # text, else the student's derived current semester.
            self.assertIsNotNone(row.get("semester"),
                                 f"semester blank for {row['usn']}")
            self.assertTrue(1 <= int(row["semester"]) <= 8,
                            f"semester out of range for {row['usn']}")
        # Where a backlog row has a stored semester, the display must equal it.
        stored = {r["usn"]: r["semester"] for r in exp if r["semester"] is not None}
        for row in rows:
            if row["usn"] in stored:
                self.assertEqual(int(row["semester"]), int(stored[row["usn"]]),
                                 f"stored semester overridden for {row['usn']}")
        # The whole point of the fix: the listing spans multiple semesters,
        # not a single one.
        sems = {int(r["semester"]) for r in rows}
        self.assertGreater(len(sems), 1, f"only one semester shown: {sems}")
        # Every student with at least one mark row must show a non-null CGPA.
        for row in rows:
            has_marks = _exp(
                "SELECT 1 x FROM marks WHERE usn=%s AND sgpa IS NOT NULL", [row["usn"]])
            if has_marks:
                self.assertIsNotNone(row["cgpa"],
                                     f"cgpa blank for {row['usn']} though marks exist")

    def test_backlog_per_semester_filter_uses_derived_semester(self):
        # Truth: active backlogs whose *effective* semester is 4 — stored value,
        # else the semester written into the free-text subject.
        exp = _exp(
            "SELECT usn FROM student_backlogs WHERE cleared=0 AND "
            "COALESCE(NULLIF(semester,0), "
            "NULLIF(CAST(NULLIF(REGEXP_SUBSTR(LOWER(subject), "
            "'[1-8](st|nd|rd|th)?[ ]?sem'), '') AS UNSIGNED), 0)) = 4")
        _, got = self._run("list backlog students 4th sem")
        self.assertEqual(sorted(got), sorted(r["usn"] for r in exp))


class BacklogParserTests(unittest.TestCase):
    """_upsert_backlogs must capture every real backlog form value, and never
    invent rows for 'No'/'0'/'Not applicable'. Uses a synthetic USN and removes
    it in teardown — production backlog rows are never touched."""
    SYN = "9ZZ99BLTEST"

    def _write(self, text):
        with db_conn() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM student_backlogs WHERE usn=%s", (self.SYN,))
            n = _upsert_backlogs(cur, self.SYN, text)
            c.commit()
            cur.close()
        return n

    def tearDown(self):
        with db_conn() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM student_backlogs WHERE usn=%s", (self.SYN,))
            c.commit()
            cur.close()

    def test_no_backlog_values_write_nothing(self):
        for t in ("No", "no", "0", "0.0", "No backlog", "No Backlogs",
                  "Zero backlogs", "Not applicable", "-", ""):
            self.assertEqual(self._write(t), 0, f"'{t}' should write nothing")

    def test_bare_count_writes_one_row(self):
        self.assertEqual(self._write("2"), 1, "count '2' must record a backlog")
        self.assertEqual(self._write("5"), 1)

    def test_descriptive_text_writes_row(self):
        self.assertEqual(self._write("Mathamatics sem 2"), 1)
        self.assertEqual(self._write(
            "Calculus and linear algebra 1BMATS101 1st semester 2025"), 1)

    def test_is_no_backlog_classifier(self):
        for t in ("No", "0", "zero", "Not applicable", "no backlogs"):
            self.assertTrue(_is_no_backlog(t), t)
        for t in ("1", "2", "Mathamatics sem 2", "DSA"):
            self.assertFalse(_is_no_backlog(t), t)


if __name__ == "__main__":
    unittest.main(verbosity=2)
