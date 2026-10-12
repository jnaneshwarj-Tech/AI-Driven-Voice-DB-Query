"""Master QA Phase 3 — complex filter queries.

Each phrasing is executed through the real query route and the returned student
set is compared with rows computed straight from MySQL. The truth expressions
(CGPA, current semester, canonical branch) are restated here from the documented
business rules instead of importing the app's SQL, so the engine cannot grade
its own homework.

Run against the isolated staging database:
    MYSQL_DB=student_db_staging ./.venv/Scripts/python.exe -m unittest \
        tests.test_master_phase3_filters
"""
import os
import re
import sys
import unittest
from datetime import date

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from fastapi import HTTPException

from database import db_conn
from routes_query import QueryRequest, generate_query

ADMIN = {"username": "qa_admin", "role": "Admin"}

# Restated from the documented rule: cumulative average of the semester marks,
# falling back to the stored cgpa column when no marks rows exist.
CGPA = ("ROUND(COALESCE((SELECT AVG(m.sgpa) FROM marks m WHERE m.usn=s.usn "
        "AND m.sgpa IS NOT NULL), s.cgpa), 2)")
AGE = "TIMESTAMPDIFF(YEAR, s.dob, CURDATE())"
USN_RE = re.compile(r"([0-9][A-Z]{2,3})([0-9]{2})([A-Z]{2,4})([0-9]{2,3})")
BRANCH_CANON = {
    "CS": "CS", "CSE": "CS", "COMPUTER SCIENCE AND ENGINEERING": "CS",
    "CV": "CV", "CIV": "CV", "CIVIL ENGINEERING": "CV",
    "EC": "EC", "ECE": "EC", "ELECTRONICS AND COMMUNICATION ENGINEERING": "EC",
    "IS": "IS", "ISE": "IS", "INFORMATION SCIENCE AND ENGINEERING": "IS",
    "ME": "ME", "MECH": "ME", "MECHANICAL ENGINEERING": "ME",
}


def sql_rows(query, params=()):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(query, list(params))
        rows = cur.fetchall()
        cur.close()
    return rows


def truth_usns(query, params=()):
    return sorted({r["usn"].upper() for r in sql_rows(query, params) if r.get("usn")})


def current_semester(usn):
    """VTU semester for a valid USN today: admission year + lateral entry + term."""
    m = USN_RE.fullmatch(usn.upper())
    if not m:
        return None
    admission = 2000 + int(m.group(2))
    lateral = int(m.group(4)) >= 400
    today = date.today()
    years = today.year - admission + (1 if lateral else 0) - (1 if today.month < 7 else 0)
    return max(1, min(8, years * 2 + (1 if today.month >= 7 else 0)))


def canonical_branch(usn, branch):
    raw = (branch or "").strip().upper()
    if raw in BRANCH_CANON:
        return BRANCH_CANON[raw]
    m = USN_RE.fullmatch(usn.upper())
    return m.group(3) if m else raw


def branch_truth(code):
    return sorted({r["usn"].upper() for r in sql_rows("SELECT usn, branch FROM students")
                   if canonical_branch(r["usn"], r["branch"]) == code})


def pick_value(column, exclude=("", None)):
    """Most frequent real value of a column, so the literals stay concrete."""
    rows = sql_rows(f"SELECT `{column}` AS v, COUNT(*) AS n FROM students "
                    f"WHERE `{column}` IS NOT NULL AND TRIM(`{column}`)<>'' "
                    f"GROUP BY `{column}` ORDER BY n DESC LIMIT 12")
    for r in rows:
        if r["v"] not in exclude:
            return r["v"]
    return None


def run(query, user=ADMIN, language="english"):
    """(USN set, response). A clarification comes back as an empty set plus
    `_http_error`, which callers may assert on."""
    req = QueryRequest(natural_query=query, language=language,
                       response_language="en", debug=False)
    try:
        resp = generate_query(req, current_user=user) or {}
    except HTTPException as exc:
        resp = {"_http_error": exc.status_code, "_detail": exc.detail}
    usns = sorted({(r.get("usn") or "").upper() for r in (resp.get("data") or [])
                   if r.get("usn")})
    return usns, resp


