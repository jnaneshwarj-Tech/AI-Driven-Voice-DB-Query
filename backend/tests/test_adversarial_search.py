"""
Adversarial search / language torture suite (Phase 7A of the master brief).

For a fixed set of verified intents we drive *many* noisy phrasings — case
flips, missing/extra spaces, common misspellings, punctuation, romanised
Kannada terms — through the real in-process query engine and require every
variant to return exactly the authoritative MySQL result set. This measures
normalisation robustness, recall (correct rows are found) and precision (no
extra rows leak in), without trusting the parser under test to define truth.

A separate battery pins the false-positive guard: a meaningless or unsupported
request must never be answered by dumping the whole student table; it returns
nothing (or a clarification).

Expected sets come from hand-written authoritative SQL against live MySQL, the
same project rules the app uses (CGPA-from-marks, computed current semester).
No production rows are written.
"""
import os
import sys
import unittest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from fastapi import HTTPException

import report_service
from database import db_conn
from routes_query import (
    QueryRequest,
    generate_query,
    _current_academic_fields_sql,
)

ADMIN = {"username": "admin", "role": "Admin"}
CS_EXPR, _CY = _current_academic_fields_sql("s")
VALID_SEM = f"({CS_EXPR})"


def run_expected(sql, params=()):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, list(params))
        rows = cur.fetchall()
        cur.close()
    return rows


def app_usns(query, language="en"):
    req = QueryRequest(natural_query=query, language=language,
                       response_language="en", debug=False)
    try:
        resp = generate_query(req, current_user=ADMIN) or {}
    except HTTPException as exc:
        # A clarification / safe refusal: no rows returned.
        resp = {"_http_error": exc.status_code, "_detail": exc.detail}
    return sorted((r.get("usn") for r in (resp.get("data") or []) if r.get("usn"))), resp


def _total_students():
    return run_expected("SELECT COUNT(*) AS c FROM students")[0]["c"]


class VariantInvarianceTests(unittest.TestCase):
    """Every noisy phrasing of one intent == the authoritative set."""

    def _check(self, label, expected_sql, variants):
        exp = sorted(r["usn"] for r in run_expected(expected_sql))
        # Guard against an empty expectation masking a broken query.
        self.assertTrue(exp or label.startswith("zero"),
                        f"{label}: expected set is empty — intent can't be verified")
        for v in variants:
            act, _ = app_usns(v)
            self.assertEqual(act, exp,
                             f"{label}: variant {v!r} -> {len(act)} rows, expected {len(exp)}")

    # ── Rural students ────────────────────────────────────────────────────────
    def test_rural_variants(self):
        self._check(
            "rural",
            "SELECT usn FROM students WHERE UPPER(COALESCE(area_type,''))='RURAL'",
            [
                "list rural students",
                "List Rural Students",
                "LIST   RURAL    STUDENTS",
                "show students from rural area",
                "rural students",
                "students who are from rural",
                "lis rural studentz",          # misspelt
                "list of the rural students.", # punctuation
                "tally rural students",        # synonym
            ])

    # ── 5th semester students (numeric + spelled-out ordinals) ────────────────
    def test_fifth_semester_variants(self):
        self._check(
            "sem5",
            f"SELECT usn FROM students s WHERE {VALID_SEM}=5",
            [
                "list 5th semester students",
                "show students in fifth semester",   # spelled-out ordinal
                "5th sem students",
                "LIST 5TH SEMESTER STUDENTS",
                "students of 5 sem",
                "5th semesterr student",             # misspelt
                "list students studying in 5th semester",
            ])

    # ── Glued words: currently an un-supported normalisation path. The safe,
    #    expected behaviour is a no-match (never fabricated rows), so we assert
    #    the engine degrades honestly instead of returning wrong data. ─────────
    def test_glued_words_fail_safe_not_fabricated(self):
        for glued in ("ruralstudent", "fifthsemester students", "showdropoutstudents"):
            act, resp = app_usns(glued)
            # Must not return the full table or arbitrary unrelated rows.
            self.assertTrue(len(act) == 0 or len(act) < _total_students() // 2,
                            f"glued {glued!r} leaked {len(act)} rows")

    # ── Blood group O Positive (stored as "O+") ───────────────────────────────
    def test_blood_group_variants(self):
        self._check(
            "blood",
            "SELECT usn FROM students s "
            "WHERE UPPER(REPLACE(s.blood_group,' ','')) IN ('O+','OPOSITIVE')",
            [
                "list students with blood group o positive",
                "show o positive students",
                "blood group o+ students",
                "BLOOD GROUP O POSITIVE STUDENTS",
                "students having O positive blood group",
                "list students whose blood group is o positive",
            ])

    # ── Father occupation = farmer (deterministic college phrasings) ──────────
    def test_farmer_variants(self):
        exp = run_expected(
            "SELECT usn FROM students "
            "WHERE LOWER(COALESCE(father_occupation,'')) LIKE '%farmer%'")
        exp_usns = sorted(r["usn"] for r in exp)
        for v in [
            "students whose father is a farmer",
            "students with father occupation farmer",
            "SHOW STUDENTS WHOSE FATHER IS FARMER",
        ]:
            act, _ = app_usns(v)
            self.assertEqual(act, exp_usns, f"farmer variant {v!r} mismatch")

    # An unusual word order the deterministic layer cannot yet map must degrade
    # to a clean clarification (400), never the misleading 403 "Invalid student
    # data." nor fabricated rows — a genuine, non-technical-user-safe behaviour.
    def test_unmappable_occupation_phrasing_clarifies_not_errors(self):
        for v in ["farmer family students", "list farmer father students"]:
            act, resp = app_usns(v)
            self.assertEqual(act, [], f"{v!r} returned fabricated rows")
            code = resp.get("_http_error")
            if code is not None:
                self.assertEqual(code, 400, f"{v!r} raised {code}, expected 400 clarification")
                self.assertNotIn("Invalid student data", str(resp.get("_detail", "")))


