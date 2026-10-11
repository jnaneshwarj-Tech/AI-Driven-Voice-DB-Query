"""
Regression suite: natural-language query correctness verified against
independently-computed DB truth.

Expected results are produced by hand-written, authoritative SQL run directly
against MySQL (via db_conn), NOT by the query-understanding layer / LLM under
test. The app's actual output is produced by calling generate_query() in-process.
A test PASSES only when expected (DB truth) == actual (app).

Per-test observability is written to _regression_report.json (spec section 7).
"""
import io
import json
import os
import sys
import unittest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from database import db_conn
from routes_query import (
    QueryRequest,
    generate_query,
    _current_academic_fields_sql,
)

ADMIN = {"username": "admin", "role": "Admin"}

# Authoritative project rules reused for *expected* SQL (schema/rule layer,
# not the NL parser under test). See spec section 8.
CS_EXPR, _CY_EXPR = _current_academic_fields_sql("s")
CGPA = ("COALESCE((SELECT AVG(m.sgpa) FROM marks m "
        "WHERE m.usn=s.usn AND m.sgpa IS NOT NULL), s.cgpa)")
# Stable secondary ordering used by the engine (admission batch, then USN).
TIEBREAK = (
    "(CASE WHEN UPPER(s.usn) REGEXP "
    "'^[0-9][A-Z]{2,3}[0-9]{2}[A-Z]{2,4}[0-9]{2,3}' "
    "THEN CAST(SUBSTRING(s.usn, 4, 2) AS UNSIGNED) - "
    "IF(CAST(RIGHT(s.usn, 3) AS UNSIGNED) >= 400, 1, 0) ELSE 999 END) ASC, s.usn ASC"
)
VALID_SEM = f"({CS_EXPR})"


def run_expected(sql, params=()):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, list(params))
        rows = cur.fetchall()
        cur.close()
    return rows


def app_result(query, language="en"):
    req = QueryRequest(
        natural_query=query, language=language,
        response_language="en", debug=True,
    )
    return generate_query(req, current_user=ADMIN)


def app_usns(query, language="en"):
    resp = app_result(query, language)
    return [r.get("usn") for r in (resp.get("data") or [])], resp


def usn_set(rows):
    return sorted(r["usn"] for r in rows)


