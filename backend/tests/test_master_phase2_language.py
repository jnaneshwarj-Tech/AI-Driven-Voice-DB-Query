"""Master QA Phase 2 — search and language understanding.

Every phrasing is pushed through the real query route and the returned student
set is compared against expected rows computed straight from MySQL, so the
parser cannot grade its own homework. Coverage follows the brief: case,
misspelling, glued and extra spaces, punctuation, word order, singular/plural,
synonyms, college abbreviations and column aliases, Kannada (Unicode, romanised
and mixed), names, USNs, counts, rankings, projections and long multi-filter
requests — plus the requests that must *not* be answered.

Run against the isolated staging database:
    MYSQL_DB=student_db_staging ./.venv/Scripts/python.exe -m unittest \
        tests.test_master_phase2_language
"""
import os
import re
import sys
import unittest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from fastapi import HTTPException

from database import db_conn
from routes_query import QueryRequest, generate_query, suggest_students, _current_academic_fields_sql

ADMIN = {"username": "qa_admin", "role": "Admin"}
CS_EXPR, _CY = _current_academic_fields_sql("s")
VALID_SEM = f"({CS_EXPR})"
CGPA = ("ROUND(COALESCE((SELECT AVG(m.sgpa) FROM marks m WHERE m.usn=s.usn "
        "AND m.sgpa IS NOT NULL), s.cgpa), 2)")


def sql_rows(query, params=()):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(query, list(params))
        rows = cur.fetchall()
        cur.close()
    return rows


def truth_usns(query, params=()):
    return sorted({r["usn"] for r in sql_rows(query, params) if r.get("usn")})


def run(query, user=ADMIN, language="english"):
    """Return (usn set, response). A safe clarification comes back as an empty
    set with `_http_error` set, which callers can assert on."""
    req = QueryRequest(natural_query=query, language=language,
                       response_language="en", debug=False)
    try:
        resp = generate_query(req, current_user=user) or {}
    except HTTPException as exc:
        resp = {"_http_error": exc.status_code, "_detail": exc.detail}
    usns = sorted({(r.get("usn") or "").upper() for r in (resp.get("data") or [])
                   if r.get("usn")})
    return usns, resp


def pick_value(table, column, exclude=("", None)):
    """Most common real value of a column — the fixtures stay portable while the
    literals under test remain concrete."""
    rows = sql_rows(f"SELECT `{column}` AS v, COUNT(*) AS n FROM `{table}` "
                    f"WHERE `{column}` IS NOT NULL AND TRIM(`{column}`)<>'' "
                    f"GROUP BY `{column}` ORDER BY n DESC LIMIT 12")
    for r in rows:
        if r["v"] not in exclude:
            return r["v"]
    raise AssertionError(f"no usable value for {table}.{column}")


# What "the CS students" means, written independently of the app: the college's
# own sheets type the department any way they like, so the authoritative branch
# is the VTU code carried in the USN, with the typed text used when present.
BRANCH_ALIASES = {
    "CS": {"CS", "CSE", "COMPUTER SCIENCE", "COMPUTER SCIENCE AND ENGINEERING"},
    "CV": {"CV", "CIV", "CE", "CIVIL", "CIVIL ENGINEERING"},
    "EC": {"EC", "ECE", "ELECTRONICS", "ELECTRONICS AND COMMUNICATION ENGINEERING"},
    "IS": {"IS", "ISE", "INFORMATION SCIENCE",
           "INFORMATION SCIENCE AND ENGINEERING"},
    "ME": {"ME", "MECH", "MECHANICAL", "MECHANICAL ENGINEERING"},
}


def canonical_branch(usn, typed):
    text = str(typed or "").strip().upper()
    for code, aliases in BRANCH_ALIASES.items():
        if text in aliases:
            return code
    match = re.match(r"^\d[A-Z]{2,3}\d{2}([A-Z]{2,4})", str(usn or "").strip().upper())
    return match.group(1) if match else ""