class Phase3FilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.district = pick_value("district")
        cls.other_district = next(
            (r["district"] for r in sql_rows(
                "SELECT district, COUNT(*) n FROM students WHERE TRIM(COALESCE(district,''))<>'' "
                "GROUP BY district ORDER BY n DESC")
             if r["district"] != cls.district), cls.district)
        cls.taluk = pick_value("taluk")
        cls.religion = pick_value("religion")
        cls.caste = pick_value("caste")
        cls.occupation = pick_value("father_occupation")
        cls.total = sql_rows("SELECT COUNT(*) n FROM students")[0]["n"]

    def assert_truth(self, phrasing, sql, params=(), note=""):
        exp = truth_usns(sql, params)
        act, resp = run(phrasing)
        self.assertEqual(
            act, exp,
            f"{phrasing!r} {note}: expected {len(exp)} students from DB truth, "
            f"got {len(act)} (http={resp.get('_http_error')}, "
            f"missing={sorted(set(exp) - set(act))[:6]}, "
            f"extra={sorted(set(act) - set(exp))[:6]})")
        return resp

    # ── 1. one filter per column ─────────────────────────────────────────────
    def test_single_filters_on_each_major_column(self):
        cases = [
            (f"show students from {self.district} district",
             "SELECT usn FROM students s WHERE LOWER(COALESCE(district,''))=%s",
             [self.district.lower()]),
            (f"list students of {self.taluk} taluk",
             "SELECT usn FROM students s WHERE LOWER(COALESCE(taluk,''))=%s",
             [self.taluk.lower()]),
            (f"show male students",
             "SELECT usn FROM students s WHERE LOWER(COALESCE(gender,''))='male'"),
            ("show female students",
             "SELECT usn FROM students s WHERE LOWER(COALESCE(gender,''))='female'"),
            (f"show {self.religion} religion students",
             "SELECT usn FROM students s WHERE LOWER(COALESCE(religion,''))=%s",
             [self.religion.lower()]),
            (f"list students of {self.caste} caste",
             "SELECT usn FROM students s WHERE LOWER(COALESCE(caste,''))=%s",
             [self.caste.lower()]),
            (f"show {self.occupation} father occupation students",
             "SELECT usn FROM students s WHERE LOWER(COALESCE(father_occupation,''))=%s",
             [self.occupation.lower()]),
            ("show lateral entry students",
             "SELECT usn FROM students s WHERE LOWER(COALESCE(student_type,''))='lateral'"),
            ("show rural students",
             "SELECT usn FROM students s WHERE UPPER(COALESCE(area_type,''))='RURAL'"),
        ]
        for phrasing, sql, *params in cases:
            self.assert_truth(phrasing, sql, params[0] if params else (), "single filter")

    # ── 2. branch is matched through the canonical code, not the raw string ──
    def test_branch_filter_collects_every_spelling(self):
        codes = sorted({canonical_branch(r["usn"], r["branch"])
                        for r in sql_rows("SELECT usn, branch FROM students")} - {""})
        for code in codes:
            exp = branch_truth(code)
            for phrasing in (f"show {code} branch students",
                             f"list students in {code}",
                             f"students of {code} department"):
                act, resp = run(phrasing)
                self.assertEqual(
                    act, exp,
                    f"{phrasing!r} for branch {code}: expected {len(exp)} students, "
                    f"got {len(act)} (http={resp.get('_http_error')}, "
                    f"missing={sorted(set(exp) - set(act))[:6]}, "
                    f"extra={sorted(set(act) - set(exp))[:6]})")

    # ── 3. numeric operators and their words ─────────────────────────────────
    def test_cgpa_operators(self):
        cases = [
            ("show students with cgpa above 7", f"{CGPA} > 7"),
            ("show students whose cgpa is more than 7", f"{CGPA} > 7"),
            ("show students with cgpa greater than or equal to 7", f"{CGPA} >= 7"),
            ("list students with at least 7 cgpa", f"{CGPA} >= 7"),
            ("show students with cgpa below 7", f"{CGPA} < 7"),
            ("show students with cgpa less than 7", f"{CGPA} < 7"),
            ("list students with at most 7 cgpa", f"{CGPA} <= 7"),
            ("show students with cgpa between 6 and 8", f"{CGPA} BETWEEN 6 AND 8"),
        ]
        for phrasing, cond in cases:
            self.assert_truth(phrasing, f"SELECT usn FROM students s WHERE {cond}",
                              note="cgpa operator")

    # ── 4. boundaries: inclusive vs exclusive must be exact ─────────────────
    def test_cgpa_boundary_values_are_included_or_excluded_correctly(self):
        # The bounds must be CGPA values the fixture really holds, otherwise the
        # "at least" vs "above" distinction below is measured against nothing.
        bounds = [str(r["c"]) for r in sql_rows(
            f"SELECT DISTINCT {CGPA} AS c FROM students s WHERE {CGPA} IS NOT NULL "
            f"ORDER BY c DESC LIMIT 6")][:3]
        self.assertTrue(bounds, "staging fixture has no CGPA values at all")
        for bound in bounds:
            at_or_above = truth_usns(f"SELECT usn FROM students s WHERE {CGPA} >= {bound}")
            above = truth_usns(f"SELECT usn FROM students s WHERE {CGPA} > {bound}")
            self.assertNotEqual(at_or_above, above,
                                f"staging fixture has no student at exactly {bound} cgpa; "
                                "the boundary case cannot be measured")
            for phrasing, cond in [
                    (f"show students with cgpa at least {bound}", f"{CGPA} >= {bound}"),
                    (f"show students with cgpa up to {bound}", f"{CGPA} <= {bound}"),
                    (f"show students with cgpa above {bound}", f"{CGPA} > {bound}"),
                    (f"show students with cgpa more than {bound}", f"{CGPA} > {bound}"),
                    (f"show students with cgpa below {bound}", f"{CGPA} < {bound}"),
                    (f"show students with cgpa exactly {bound}", f"{CGPA} = {bound}")]:
                self.assert_truth(phrasing, f"SELECT usn FROM students s WHERE {cond}",
                                  note="boundary")

    # ── 5. semester filter uses the computed academic semester ───────────────
    def test_current_semester_filter_matches_computed_semester(self):
        sems = sorted({s for s in (current_semester(r["usn"])
                                   for r in sql_rows("SELECT usn FROM students")) if s})
        for sem in [s for s in sems if s in (5, 7, 8)] or sems[-2:]:
            exp = sorted(r["usn"].upper() for r in sql_rows("SELECT usn FROM students")
                         if current_semester(r["usn"]) == sem)
            for phrasing in (f"show {sem}th semester students",
                             f"list students in semester {sem}"):
                act, resp = run(phrasing)
                self.assertEqual(act, exp,
                                 f"{phrasing!r}: semester {sem} truth is {len(exp)} rows, "
                                 f"got {len(act)} (http={resp.get('_http_error')})")

    # ── 6. age and date-of-birth ranges ──────────────────────────────────────
    def test_age_range_filters(self):
        lo, hi = 18, 21
        cases = [
            (f"show students aged between {lo} and {hi}",
             f"SELECT usn FROM students s WHERE dob IS NOT NULL AND {AGE} BETWEEN {lo} AND {hi}"),
            (f"list students with age more than {hi}",
             f"SELECT usn FROM students s WHERE dob IS NOT NULL AND {AGE} > {hi}"),
            (f"show students whose age is at least {lo}",
             f"SELECT usn FROM students s WHERE dob IS NOT NULL AND {AGE} >= {lo}"),
        ]
        for phrasing, sql in cases:
            self.assert_truth(phrasing, sql, note="age range")

    # ── 7. several filters joined by AND must all survive ────────────────────
    def test_multi_filter_and_keeps_every_condition(self):
        district_sql = "SELECT usn FROM students s WHERE LOWER(COALESCE(district,''))=%s"
        female_haveri = truth_usns(district_sql + " AND UPPER(COALESCE(gender,''))='FEMALE'",
                                   [self.district.lower()])
        self.assertEqual(
            run(f"show female students from {self.district} district")[0], female_haveri,
            "two-condition AND lost a condition")

        female_haveri_7 = truth_usns(
            district_sql + " AND UPPER(COALESCE(gender,''))='FEMALE' AND " + CGPA + " >= 7",
            [self.district.lower()])
        self.assertEqual(
            run(f"show female students from {self.district} district with cgpa at least 7")[0],
            female_haveri_7, "three-condition AND lost a condition")

        four = truth_usns(
            district_sql + " AND UPPER(COALESCE(gender,''))='FEMALE' AND " + CGPA + " >= 7"
            " AND dob IS NOT NULL AND " + AGE + " > 17", [self.district.lower()])
        self.assertEqual(
            run(f"show female students from {self.district} district with cgpa at least 7 "
                "and age more than 17")[0],
            four, "four-condition AND lost a condition")

        cs_haveri_7 = truth_usns(
            district_sql + " AND " + CGPA + " > 7 AND usn LIKE '9QA%%CS%%'",
            [self.district.lower()])
        self.assertEqual(
            run(f"list cs students from {self.district} district with cgpa above 7")[0],
            cs_haveri_7, "branch+district+cgpa AND lost a condition")

    # ── 8. OR and IN lists ───────────────────────────────────────────────────
    def test_or_and_in_lists(self):
        d1, d2 = self.district, self.other_district
        self.assert_truth(f"show students from {d1} or {d2} district",
                          "SELECT usn FROM students s WHERE LOWER(COALESCE(district,'')) IN (%s,%s)",
                          [d1.lower(), d2.lower()], "OR of 2")
        three = [r["district"] for r in sql_rows(
            "SELECT district FROM students WHERE TRIM(COALESCE(district,''))<>'' "
            "GROUP BY district ORDER BY COUNT(*) DESC LIMIT 3")]
        self.assert_truth(
            f"list students from {three[0]}, {three[1]} and {three[2]} districts",
            "SELECT usn FROM students s WHERE LOWER(COALESCE(district,'')) IN (%s,%s,%s)",
            [d.lower() for d in three], "IN of 3")
        act = run("show CS or EC branch students")[0]
        self.assertEqual(act, sorted(set(branch_truth("CS")) | set(branch_truth("EC"))),
                         "OR of two branches must be the union")

    # ── 9. negation ──────────────────────────────────────────────────────────
    def test_negated_filters(self):
        self.assert_truth(f"show students not from {self.district} district",
                          "SELECT usn FROM students s WHERE LOWER(COALESCE(district,''))<>%s",
                          [self.district.lower()], "negated value")
        self.assert_truth(f"list students except those from {self.district} district",
                          "SELECT usn FROM students s WHERE LOWER(COALESCE(district,''))<>%s",
                          [self.district.lower()], "except")
        self.assert_truth("show students without a district",
                          "SELECT usn FROM students s WHERE TRIM(COALESCE(district,''))=''")

    # ── 10. substring search ────────────────────────────────────────────────
    def test_contains_searches(self):
        for word in ("Ra", "hu"):
            self.assert_truth(f"show students whose name contains {word}",
                              "SELECT usn FROM students s WHERE LOWER(name) LIKE %s",
                              [f"%{word.lower()}%"], "name contains")
        self.assert_truth(f"show students whose address contains {self.taluk}",
                          "SELECT usn FROM students s WHERE LOWER(COALESCE(address,'')) LIKE %s "
                          "OR LOWER(COALESCE(permanent_address,'')) LIKE %s "
                          "OR LOWER(COALESCE(village,'')) LIKE %s "
                          "OR LOWER(COALESCE(taluk,'')) LIKE %s",
                          [f"%{self.taluk.lower()}%"] * 4, "address contains")

    # ── 11. impossible and unknown conditions must not widen the answer ──────
    def test_empty_and_unmappable_conditions(self):
        act, resp = run("show students from Atlantis district")
        self.assertTrue(act == [] or resp.get("_http_error") == 400,
                        f"unknown district answered with {len(act)} rows: {act[:6]}")
        self.assertLess(len(act), self.total, "unknown district widened to the whole table")

        act, resp = run(f"show male students from {self.district} district who are female")
        self.assertTrue(act == [] or resp.get("_http_error") == 400,
                        f"contradictory gender filter answered with {len(act)} rows")

    # ── 12. filters combined with ranking, limit and projection ──────────────
    def test_filter_with_top_n_and_projection(self):
        exp = [r["usn"].upper() for r in sql_rows(
            f"SELECT s.usn FROM students s "
            f"WHERE UPPER(COALESCE(s.branch,'')) IN ('CS','CSE') OR s.usn REGEXP '^[0-9][A-Z]{{2,3}}[0-9]{{2}}CS' "
            f"ORDER BY {CGPA} DESC, s.usn ASC LIMIT 5")]
        act, resp = run("show top 5 cs students by cgpa")
        self.assertEqual(sorted(act), sorted(exp),
                         f"top-5-with-filter returned {act} instead of {exp} "
                         f"(http={resp.get('_http_error')})")
        act, resp = run(f"show the names and cgpa of cs students with cgpa above 7")
        self.assertTrue(resp.get("data"), "projection query returned nothing")
        self.assertIn("cgpa", {k.lower() for r in resp["data"] for k in r},
                      "requested CGPA column missing from the projection")

    # ── 13. fee-status companion filters (multi-table) ───────────────────────
    def test_fee_status_filter_keeps_companion_conditions(self):
        unpaid = ("SELECT DISTINCT m.usn FROM student_fees m WHERE LOWER(TRIM("
                  "COALESCE(m.status,''))) IN ('no','not paid','unpaid','pending','due','balance','0')")
        no_fee = ("SELECT usn FROM students s WHERE NOT EXISTS (SELECT 1 FROM student_fees f "
                  "WHERE f.usn=s.usn AND LOWER(TRIM(COALESCE(f.status,''))) IN "
                  "('no','not paid','unpaid','pending','due','balance','0'))")
        rows_no_fee = truth_usns(no_fee)
        unpaid_usns = {r["usn"].upper() for r in sql_rows(unpaid)}
        act, resp = run("show students who have not paid fees")
        self.assertEqual(act, sorted(unpaid_usns),
                         f"fee filter alone returned {len(act)} of {len(unpaid_usns)} "
                         f"students with an unpaid row (http={resp.get('_http_error')})")

        act2, resp2 = run(f"show students from {self.district} district who have not paid fees")
        exp2 = sorted(unpaid_usns & set(truth_usns(
            "SELECT usn FROM students s WHERE LOWER(COALESCE(district,''))=%s",
            [self.district.lower()])))
        self.assertEqual(
            act2, exp2,
            f"the district condition was dropped next to the fee filter: got {len(act2)} "
            f"rows, truth is {len(exp2)} (http={resp2.get('_http_error')}); "
            f"extra={sorted(set(act2) - set(exp2))[:6]}")

        act3, resp3 = run(f"show students from {self.district} district who have paid all fees")
        exp3 = sorted(set(rows_no_fee) & set(truth_usns(
            "SELECT usn FROM students s WHERE LOWER(COALESCE(district,''))=%s",
            [self.district.lower()])))
        self.assertEqual(
            act3, exp3,
            f"'paid all fees' with a district filter returned {act3[:6]} instead of "
            f"{exp3[:6]} (http={resp3.get('_http_error')})")

    # ── 14. numeric filter on a text-typed column ────────────────────────────
    def test_distance_filter_on_varchar_column(self):
        exp = truth_usns("SELECT usn FROM students s WHERE "
                         "CAST(NULLIF(TRIM(s.distance_from_college),'') AS DECIMAL(8,2)) > 50")
        for phrasing in ("show students who live more than 50 km from college",
                         f"list students from {self.district} district living above 50 km away"):
            if "district" in phrasing:
                act, resp = run(phrasing)
                self.assertTrue(set(act) <= set(exp),
                                f"{phrasing!r} returned students closer than 50 km "
                                f"(http={resp.get('_http_error')})")
            else:
                act, resp = run(phrasing)
                self.assertEqual(act, exp,
                                 f"{phrasing!r}: distance truth is {len(exp)} rows, got "
                                 f"{len(act)} (http={resp.get('_http_error')})")

    # ── 15. a spelled-out department is a branch, never a place ──────────────
    def test_full_department_name_with_companion_filter(self):
        # "student in Electronics and Communication Engineering" used to split on
        # "and" and add LIKE '%communication engineering%' over the address blob,
        # answering a whole department with zero rows. With a companion filter the
        # answer must be the intersection, not the department and not the district.
        for code, words in [("EC", "Electronics and Communication Engineering"),
                            ("CV", "Civil Engineering"),
                            ("CS", "Computer Science and Engineering")]:
            exp_branch = branch_truth(code)
            if not exp_branch:
                continue
            act, resp = run(f"student in {words}")
            self.assertEqual(
                act, exp_branch,
                f"'student in {words}': {code} truth is {len(exp_branch)} students, got "
                f"{len(act)} (http={resp.get('_http_error')}) — the department name was "
                f"likely compiled into an address filter")

            exp_district = truth_usns(
                "SELECT usn FROM students s WHERE LOWER(COALESCE(district,''))=%s",
                [self.district.lower()])
            expected = sorted(set(exp_branch) & set(exp_district))
            act2, resp2 = run(f"list students from {self.district} district studying {words}")
            self.assertEqual(
                act2, expected,
                f"district + {words}: expected the {len(expected)} {code} students of "
                f"{self.district!r}, got {len(act2)} (http={resp2.get('_http_error')}); "
                f"extra={sorted(set(act2) - set(expected))[:6]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
