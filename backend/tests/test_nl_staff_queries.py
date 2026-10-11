"""
Natural-language correctness for the everyday staff phrasings required by the
second master prompt (sections 1, 4, 5, 7): broken English, very short
conversational queries, and fee / backlog / academic intents.

Expected results are computed *independently* here by hand-written authoritative
SQL run straight against MySQL (never by the NL parser / LLM under test). The
application output is produced by calling generate_query() in-process, which for
these queries is served by the deterministic engine (no LLM dependency). A test
passes only when the app's distinct USN set equals the independently-computed
DB truth.
"""
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

CS_EXPR, _CY = _current_academic_fields_sql("s")
VALID_SEM = f"({CS_EXPR})"
CGPA = ("COALESCE((SELECT AVG(m.sgpa) FROM marks m "
        "WHERE m.usn=s.usn AND m.sgpa IS NOT NULL), s.cgpa)")


def _expected(sql, params=()):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, list(params))
        rows = cur.fetchall()
        cur.close()
    return rows


def _app(q, language="en"):
    resp = generate_query(
        QueryRequest(natural_query=q, language=language,
                     response_language="en", debug=False),
        current_user=ADMIN,
    )
    return resp if isinstance(resp, dict) else {}


def _app_usns(q, language="en"):
    data = _app(q, language).get("data") or []
    return sorted({r.get("usn") for r in data if r.get("usn")})


class StaffPhrasingQueryTests(unittest.TestCase):
    # ── broken English threshold: "cgpa more 8" (no "than") ───────────────────
    def test_cgpa_more_8_broken_english(self):
        exp = _expected(
            f"SELECT s.usn FROM students s WHERE {VALID_SEM}=5 AND {CGPA} > 8")
        act = _app_usns("show 5 sem students cgpa more 8")
        self.assertEqual(act, sorted(r["usn"] for r in exp),
                         "cgpa>8 (broken English) set mismatch")
        # every returned row must actually satisfy the numeric threshold
        for row in (_app("show 5 sem students cgpa more 8").get("data") or []):
            self.assertGreater(float(row["cgpa"]), 8.0, "row cgpa <= 8 leaked")

    # ── fee status: unpaid ────────────────────────────────────────────────────
    def test_who_not_paid_fees(self):
        # DB truth: a student "has not paid" when at least one fee row records no
        # payment at all. "Partially Paid" is a distinct question (own test), and
        # blank / not-applicable statuses mean nothing is owed.
        exp = _expected(
            "SELECT DISTINCT usn FROM student_fees "
            "WHERE LOWER(TRIM(COALESCE(status,''))) IN "
            "('no','not paid','unpaid','pending','due','balance','0')")
        exp_usns = sorted(r["usn"] for r in exp)
        act = _app_usns("who not paid fees")
        self.assertEqual(act, exp_usns, "unpaid fee set mismatch")
        self.assertTrue(len(act) > 0, "unpaid query unexpectedly empty")
        # count phrasing must agree with the list (same validated filter)
        cnt = _app("how many students not paid fees").get("data") or []
        self.assertEqual(int(list(cnt[0].values())[0]), len(exp_usns))

    # ── fee status: partial ───────────────────────────────────────────────────
    def test_partial_fees_paid(self):
        exp = _expected(
            "SELECT DISTINCT usn FROM student_fees WHERE LOWER(status) LIKE '%partial%'")
        exp_usns = sorted(r["usn"] for r in exp)
        act = _app_usns("partial fees paid students list")
        self.assertEqual(act, exp_usns, "partial fee set mismatch")

    # ── fee status: paid (positive) is a distinct, larger set than unpaid ─────
    def test_paid_fees_positive_distinct_from_unpaid(self):
        unpaid = set(_app_usns("who not paid fees"))
        paid = set(_app_usns("students who paid fees"))
        self.assertTrue(len(paid) > len(unpaid),
                        "paid list should be larger than unpaid in this fixture")
        # A student who has fully-paid rows is legitimately also allowed to have
        # an unpaid row; the key invariant is the unpaid query never returns a
        # student whose every fee status is blank / 'Not applicable'.
        blank_only = _expected(
            "SELECT usn FROM student_fees GROUP BY usn "
            "HAVING SUM(CASE WHEN status IS NOT NULL AND TRIM(status) NOT IN "
            "('','none','not applicable') THEN 1 ELSE 0 END) = 0")
        for r in blank_only:
            self.assertNotIn(r["usn"], unpaid,
                             f"{r['usn']} has only blank/NA fees but was returned as unpaid")

    # ── backlog filtered by SUBJECT (was returning all backlog students) ──────
    def test_backlog_by_subject(self):
        exp = _expected(
            "SELECT DISTINCT usn FROM student_backlogs WHERE cleared=0 "
            "AND REPLACE(LOWER(subject),' ','') LIKE '%operatingsystem%'")
        exp_usns = sorted(r["usn"] for r in exp)
        act = _app_usns("who have backlog in operating system")
        self.assertEqual(act, exp_usns, "backlog-by-subject set mismatch")
        # subject filter must narrow the result below the unrestricted set
        all_backlog = _expected(
            "SELECT DISTINCT usn FROM student_backlogs WHERE cleared=0")
        self.assertLessEqual(len(act), len(all_backlog))

    # ── complete profile by USN ───────────────────────────────────────────────
    def test_full_profile_by_usn(self):
        usn = "4HG24CS007"
        exists = _expected("SELECT usn FROM students WHERE UPPER(usn)=%s", [usn])
        self.assertTrue(exists, f"{usn} not present in fixture DB")
        resp = _app(f"student all details USN {usn}")
        data = resp.get("data") or []
        self.assertTrue(any((r.get("usn") or "").upper() == usn for r in data),
                        "requested student absent from profile result")

    # ── multi-condition: rural + hassan district + 5th sem (short broken English)
    def test_rural_hassan_5th_sem(self):
        exp = _expected(
            "SELECT s.usn FROM students s WHERE UPPER(COALESCE(s.area_type,''))='RURAL' "
            f"AND {VALID_SEM}=5 AND LOWER(COALESCE(s.district,'')) LIKE '%hassan%'")
        act = _app_usns("rural student hassan district 5 sem")
        self.assertEqual(act, sorted(r["usn"] for r in exp),
                         "rural+hassan+5th set mismatch")