class RegressionQueryTests(unittest.TestCase):
    report = []

    def _record(self, test_id, query, language, expected, actual, passed, detail=""):
        self.report.append({
            "test_id": test_id, "query": query, "language": language,
            "expected_count": expected, "actual_count": actual,
            "passed": bool(passed), "detail": detail,
        })

    # ── A: top 10 5th sem by CGPA ────────────────────────────────────────────
    def test_A_top10_5th_sem_cgpa(self):
        q = "show top 10 students from 5th semester by cgpa"
        exp = run_expected(
            f"SELECT s.usn, ROUND({CGPA},2) cgpa FROM students s "
            f"WHERE {VALID_SEM} = 5 ORDER BY {CGPA} DESC, {TIEBREAK} LIMIT 10")
        act_usns, resp = app_usns(q)
        exp_usns = [r["usn"] for r in exp]
        rows = resp.get("data") or []
        self.assertEqual(act_usns, exp_usns, f"A order mismatch: {act_usns} vs {exp_usns}")
        for row in rows:
            self.assertIn("cgpa", row, "A: cgpa column missing from result")
            self.assertIsNotNone(row["cgpa"], "A: cgpa is null")
        cg = [r["cgpa"] for r in rows]
        self.assertTrue(all(cg[i] >= cg[i + 1] for i in range(len(cg) - 1)), "A: cgpa not desc")
        self._record("A", q, "en", len(exp), len(rows), True)

    # ── B: rural 5th sem more than 8 cgpa + threshold variants ────────────────
    def _b_expected(self, op, val):
        return run_expected(
            f"SELECT s.usn FROM students s WHERE UPPER(COALESCE(s.area_type,''))='RURAL' "
            f"AND {VALID_SEM}=5 AND {CGPA} {op} %s", [val])

    def test_B_rural_5th_gt8_cgpa(self):
        q = "list the students from rural in 5th sem having more than 8 cgpa"
        exp = self._b_expected(">", 8.0)
        act_usns, resp = app_usns(q)
        self.assertEqual(sorted(act_usns), usn_set(exp), "B set mismatch")
        for row in (resp.get("data") or []):
            self.assertGreater(row["cgpa"], 8.0, "B: row cgpa <= 8")
        self._record("B", q, "en", len(exp), len(act_usns), True)

    def test_B_threshold_variants(self):
        cases = [("more than 0", ">", 0.0), ("more than 8", ">", 8.0),
                 ("more than 10", ">", 10.0), ("less than 8", "<", 8.0),
                 ("at least 8", ">=", 8.0), ("at most 8", "<=", 8.0)]
        for phrase, op, val in cases:
            q = f"list the rural students in 5th sem having {phrase} cgpa"
            exp = self._b_expected(op, val)
            act_usns, _ = app_usns(q)
            self.assertEqual(sorted(act_usns), usn_set(exp),
                             f"B variant {phrase!r} mismatch ({len(act_usns)} vs {len(exp)})")
            self._record(f"B:{phrase}", q, "en", len(exp), len(act_usns), True)

    # ── C: born between 2005 and 2006 (inclusive boundaries) ──────────────────
    def _c_expected(self):
        return run_expected(
            "SELECT s.usn FROM students s WHERE YEAR(s.dob) BETWEEN 2005 AND 2006 "
            f"ORDER BY {TIEBREAK}")

    def test_C_born_2005_2006(self):
        q = "show students born between 2005 and 2006"
        exp = self._c_expected()
        act_usns, _ = app_usns(q)
        self.assertEqual(sorted(act_usns), usn_set(exp), "C set mismatch")
        self._record("C", q, "en", len(exp), len(act_usns), True)

    def test_C_boundaries_inclusive(self):
        exp = self._c_expected()
        exp_usns = set(r["usn"] for r in exp)
        # boundary rows must be included (Jan 2005 and Dec 2006)
        jan05 = run_expected("SELECT usn FROM students WHERE dob>='2005-01-01' AND dob<='2005-01-31'")
        dec06 = run_expected("SELECT usn FROM students WHERE dob>='2006-12-01' AND dob<='2006-12-31'")
        for r in jan05 + dec06:
            self.assertIn(r["usn"], exp_usns, f"C boundary excluded {r['usn']}")
        # just-outside rows excluded
        out = run_expected("SELECT usn FROM students WHERE YEAR(dob)=2004 OR YEAR(dob)=2007")
        q = "show students born between 2005 and 2006"
        act_usns, _ = app_usns(q)
        for r in out:
            self.assertNotIn(r["usn"], act_usns, f"C excluded-year leaked {r['usn']}")
        self._record("C:boundaries", q, "en", len(exp_usns), len(act_usns), True)

    # ── D: Kannada birth-range == English (same records) ──────────────────────
    def test_D_kannada_birth_range_equivalence(self):
        exp = self._c_expected()
        kn = "2005 ರಿಂದ 2006ರ ಮಧ್ಯೆ ಹುಟ್ಟಿರುವ ವಿದ್ಯಾರ್ಥಿಯ ಮಾಹಿತಿ"
        act_usns, resp = app_usns(kn, language="kn")
        self.assertEqual(sorted(act_usns), usn_set(exp),
                         f"D Kannada != DB truth ({len(act_usns)} vs {len(exp)})")
        self._record("D", kn, "kn", len(exp), len(act_usns), True)

    # ── E: incomplete personal details ────────────────────────────────────────
    _REQ = ["name", "gender", "dob", "blood_group", "aadhar_no", "phone",
            "email", "address", "father_name", "mother_name"]

    def test_E_incomplete_personal_details(self):
        conds = " OR ".join(
            "(NULLIF(TRIM(COALESCE(s.`%s`,'')),'') IS NULL)" % c for c in self._REQ)
        exp = run_expected(f"SELECT s.usn FROM students s WHERE {conds}")
        q = "show students with incomplete personal details"
        act_usns, resp = app_usns(q)
        self.assertEqual(sorted(act_usns), usn_set(exp), "E set mismatch")
        for row in (resp.get("data") or []):
            self.assertGreaterEqual(row.get("missing_count", 0), 1, "E: missing_count<1")
        self._record("E", q, "en", len(exp), len(act_usns), True)

    # ── F: top 10 3rd sem SGPA of 2023 batch (marks semester, not current) ─────
    def test_F_top10_3rd_sem_sgpa_2023(self):
        q = "top 10 3rd sem sgpa of 2023 batch"
        exp = run_expected(
            "SELECT s.usn, ROUND(m.sgpa,2) sgpa FROM students s "
            "JOIN marks m ON m.usn=s.usn AND m.semester=3 AND m.sgpa IS NOT NULL "
            "WHERE s.admission_year=2023 "
            "GROUP BY s.usn ORDER BY MAX(m.sgpa) DESC, " + TIEBREAK + " LIMIT 10")
        act_usns, resp = app_usns(q)
        rows = resp.get("data") or []
        self.assertEqual(len(rows), 10, "F: not 10 rows")
        for row in rows:
            self.assertIn("sgpa", row, "F: sgpa column missing")
            self.assertIsNotNone(row["sgpa"], "F: sgpa null")
        sg = [r["sgpa"] for r in rows]
        self.assertTrue(all(sg[i] >= sg[i + 1] for i in range(len(sg) - 1)), "F: sgpa not desc")
        self.assertEqual(sorted(act_usns), sorted(r["usn"] for r in exp), "F set mismatch")
        self._record("F", q, "en", len(exp), len(rows), True)

    # ── G: rural 5th sem hassan district (typo) ───────────────────────────────
    def test_G_rural_5th_hassan_district_typo(self):
        exp = run_expected(
            f"SELECT s.usn FROM students s WHERE UPPER(COALESCE(s.area_type,''))='RURAL' "
            f"AND {VALID_SEM}=5 AND LOWER(COALESCE(s.district,'')) LIKE '%hassan%'")
        for phrase in ("hassan distict", "hassan district", "hassan distrct"):
            q = f"rural 5th sem {phrase}"
            act_usns, _ = app_usns(q)
            self.assertEqual(sorted(act_usns), usn_set(exp),
                             f"G ({phrase}) set mismatch ({len(act_usns)} vs {len(exp)})")
            self._record(f"G:{phrase}", q, "en", len(exp), len(act_usns), True)

    # ── H: last 10 7th sem by cgpa (lowest) ───────────────────────────────────
    def test_H_last10_7th_sem_cgpa(self):
        q = "last 10 7th sem students by cgpa"
        exp = run_expected(
            f"SELECT s.usn, ROUND({CGPA},2) cgpa FROM students s WHERE {VALID_SEM}=7 "
            f"AND {CGPA} IS NOT NULL ORDER BY {CGPA} ASC, {TIEBREAK} LIMIT 10")
        act_usns, resp = app_usns(q)
        rows = resp.get("data") or []
        cg = [r["cgpa"] for r in rows]
        self.assertTrue(all(cg[i] <= cg[i + 1] for i in range(len(cg) - 1)), "H: cgpa not asc")
        self.assertEqual(act_usns, [r["usn"] for r in exp], "H order/set mismatch")
        self._record("H", q, "en", len(exp), len(rows), True)

    @classmethod
    def tearDownClass(cls):
        out = os.path.join(BACKEND, "_regression_report.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(cls.report, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
