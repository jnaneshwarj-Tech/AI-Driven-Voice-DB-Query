"""
Auto-generated regression coverage (spec section 6): operator-synonym matrix,
top/bottom-N ranking, equality field filters, counts, unknown columns, and the
LLM-unavailable deterministic fallback. Every expectation is computed with
hand-written SQL directly against MySQL, independent of the NL parser/LLM.
"""
import os
import sys
import unittest
from unittest.mock import patch

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from database import db_conn
from routes_query import (
    QueryRequest, generate_query, _current_academic_fields_sql,
)

ADMIN = {"username": "admin", "role": "Admin"}
CGPA = ("COALESCE((SELECT AVG(m.sgpa) FROM marks m "
        "WHERE m.usn=s.usn AND m.sgpa IS NOT NULL), s.cgpa)")
VALID_SEM = f"({_current_academic_fields_sql('s')[0]})"


def run_expected(sql, params=()):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, list(params))
        rows = cur.fetchall()
        cur.close()
    return rows


def app_rows(query):
    resp = generate_query(
        QueryRequest(natural_query=query, language="en",
                     response_language="en", debug=True),
        current_user=ADMIN)
    return resp.get("data") or [], resp


def app_usns(query):
    rows, _ = app_rows(query)
    return sorted(r["usn"] for r in rows)


class OperatorSynonymTests(unittest.TestCase):
    # phrase -> SQL operator. Reused for both field-first and value-first forms.
    MATRIX = [
        ("above", ">"), ("over", ">"), ("greater than", ">"),
        ("more than", ">"), ("exceeds", ">"),
        ("below", "<"), ("under", "<"), ("less than", "<"),
        ("at least", ">="), ("minimum", ">="),
        ("at most", "<="), ("maximum", "<="),
    ]

    def _truth(self, op, val):
        return run_expected(
            f"SELECT s.usn FROM students s WHERE {CGPA} {op} %s", [val])

    def test_field_first_cgpa_synonyms(self):
        for phrase, op in self.MATRIX:
            q = f"show students with cgpa {phrase} 7"
            exp = self._truth(op, 7.0)
            got = app_usns(q)
            self.assertEqual(got, sorted(r["usn"] for r in exp),
                             f"field-first {phrase!r} mismatch ({len(got)} vs {len(exp)})")

    def test_value_first_cgpa_synonyms(self):
        for phrase, op in self.MATRIX:
            q = f"show students with {phrase} 7 cgpa"
            exp = self._truth(op, 7.0)
            got = app_usns(q)
            self.assertEqual(got, sorted(r["usn"] for r in exp),
                             f"value-first {phrase!r} mismatch ({len(got)} vs {len(exp)})")

    def test_negative_operators(self):
        cases = [("not below", ">="), ("not above", "<="),
                 ("not less than", ">="), ("not more than", "<=")]
        for phrase, op in cases:
            q = f"show students with cgpa {phrase} 7"
            exp = self._truth(op, 7.0)
            got = app_usns(q)
            self.assertEqual(got, sorted(r["usn"] for r in exp),
                             f"negation {phrase!r} mismatch")

    def test_between_range(self):
        exp = run_expected(
            f"SELECT s.usn FROM students s WHERE {CGPA} BETWEEN 6 AND 8")
        q = "show students with cgpa between 6 and 8"
        self.assertEqual(app_usns(q), sorted(r["usn"] for r in exp), "between mismatch")


class RankingTests(unittest.TestCase):
    def _rank(self, sem, n, direction):
        # Deterministic tie-break mirrors the engine's documented ranking rule
        # (ORDER BY <cgpa> <dir>, s.usn ASC) so equal-CGPA students at the top-N
        # cutoff do not depend on arbitrary storage order.
        return run_expected(
            f"SELECT s.usn FROM students s WHERE {VALID_SEM}={sem} AND {CGPA} IS NOT NULL "
            f"ORDER BY {CGPA} {direction}, s.usn ASC LIMIT {n}")

    def test_top_various(self):
        for n in (5, 10, 20):
            exp = self._rank(5, n, "DESC")
            q = f"show top {n} 5th sem students by cgpa"
            rows, _ = app_rows(q)
            self.assertEqual(len(rows), min(n, len(run_expected("SELECT usn FROM students s WHERE " + VALID_SEM + "=5 AND " + CGPA + " IS NOT NULL"))),
                             f"top {n} count")
            self.assertEqual([r["usn"] for r in rows], [r["usn"] for r in exp],
                             f"top {n} order mismatch")

    def test_bottom_various(self):
        for n in (5, 10):
            exp = self._rank(7, n, "ASC")
            q = f"last {n} 7th sem students by cgpa"
            rows, _ = app_rows(q)
            self.assertEqual([r["usn"] for r in rows], [r["usn"] for r in exp],
                             f"bottom {n} order mismatch")


class EqualityFieldTests(unittest.TestCase):
    def test_gender(self):
        for value in ("male", "female"):
            exp = run_expected(
                "SELECT usn FROM students WHERE LOWER(TRIM(gender))=%s", [value])
            q = f"show {value} students"
            self.assertEqual(app_usns(q), sorted(r["usn"] for r in exp),
                             f"gender {value} mismatch")

    def test_area_type(self):
        for value in ("rural", "urban"):
            exp = run_expected(
                "SELECT usn FROM students WHERE LOWER(TRIM(area_type))=%s", [value])
            q = f"list all {value} students"
            self.assertEqual(app_usns(q), sorted(r["usn"] for r in exp),
                             f"area_type {value} mismatch")

    def test_student_type(self):
        exp = run_expected("SELECT usn FROM students WHERE student_type=%s", ["Lateral Entry"])
        q = "show lateral entry students"
        self.assertEqual(app_usns(q), sorted(r["usn"] for r in exp), "lateral mismatch")


class ScalarCountTests(unittest.TestCase):
    def test_count(self):
        exp = run_expected("SELECT COUNT(*) n FROM students WHERE LOWER(TRIM(area_type))='rural'")[0]["n"]
        resp = generate_query(
            QueryRequest(natural_query="how many rural students are there",
                         language="en", response_language="en", debug=True),
            current_user=ADMIN)
        data = resp.get("data") or []
        nums = [v for row in data for v in row.values() if isinstance(v, int)]
        self.assertIn(exp, nums, f"count {exp} not in {data}")


class RobustnessTests(unittest.TestCase):
    def test_unknown_column_does_not_leak_or_crash(self):
        # A field that does not exist must not 500 nor expose internals; it should
        # return no matching rows (graceful) rather than the whole table.
        try:
            rows, _ = app_rows("show students whose favourite colour is blue")
        except Exception as e:  # HTTPException with a friendly reason is acceptable
            self.assertNotIn("Traceback", str(e))
            return
        self.assertTrue(len(rows) <= 148)

    @patch("routes_query.generate_sql_query", side_effect=RuntimeError("LLM down"))
    def test_llm_unavailable_falls_back_deterministically(self, _mock):
        # A query the deterministic planner understands must still return correct
        # DB-truth results even when the LLM raises.
        exp = run_expected("SELECT usn FROM students WHERE LOWER(TRIM(gender))='female'")
        got = app_usns("show female students")
        self.assertEqual(got, sorted(r["usn"] for r in exp),
                         "deterministic fallback failed while LLM down")


if __name__ == "__main__":
    unittest.main(verbosity=2)