def branch_students(code):
    rows = sql_rows("SELECT usn, branch FROM students")
    return sorted({r["usn"].upper() for r in rows
                   if canonical_branch(r["usn"], r["branch"]) == code})


class Phase2LanguageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.district = pick_value("students", "district")
        cls.village = pick_value("students", "village")
        cls.occupation = pick_value("students", "father_occupation")
        cls.name = sql_rows("SELECT name FROM students WHERE name IS NOT NULL "
                            "AND name<>'' ORDER BY usn LIMIT 1")[0]["name"]
        cls.usn = sql_rows("SELECT usn FROM students ORDER BY usn LIMIT 1")[0]["usn"]
        counts = {code: len(branch_students(code)) for code in BRANCH_ALIASES}
        cls.branch = max(counts, key=lambda c: (counts[c], c))
        # A second, differently spelled name for the same department, so an alias
        # is exercised as well as the code itself.
        cls.branch_alias = next(
            (r["v"] for r in sql_rows(
                "SELECT branch AS v, COUNT(*) n FROM students WHERE TRIM(COALESCE(branch,''))<>'' "
                "GROUP BY branch ORDER BY n DESC")
             if canonical_branch("1XX00XX000", r["v"]) == cls.branch
             and r["v"].upper() != cls.branch), cls.branch)

    # ── helpers ──────────────────────────────────────────────────────────────
    def assert_query(self, phrasing, truth_sql, params=(), msg=""):
        exp = truth_usns(truth_sql, params)
        act, resp = run(phrasing)
        self.assertEqual(
            act, exp,
            f"{msg or phrasing!r}: expected {len(exp)} rows, got {len(act)}. "
            f"extra={sorted(set(act) - set(exp))[:5]} "
            f"missing={sorted(set(exp) - set(act))[:5]} "
            f"http={resp.get('_http_error')}")
        return exp, act

    # ── 1. case, spacing and punctuation of correct English ──────────────────
    def test_case_space_and_punctuation_variants(self):
        d = self.district
        base = f"students from {d} district"
        truth = f"SELECT usn FROM students WHERE LOWER(COALESCE(district,''))=%s"
        params = [d.lower()]
        variants = [
            base.upper(),
            base.title(),
            f"  {base}  ",
            base.replace(" ", "  "),
            f"{base}.",
            f"{base}?",
            f"{base}!!",
        ]
        for v in variants:
            self.assert_query(v, truth, params, f"variant {v!r}")

    # ── 2. misspellings: a typo is a parser bug, never a request to rephrase ─
    def test_misspellings_still_find_the_same_students(self):
        d = self.district
        real = [r["v"] for r in sql_rows(
            "SELECT DISTINCT district AS v FROM students "
            "WHERE district IS NOT NULL AND TRIM(district)<>''")]
        by_set = {tuple(truth_usns(
            "SELECT usn FROM students WHERE LOWER(COALESCE(district,''))=%s",
            [v.lower()])): v for v in real}
        for word in [d[:-2], d.replace("a", ""), f"{d}dd", f"{d[:3]} {d[3:]}"]:
            if len(word) < 4:
                continue
            act, resp = run(f"show students of {word} district")
            self.assertTrue(act, f"misspelled district {word!r} found nobody "
                                 f"(http={resp.get('_http_error')})")
            self.assertIn(
                tuple(act), by_set,
                f"{word!r} returned {len(act)} students, which is not the whole "
                f"student list of any real district — the typo was guessed at "
                f"rather than resolved")

    # ── 3. singular / plural and synonyms ────────────────────────────────────
    def test_singular_plural_and_synonyms(self):
        truth = branch_students(self.branch)
        self.assertTrue(truth, "staging seed has no students of branch "
                        + self.branch)
        for v in [f"{self.branch} students", f"student in {self.branch}",
                  f"list {self.branch} branch students",
                  f"students studying {self.branch}", f"show {self.branch} class",
                  f"{self.branch_alias} students",
                  f"list all {self.branch_alias} students"]:
            act, resp = run(v)
            self.assertEqual(act, truth,
                             f"branch phrasing {v!r} mismatch "
                             f"(http={resp.get('_http_error')})")

    # ── 4. names and USNs ────────────────────────────────────────────────────
    def test_search_by_name_and_by_usn(self):
        act, _ = run(f"show details of student {self.usn}")
        self.assertEqual(act, [self.usn.upper()], "USN lookup returned the wrong student")

        act, resp = run(f"find {self.name}")
        exp = truth_usns("SELECT usn FROM students WHERE name=%s", [self.name])
        self.assertEqual(act, sorted(x.upper() for x in exp),
                         f"name search {self.name!r} mismatch "
                         f"(http={resp.get('_http_error')})")

    # ── 5. college terminology and column aliases ────────────────────────────
    def test_aliases_and_college_terminology(self):
        self.assert_query(
            "students having arrears",
            "SELECT DISTINCT sb.usn FROM student_backlogs sb JOIN students s "
            "ON s.usn=sb.usn WHERE sb.cleared=0")
        self.assert_query(
            "students with backlog subjects",
            "SELECT DISTINCT sb.usn FROM student_backlogs sb JOIN students s "
            "ON s.usn=sb.usn WHERE sb.cleared=0")
        self.assert_query(
            "students whose father's occupation is "
            f"{self.occupation}",
            "SELECT usn FROM students WHERE LOWER(COALESCE(father_occupation,''))=%s",
            [self.occupation.lower()])

    # ── 6. counts, rankings and projections ──────────────────────────────────
    def test_count_ranking_and_projection(self):
        total = sql_rows("SELECT COUNT(*) AS n FROM students")[0]["n"]
        _, resp = run("how many students are there")
        rows = resp.get("data") or []
        self.assertTrue(rows, "count query returned no rows")
        self.assertEqual(int(list(rows[0].values())[0]), total,
                         f"count said {rows[0]} but the table holds {total}")

        _, resp = run("top 5 students by cgpa")
        rows = resp.get("data") or []
        self.assertLessEqual(len(rows), 5, "ranking ignored the limit")
        given = [float(r["cgpa"]) for r in rows if r.get("cgpa") is not None]
        self.assertEqual(given, sorted(given, reverse=True),
                         f"ranking is not descending: {given}")
        exp = truth_usns(f"SELECT usn, {CGPA} AS c FROM students s ORDER BY c DESC LIMIT 5")
        self.assertEqual(sorted({r["usn"] for r in rows if r.get("usn")}),
                         sorted(exp), "top-5 set differs from DB truth")

    # ── 7. long queries with several filters ─────────────────────────────────
    def test_multi_filter_query_keeps_every_filter(self):
        d = self.district
        query = (f"show active {self.branch} students in semester 6 with cgpa above 7.0 "
                 f"from {d} district having zero backlogs sorted by cgpa")
        branch_usns = branch_students(self.branch)
        placeholders = ",".join(["%s"] * len(branch_usns))
        exp = truth_usns(
            f"SELECT s.usn FROM students s WHERE s.usn IN ({placeholders}) "
            f"AND {VALID_SEM}=6 AND {CGPA} > 7.0 AND LOWER(COALESCE(s.district,''))=%s "
            f"AND NOT EXISTS (SELECT 1 FROM student_backlogs b "
            f"WHERE b.usn=s.usn AND b.cleared=0)",
            branch_usns + [d.lower()])
        act, resp = run(query)
        self.assertEqual(act, sorted(x.upper() for x in exp),
                         f"multi-filter query mismatch (http={resp.get('_http_error')})")

    # ── 8. Kannada: Unicode, romanised and mixed ─────────────────────────────
    def test_kannada_unicode_and_romanised(self):
        kannada = [r["name"] for r in sql_rows("SELECT name FROM students")
                   if re.search(r"[\u0C80-\u0CFF]", r["name"] or "")]
        self.assertTrue(kannada, "staging seed has no Kannada-script student name")
        for nm in kannada[:3]:
            exp = sorted(x.upper() for x in
                         truth_usns("SELECT usn FROM students WHERE name=%s", [nm]))
            for phrasing, lang in [(f"{nm} ಅವರ ವಿವರಗಳು ತೋರಿಸಿ", "kannada"),
                                   (f"{nm} ವಿವರ ಬೇಕು", "kannada"),
                                   (f"show details of {nm}", "mixed")]:
                act, resp = run(phrasing, language=lang)
                self.assertEqual(act, exp,
                                 f"{lang} request {phrasing!r} did not find "
                                 f"student(s) of {nm!r} "
                                 f"(http={resp.get('_http_error')})")

        latin = sql_rows("SELECT name FROM students WHERE name REGEXP '^[A-Za-z]' "
                         "ORDER BY name LIMIT 1")
        self.assertTrue(latin, "staging seed has no Latin-script student name")
        nm = latin[0]["name"]
        exp = sorted(x.upper() for x in
                     truth_usns("SELECT usn FROM students WHERE name=%s", [nm]))
        for phrasing in [f"{nm} avara vivara torisi",
                         f"{nm} details kodu",
                         f"{nm} sampoorna mahiti beku"]:
            act, resp = run(phrasing)
            self.assertEqual(act, exp,
                             f"romanised request {phrasing!r} mismatch "
                             f"(http={resp.get('_http_error')})")

        act, resp = run(f"{nm} ವಿವರಗಳು ತೋರಿಸಿ", language="mixed")
        self.assertEqual(act, exp,
                         f"mixed-script request for {nm!r} mismatch "
                         f"(http={resp.get('_http_error')})")

    # ── 9. unavailable data and ambiguity must be handled honestly ───────────
    def test_unsupported_field_and_ambiguity_do_not_fabricate(self):
        for phrase in ["students whose grandfather was a freedom fighter",
                       "students with the highest attendance percentage"]:
            act, resp = run(phrase)
            if resp.get("_http_error"):
                self.assertIn(resp["_http_error"], (400, 404))
            else:
                total = sql_rows("SELECT COUNT(*) AS n FROM students")[0]["n"]
                self.assertLess(len(act), total,
                                f"{phrase!r} answered with the whole table")

    # ── 11. branch spellings must never leak into an address filter ───────────
    def test_branch_spelling_is_not_read_as_a_place(self):
        # "student in CIV" used to add LIKE '%civ%' over address/village/taluk on
        # top of the branch filter, answering a whole department with zero rows.
        for code, spellings in [
            (self.branch, [self.branch, self.branch_alias]),
            ("CV", ["CV", "CIV", "CIVIL", "CIVIL ENGINEERING"]),
            ("ME", ["ME", "MECH", "MECHANICAL"]),
            ("IS", ["IS", "ISE", "INFORMATION SCIENCE"]),
            ("EC", ["EC", "ECE", "ELECTRONICS"]),
            ("CS", ["CS", "CSE", "COMPUTER SCIENCE"]),
        ]:
            exp = branch_students(code)
            if not exp:
                continue
            for word in spellings:
                for phrasing in [f"{word} students", f"student in {word}",
                                 f"students studying {word}",
                                 f"list {word} branch students"]:
                    act, resp = run(phrasing)
                    self.assertEqual(
                        act, exp,
                        f"{phrasing!r} returned {len(act)} of {len(exp)} {code} "
                        f"students (http={resp.get('_http_error')})")

    # ── 12. "<value> students": the word names a column, not a person ────────
    def test_value_led_group_phrasings(self):
        cases = [
            (self.village, "village", "taluk", "district"),
            (pick_value("students", "caste"), "caste", "sub_caste", "category"),
            (self.occupation, "father_occupation", "mother_occupation"),
            (self.district, "district", "village", "taluk"),
        ]
        for value, *columns in cases:
            conds = " OR ".join(f"LOWER(COALESCE(`{c}`,''))=%s" for c in columns)
            truth = truth_usns(f"SELECT usn FROM students WHERE {conds}",
                               [value.lower()] * len(columns))
            if not truth:
                continue
            for phrasing in [f"{value} students",
                             f"show details of {value} students",
                             f"list all {value} students"]:
                act, resp = run(phrasing)
                self.assertEqual(
                    act, sorted(t.upper() for t in truth),
                    f"{phrasing!r} should list the students whose "
                    f"{'/'.join(columns)} is {value!r} "
                    f"(http={resp.get('_http_error')})")

    # ── 13. verb-final romanised Kannada is a name lookup, not a filter ───────
    def test_verb_final_kannada_lookups(self):
        names = [r["name"] for r in sql_rows(
                "SELECT name FROM students WHERE name REGEXP '^[A-Za-z]' "
                "ORDER BY name LIMIT 3")]
        # Staff also type the Kannada-script name with romanised request words
        # ("ಲಕ್ಷ್ಮೀ ದೇವಿ avara vivara torisi"), so a non-Latin name is covered.
        names += [r["name"] for r in sql_rows(
                "SELECT name FROM students WHERE name REGEXP '^[^A-Za-z0-9]' "
                "ORDER BY name LIMIT 2")]
        for nm in names:
            exp = sorted(x.upper() for x in
                         truth_usns("SELECT usn FROM students WHERE name=%s", [nm]))
            for phrasing, lang in [
                    (f"{nm} avara vivara torisi", "english"),
                    (f"{nm} details kodu", "english"),
                    (f"{nm} sampoorna mahiti beku", "english"),
                    (f"{nm} ಅವರ vivara torisi", "mixed"),
                    (f"{nm} ವಿವರಗಳು ತೋರಿಸಿ", "mixed"),
                    (f"{nm} ಅವರ ವಿವರಗಳು ತೋರಿಸಿ", "kannada")]:
                act, resp = run(phrasing, language=lang)
                self.assertEqual(act, exp,
                                 f"{lang} {phrasing!r} did not find {nm!r} "
                                 f"(http={resp.get('_http_error')})")

    # ── 14. a typo is only "resolved" when it lands on a real value ───────────
    def test_typo_resolution_never_widens_the_answer(self):
        total = sql_rows("SELECT COUNT(*) AS n FROM students")[0]["n"]
        d = self.district
        exp = truth_usns("SELECT usn FROM students "
                         "WHERE LOWER(COALESCE(district,''))=%s", [d.lower()])
        for phrasing in [f"show students of {d[:-2]} district",
                         f"show students of {d}dd district",
                         f"show students of {d[:3]} {d[3:]} district",
                         f"show students in {d[:-1]} district"]:
            act, resp = run(phrasing)
            self.assertEqual(
                len(act), len(exp),
                f"{phrasing!r} returned {len(act)} students instead of the "
                f"{len(exp)} of {d!r} (http={resp.get('_http_error')})")
            self.assertLess(len(act), total,
                            f"{phrasing!r} answered with the whole table")

    # ── 15. autocomplete never mistakes a request word for a name ────────────
    def test_live_suggestions_ignore_kannada_request_words(self):
        for term in ["torisi", "vivara", "avara", "beku", "ತೋರಿಸಿ", "ವಿವರ", "ಅವರ"]:
            self.assertEqual(suggest_students(term, current_user=ADMIN), [],
                             f"{term!r} is a request word, not a student name")
        # A real name fragment must still suggest students.
        first = self.name.split()[0]
        self.assertTrue(suggest_students(first, current_user=ADMIN),
                        f"no suggestions for the name fragment {first!r}")

    # ── 16. pagination: later pages are the same truth set ───────────────────
    def test_all_pages_reach_every_matching_student(self):
        d = self.district
        exp = truth_usns("SELECT usn FROM students WHERE LOWER(COALESCE(district,''))=%s",
                         [d.lower()])
        act, resp = run(f"list all students from {d} district")
        self.assertEqual(len(exp), len(act),
                         f"{d}: expected {len(exp)} students, page returned {len(act)} "
                         f"— later rows were silently truncated")


if __name__ == "__main__":
    unittest.main(verbosity=2)