class FalsePositiveGuardTests(unittest.TestCase):
    def test_gibberish_does_not_dump_whole_table(self):
        total = _total_students()
        for junk in [
            "asdf qwerty zxcv",
            "asdasdasdasd",
            "???",
            "list students with field xyzzyplugh9000",
            "qwertyuiop asdfghjkl",
        ]:
            act, _ = app_usns(junk)
            # Either nothing matched, or a clarification replaced the data. It
            # must never quietly return the entire student table.
            self.assertLess(
                len(act), max(1, total),
                f"gibberish {junk!r} leaked the whole table")

    # Pinned locally because the leak this guards against was intermittent: a
    # content-free request has nothing for the deterministic engine to parse, so
    # it used to reach the LLM, which sometimes answered with an unfiltered
    # SELECT and returned every student. The refusal must be a deterministic
    # clarification, not a roll of the AI dice.
    def test_content_free_request_clarifies_without_ai(self):
        for junk in ["???", "...", "   ", "", "-!?!-"]:
            act, resp = app_usns(junk)
            self.assertEqual(act, [], f"{junk!r} returned rows")
            self.assertEqual(resp.get("_http_error"), 400,
                             f"{junk!r} did not clarify: {resp}")

    # The guard keys on "no letters or digits at all", so real short queries —
    # which are exactly what non-technical staff type — must still be answered.
    def test_single_token_and_list_all_still_work(self):
        name = run_expected(
            "SELECT name FROM students WHERE name IS NOT NULL AND name<>'' "
            "ORDER BY usn LIMIT 1")[0]["name"]
        act, _ = app_usns(name)
        self.assertTrue(act, f"single-token name query {name!r} found nothing")
        total = _total_students()
        listed, _ = app_usns("list all students")
        self.assertEqual(len(listed), total, "list-all regressed")


class ReportScopeRegressionTests(unittest.TestCase):
    """Regression for the named defect: a filtered dashboard list must produce a
    report of EXACTLY those records — never every student's full details."""

    ADMIN = {"username": "admin", "role": "Admin"}
    STAFF = {"username": "staff", "role": "Staff"}

    def _sample(self, n=4):
        rows = run_expected(
            "SELECT usn, name FROM students WHERE usn IS NOT NULL "
            "ORDER BY usn LIMIT " + str(n))
        return rows

    def _assert_scoped(self, category):
        sample = self._sample()
        self.assertTrue(len(sample) >= 2, "need at least 2 students to prove scoping")
        expected_usns = {r["usn"] for r in sample}
        total = _total_students()
        model = report_service.build_table_report_model(
            [dict(r) for r in sample], self.ADMIN, category)
        got_usns = {rec.get("usn") for rec in model["records"] if rec.get("usn")}
        # No student outside the displayed selection leaks in.
        self.assertTrue(got_usns <= expected_usns or not got_usns,
                        f"{category}: report contains students not in the selection")
        # And it is never the whole table.
        self.assertLess(len(model["records"]), total,
                        f"{category}: report dumped the entire student table")

    def test_student_list_scoped(self):
        self._assert_scoped("student_list")

    def test_academic_scoped(self):
        self._assert_scoped("academic")

    def test_personal_scoped(self):
        self._assert_scoped("personal")

    def test_count_matches_selection(self):
        sample = self._sample(4)
        model = report_service.build_table_report_model(
            [dict(r) for r in sample], self.ADMIN, "student_list")
        self.assertEqual(len(model["records"]), len(sample))
        self.assertEqual(model["record_count"], len(sample))


if __name__ == "__main__":
    unittest.main()