class DemographicFilterTests(unittest.TestCase):
    """Religion / caste / category / gender and per-semester SGPA-vs-CGPA.
    Each expected set is computed independently in SQL (never via the NL parser)."""

    def _set(self, q):
        return set(_app_usns(q))

    def test_religion_muslim_with_semester(self):
        exp = _expected(
            f"SELECT s.usn FROM students s WHERE "
            f"(LOWER(s.religion) LIKE '%muslim%' OR LOWER(s.religion) LIKE '%islam%') "
            f"AND {VALID_SEM}=7")
        self.assertEqual(self._set("list the muslim students in 7th sem"),
                         {r["usn"] for r in exp}, "muslim+7th set mismatch")

    def test_religion_typo_and_bare(self):
        # "relegion" misspelling + bare "hindu" must match stored Hindu AND Hindhu.
        exp = _expected(
            "SELECT usn FROM students WHERE LOWER(religion) LIKE '%hindu%' "
            "OR LOWER(religion) LIKE '%hindhu%'")
        self.assertEqual(self._set("list hindu relegion students"),
                         {r["usn"] for r in exp}, "hindu (typo) set mismatch")

    def test_caste(self):
        exp = _expected(
            "SELECT usn FROM students WHERE LOWER(CONCAT_WS(' ', "
            "COALESCE(caste,''), COALESCE(sub_caste,''))) LIKE '%vokkaliga%'")
        self.assertEqual(self._set("list vokkaliga caste students"),
                         {r["usn"] for r in exp}, "vokkaliga caste set mismatch")

    def test_category(self):
        exp = _expected(
            "SELECT usn FROM students WHERE LOWER(TRIM(COALESCE(category,''))) LIKE '%2a%'")
        self.assertEqual(self._set("list 2a category students"),
                         {r["usn"] for r in exp}, "2A category set mismatch")

    def test_girls_synonym_with_semester(self):
        exp = _expected(
            f"SELECT s.usn FROM students s WHERE UPPER(s.gender)='FEMALE' AND {VALID_SEM}=7")
        self.assertEqual(self._set("list girls in 7th sem"),
                         {r["usn"] for r in exp}, "girls+7th set mismatch")

    def test_quota_value_before_keyword(self):
        exp = _expected("SELECT usn FROM students WHERE LOWER(quota) LIKE '%defence%'")
        self.assertEqual(self._set("list defence quota students"),
                         {r["usn"] for r in exp}, "defence quota set mismatch")

    def test_per_sem_sgpa_distinct_from_cumulative_cgpa(self):
        # A per-semester SGPA ranking must show the true cumulative CGPA, which is
        # a DIFFERENT number than the single-semester SGPA (the reported bug).
        data = _app("top 10 students 3rd sem sgpa wise 2023 batch").get("data") or []
        self.assertTrue(data, "no rows for 3rd-sem SGPA ranking")
        for row in data:
            self.assertIsNotNone(row.get("sgpa"), "sgpa missing")
            self.assertIsNotNone(row.get("cgpa"), "cgpa missing")
        # sgpa is the 3rd-semester marks value; cgpa is AVG over ALL semesters.
        sample = data[0]["usn"]
        sem3 = _expected(
            "SELECT sgpa FROM marks WHERE usn=%s AND semester=3", [sample])
        cum = _expected(
            "SELECT ROUND(AVG(sgpa),2) cgpa FROM marks WHERE usn=%s AND sgpa IS NOT NULL",
            [sample])
        self.assertAlmostEqual(float(data[0]["sgpa"]), float(sem3[0]["sgpa"]), places=2)
        self.assertAlmostEqual(float(data[0]["cgpa"]), float(cum[0]["cgpa"]), places=2)


class RankingToleranceTests(unittest.TestCase):
    """Non-technical staff type the metric phonetically and use whatever
    preposition comes to hand. 'top 5 students in capa' must behave exactly like
    'top 5 students by cgpa' — not return zero rows (the misspelt word becoming a
    location filter) and not return the wrong rows (no ORDER BY applied at all)."""

    VARIANTS = [
        "top 5 students by cgpa",
        "top 5 students in cgpa",
        "top 5 students by capa",
        "top 5 students in capa",
        "top 5 students capa",
        "top 5 students by cpga",
        "show top 5 students by cgpa",
    ]

    def test_metric_typos_rank_by_db_truth(self):
        exp = [r["usn"] for r in _expected(
            f"SELECT s.usn FROM students s WHERE {CGPA} IS NOT NULL "
            f"ORDER BY {CGPA} DESC, s.usn LIMIT 5")]
        self.assertTrue(exp, "no ranked students in DB")
        for q in self.VARIANTS:
            with self.subTest(query=q):
                resp = _app(q)
                data = resp.get("data") or []
                self.assertEqual([r["usn"] for r in data], exp,
                                 f"{q!r} did not rank by CGPA as stored in DB")
                self.assertNotIn("location", str(resp.get("ast") or {}),
                                 f"{q!r} leaked the metric into a location filter")

    def test_ranked_rows_are_descending_and_have_cgpa(self):
        data = _app("top 5 students in capa").get("data") or []
        self.assertTrue(data, "typo'd ranking returned no rows")
        vals = [float(r["cgpa"]) for r in data]
        self.assertEqual(vals, sorted(vals, reverse=True), "not descending")
        for r in data:
            self.assertIsNotNone(r.get("cgpa"), "cgpa not projected for a CGPA ranking")

    def test_bottom_ranking_uses_asc(self):
        exp = [r["usn"] for r in _expected(
            f"SELECT s.usn FROM students s WHERE {CGPA} IS NOT NULL "
            f"ORDER BY {CGPA} ASC, s.usn LIMIT 5")]
        act = _app_usns("bottom 5 students by capa")
        self.assertEqual(act, sorted(exp), "bottom-N typo'd ranking mismatch")

    def test_name_and_place_values_are_not_rewritten(self):
        # The repairer must not touch a value that merely resembles an
        # abbreviation, or a real student/place search would break.
        from routes_query import _fix_metric_typos
        for q in ["top 5 students named capra", "top 10 students in hasan",
                  "list of students from cse branch", "top 5 students by marks"]:
            with self.subTest(query=q):
                self.assertEqual(_fix_metric_typos(q), q)


if __name__ == "__main__":
    unittest.main(verbosity=2)
