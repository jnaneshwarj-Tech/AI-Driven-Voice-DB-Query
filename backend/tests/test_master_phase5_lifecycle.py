"""Phase 5 — student lifecycle: statuses, transitions, categories, retrieval.

Every expectation here is computed from MySQL in this process (COALESCE over the
derived cache), never from what the application answered, and each test asserts
the register actually contains the student it is claiming to find so a vacuous
pass is loud. Only this file's own 9QQ25CS9xx rows are ever written.

    cd backend && MYSQL_DB=student_db_staging ./.venv/Scripts/python.exe \
        -m unittest tests.test_master_phase5_lifecycle
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import HTTPException

import lifecycle as LC
import routes_lifecycle as RL
import routes_query as RQ
from auth import require_roles
from database import db_conn
from lifecycle import (classify_reason_category, is_transition_allowed,
                       next_actions, normalize_status, parse_lifecycle_command)
from query_security_validator import create_confirmation_token

ADMIN = {"username": "p5_admin", "role": "Admin", "user_id": 1}
STAFF = {"username": "p5_staff", "role": "Staff", "user_id": 2}
VIEWER = {"username": "p5_viewer", "role": "Student", "user_id": 3}
ACTORS = [ADMIN["username"], STAFF["username"], VIEWER["username"]]

# Synthetic rows this file owns. 9QQ25CS9xx keeps them clear of the Phase-4
# (9QQ24CS9xx) fixtures so neither cleanup can wipe the other's evidence.
S_ACT = "9QQ25CS901"
S_TEMP = "9QQ25CS902"
S_REVIEW = "9QQ25CS903"
S_DROP = "9QQ25CS904"
S_REQ = "9QQ25CS905"
S_APPR = "9QQ25CS906"
S_REJOIN = "9QQ25CS907"
S_CANCEL = "9QQ25CS908"
S_OTHER = "9QQ25CS909"
MINE = [S_ACT, S_TEMP, S_REVIEW, S_DROP, S_REQ, S_APPR, S_REJOIN, S_CANCEL, S_OTHER]

# One student per canonical status, so "naming a status must return that status"
# is testable for every status the college tracks.
PLAN = [
    (S_ACT, "P5 Active Kid", LC.STATUS_ACTIVE),
    (S_TEMP, "P5 Temp Kid", LC.STATUS_TEMP_DISCONTINUED),
    (S_REVIEW, "P5 Review Kid", LC.STATUS_DISCONTINUED_REVIEW),
    (S_DROP, "P5 Dropout Kid", LC.STATUS_DROPOUT),
    (S_REQ, "P5 Requested Kid", LC.STATUS_READMISSION_REQUESTED),
    (S_APPR, "P5 Approved Kid", LC.STATUS_READMISSION_APPROVED),
    (S_REJOIN, "P5 Rejoined Kid", LC.STATUS_REJOINED),
    (S_CANCEL, "P5 Cancelled Kid", LC.STATUS_ADMISSION_CANCELLED),
    (S_OTHER, "P5 Other Kid", LC.STATUS_OTHER),
]

# Truth is read the same way the register reads it: the audited cache row when it
# exists, otherwise the student's own status column.
STATUS_EXPR = "COALESCE(ls.current_status, s.lifecycle_status)"
USN_TABLES = ("students", "marks", "student_fees", "student_backlogs",
              "student_history", "student_field_sources", "student_lifecycle_status",
              "student_lifecycle_events", "readmission_requests",
              "student_identity_links")


def rows(sql, params=()):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, list(params))
        out = cur.fetchall()
        cur.close()
    return out


def one(sql, params=()):
    got = rows(sql, params)
    return got[0] if got else None


def write(sql, params=()):
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, list(params))
        conn.commit()
        cur.close()


def status_usns(status):
    """Independent truth for "students currently in this lifecycle status"."""
    return sorted(r["usn"] for r in rows(
        f"SELECT s.usn FROM students s LEFT JOIN student_lifecycle_status ls "
        f"ON ls.usn=s.usn WHERE {STATUS_EXPR} = %s", (status,)))


def family_usns(statuses):
    seen = set()
    for st in statuses:
        seen |= set(status_usns(st))
    return sorted(seen)


def category_usns(category, statuses=None):
    where = "WHERE LOWER(ls.reason_category) = LOWER(%s)"
    params = [category]
    if statuses:
        where += f" AND {STATUS_EXPR} IN ({','.join(['%s'] * len(statuses))})"
        params += list(statuses)
    return sorted(r["usn"] for r in rows(
        f"SELECT ls.usn FROM student_lifecycle_status ls "
        f"LEFT JOIN students s ON s.usn=ls.usn {where}", params))


def answered(built):
    """USNs the lifecycle SQL actually returns."""
    return sorted({r["usn"] for r in rows(built["sql"], built.get("params", []))
                   if r.get("usn")})


def call(fn, *args, **kwargs):
    """Invoke a FastAPI handler in-process; HTTPException comes back as the error."""
    return fn(*args, **kwargs)


def events(usn):
    return rows("SELECT * FROM student_lifecycle_events WHERE usn=%s "
                "ORDER BY created_at ASC, id ASC", (usn,))


def purge(usns):
    ph = ",".join(["%s"] * len(usns))
    for table in USN_TABLES:
        write(f"DELETE FROM {table} WHERE usn IN ({ph})", usns)


def seed():
    """(Re)create this file's students exactly as planned: a students row with the
    target status and no lifecycle cache or history, so every test starts from a
    known state regardless of execution order."""
    purge(MINE)
    for usn, name, status in PLAN:
        write("INSERT INTO students (usn, name, branch, admission_year, current_sem, "
              "student_type, lifecycle_status) VALUES (%s,%s,'CS',2025,5,'Regular',%s) "
              "ON DUPLICATE KEY UPDATE name=VALUES(name), lifecycle_status=VALUES(lifecycle_status)",
              (usn, name, status))


def clear_cache(*queries):
    for q in queries:
        write("DELETE FROM query_cache WHERE user_query=%s", (q,))


class Phase5LifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed()

    def setUp(self):
        seed()

    @classmethod
    def tearDownClass(cls):
        purge(MINE)
        ph = ",".join(["%s"] * len(ACTORS))
        write(f"DELETE FROM global_undo_snapshots WHERE performed_by IN ({ph}) "
              f"OR undone_by IN ({ph})", ACTORS + ACTORS)
        write(f"DELETE FROM audit_log WHERE username IN ({ph})", ACTORS)
        # The query cache is derived, self-invalidating data: dropping it loses nothing.
        write("DELETE FROM query_cache")

    # ── 1. the register's own data integrity ─────────────────────────────────
    def test_every_stored_status_is_canonical(self):
        odd = [r for r in rows("SELECT usn, lifecycle_status FROM students")
               if r["lifecycle_status"] not in LC.LIFECYCLE_STATUSES]
        self.assertEqual(odd, [], f"students.lifecycle_status holds unknown values: {odd[:5]}")
        odd = [r for r in rows("SELECT usn, current_status FROM student_lifecycle_status")
               if r["current_status"] not in LC.LIFECYCLE_STATUSES]
        self.assertEqual(odd, [], f"current_status holds unknown values: {odd[:5]}")

    def test_derived_caches_agree_with_the_authoritative_history(self):
        """History is append-only truth; both caches must match its newest event."""
        latest = {}
        for e in rows("SELECT usn, to_status FROM student_lifecycle_events "
                      "ORDER BY created_at ASC, id ASC"):
            latest[e["usn"]] = e["to_status"]
        self.assertTrue(latest, "the register holds no lifecycle history at all")
        drift = []
        for usn, to_status in latest.items():
            student = one("SELECT lifecycle_status FROM students WHERE usn=%s", (usn,))
            cache = one("SELECT current_status FROM student_lifecycle_status WHERE usn=%s", (usn,))
            if student is None:
                drift.append((usn, "student row missing", to_status))
            elif student["lifecycle_status"] != to_status or \
                    (cache or {}).get("current_status") != to_status:
                drift.append((usn, student["lifecycle_status"],
                              (cache or {}).get("current_status"), to_status))
        self.assertEqual(drift, [], f"lifecycle caches drifted from history: {drift[:5]}")

    def test_status_history_chains_are_unbroken(self):
        by_usn = {}
        for e in rows("SELECT usn, from_status, to_status FROM student_lifecycle_events "
                      "ORDER BY usn, created_at ASC, id ASC"):
            by_usn.setdefault(e["usn"], []).append(e)
        broken = [(u, a["to_status"], b["from_status"])
                  for u, evs in by_usn.items()
                  for a, b in zip(evs, evs[1:]) if a["to_status"] != b["from_status"]]
        self.assertEqual(broken, [],
                         f"events whose from_status is not the previous to_status: {broken[:5]}")

    def test_no_orphan_lifecycle_rows(self):
        for table in ("student_lifecycle_status", "student_lifecycle_events",
                      "readmission_requests"):
            with self.subTest(table=table):
                orphans = [r["usn"] for r in rows(
                    f"SELECT DISTINCT usn FROM {table} WHERE usn NOT IN "
                    "(SELECT usn FROM students)")]
                self.assertEqual(orphans, [], f"{table} references deleted students: {orphans[:5]}")

    # ── 2. the transition matrix itself ──────────────────────────────────────
    def test_offered_actions_are_all_legal_and_canonical(self):
        for status in LC.LIFECYCLE_STATUSES:
            with self.subTest(status=status):
                actions = next_actions(status)
                self.assertTrue(actions, f"no action is offered from {status!r}")
                for action in actions:
                    self.assertIn(action["to_status"], LC.LIFECYCLE_STATUSES,
                                  f"{status} offers a non-canonical target {action}")
                    self.assertTrue(is_transition_allowed(status, action["to_status"]),
                                    f"{status} offers {action} which the checker refuses")

    def test_options_screen_offers_every_status_and_transition(self):
        opts = RL.get_options(current_user=STAFF)
        self.assertEqual(sorted(opts["statuses"]), sorted(LC.LIFECYCLE_STATUSES))
        self.assertEqual(sorted(opts["reason_categories"]), sorted(LC.REASON_CATEGORIES))
        self.assertEqual(sorted(opts["discontinued_statuses"]),
                         sorted(LC.DISCONTINUED_STATUSES))
        for status in LC.LIFECYCLE_STATUSES:
            self.assertIn(status, opts["transitions"], f"{status} has no transition list")

    def test_unknown_status_still_gets_an_escape_route(self):
        actions = next_actions("Never Heard Of")
        self.assertTrue(any(a["to_status"] == LC.STATUS_ACTIVE for a in actions),
                        f"an unrecognised status strands the student: {actions}")

    def test_readmission_cannot_be_skipped_and_graduation_is_terminal(self):
        self.assertFalse(is_transition_allowed(LC.STATUS_DROPOUT, LC.STATUS_REJOINED),
                         "a dropout must request readmission before rejoining")
        self.assertFalse(is_transition_allowed(LC.STATUS_ACTIVE, LC.STATUS_READMISSION_APPROVED),
                         "readmission cannot be approved without a request")
        self.assertFalse(is_transition_allowed(LC.STATUS_GRADUATED, LC.STATUS_DROPOUT),
                         "a graduated student cannot be re-opened as a dropout")
        self.assertTrue(is_transition_allowed(LC.STATUS_GRADUATED, LC.STATUS_ACTIVE),
                        "a wrong Graduated flag must stay correctable")

    def test_normalization_never_guessed_between_two_statuses(self):
        self.assertEqual(normalize_status("  graduated "), LC.STATUS_GRADUATED)
        self.assertEqual(normalize_status("dropout"), LC.STATUS_DROPOUT)
        self.assertIsNone(normalize_status("maybe discontinued maybe dropout"),
                          "an ambiguous label must be refused, not guessed")
        self.assertIsNone(normalize_status("Not A Status"))

    # ── 3. retrieval: naming a status must mean that status ──────────────────
    def test_each_status_is_retrievable_by_its_own_name(self):
        phrases = {
            LC.STATUS_ACTIVE: "show active students",
            LC.STATUS_TEMP_DISCONTINUED: "show temporarily discontinued students",
            LC.STATUS_DISCONTINUED_REVIEW: "show students with status Discontinued-Review Req",
            LC.STATUS_DROPOUT: "show students marked Dropout-College Recorded",
            LC.STATUS_READMISSION_REQUESTED: "show readmission requested students",
            LC.STATUS_READMISSION_APPROVED: "show readmission approved students",
            LC.STATUS_REJOINED: "show rejoined active students",
            LC.STATUS_GRADUATED: "show graduated students",
            LC.STATUS_TRANSFERRED: "show transferred students",
            LC.STATUS_ADMISSION_CANCELLED: "show students whose admission was cancelled",
            LC.STATUS_OTHER: "show students with status other",
        }
        for status, phrase in phrases.items():
            with self.subTest(phrase=phrase):
                want = status_usns(status)
                self.assertTrue(want, f"nothing is {status!r}; {phrase!r} proves nothing")
                built = RQ._build_lifecycle_query(phrase)
                self.assertIsNotNone(built,
                                     f"{phrase!r} is not recognised as a lifecycle question")
                self.assertEqual(answered(built), want,
                                 f"{phrase!r} must return exactly the {status!r} register")

    def test_a_stale_student_row_never_overrides_the_register(self):
        """students.lifecycle_status can fall behind the register (an undo taken
        before the register was re-synced, a direct column edit). The register is
        the authority, so a status question and the Lifecycle tab must agree even
        while the two sources disagree."""
        stale, registered = LC.STATUS_TEMP_DISCONTINUED, LC.STATUS_GRADUATED
        had = one("SELECT COUNT(*) AS c FROM student_lifecycle_status WHERE usn=%s",
                  (S_OTHER,))["c"]
        try:
            write("UPDATE students SET lifecycle_status=%s WHERE usn=%s", (stale, S_OTHER))
            write("INSERT INTO student_lifecycle_status (usn, current_status, reason_category) "
                  "VALUES (%s,%s,'academic') ON DUPLICATE KEY "
                  "UPDATE current_status=VALUES(current_status)", (S_OTHER, registered))
            self.assertIn(S_OTHER, status_usns(registered),
                          "the fixture no longer reproduces the drift")
            self.assertNotIn(S_OTHER, status_usns(stale))

            built = RQ._build_lifecycle_query("show graduated students")
            self.assertIsNotNone(built, "'show graduated students' built no SQL")
            self.assertIn(S_OTHER, answered(built),
                          "a status question ignored what the register says")
            listed = call(RL.list_lifecycle, status=registered, current_user=STAFF)
            self.assertIn(S_OTHER, [r["usn"] for r in listed["data"]],
                          "the register itself does not list the student")

            wrong = RQ._build_lifecycle_query(
                "show students with status temporarily discontinued")
            self.assertNotIn(S_OTHER, answered(wrong),
                             "the stale column answered a status question")
            shown = rows(wrong["sql"], wrong["params"])
            stale_row = [r for r in shown if r["usn"] == S_OTHER]
            self.assertFalse(stale_row, "the stale status leaked into the results")
        finally:
            if not had:
                write("DELETE FROM student_lifecycle_status WHERE usn=%s", (S_OTHER,))
            write("UPDATE students SET lifecycle_status=%s WHERE usn=%s",
                  (LC.STATUS_OTHER, S_OTHER))

    def test_vague_family_phrases_keep_the_documented_family(self):
        """An unnamed phrase ("list dropouts") means the whole left-the-college
        family; that widening is deliberate and must survive an exact-status fix."""
        family = family_usns([LC.STATUS_DROPOUT, LC.STATUS_TEMP_DISCONTINUED,
                              LC.STATUS_DISCONTINUED_REVIEW])
        self.assertTrue(family, "no student is in the discontinued family")
        for phrase in ("list dropouts", "show students who discontinued their studies"):
            with self.subTest(phrase=phrase):
                built = RQ._build_lifecycle_query(phrase)
                self.assertIsNotNone(built, f"{phrase!r} produced no lifecycle SQL")
                self.assertEqual(answered(built), family,
                                 f"{phrase!r} must return the whole family")

    def test_a_count_question_answers_with_a_number_not_a_widened_set(self):
        want = status_usns(LC.STATUS_TEMP_DISCONTINUED)
        self.assertTrue(want, "no student is temporarily discontinued")
        built = RQ._build_lifecycle_query("how many students are temporarily discontinued")
        self.assertIsNotNone(built, "the count question was not recognised")
        self.assertIn("COUNT(", built["sql"].upper())
        got = rows(built["sql"], built["params"])[0]
        self.assertEqual(int(got["total_students"]), len(want),
                         f"counted {got} but the register holds {len(want)}")

    def test_a_status_word_in_an_unrelated_question_does_not_hijack_it(self):
        """'Active' also qualifies backlogs, fees and semesters. A question about
        those must stay with the answer engine that knows them."""
        for phrase in (
                "show active CS students in semester 6 with cgpa above 7.0 from kolar "
                "district having zero backlogs",
                "students with active backlog arrears",
                "show students who failed the CET exam in 2019",
                "show students who were expelled",
                "list students from other branches"):
            with self.subTest(phrase=phrase):
                self.assertIsNone(RQ._build_lifecycle_query(phrase),
                                  f"{phrase!r} must not be answered as a lifecycle register")

    def test_lifecycle_answers_reach_the_real_query_endpoint(self):
        phrase = "show graduated students"
        want = status_usns(LC.STATUS_GRADUATED)
        self.assertTrue(want, "no student is graduated")
        clear_cache(phrase)
        resp = RQ.generate_query(RQ.QueryRequest(natural_query=phrase, language="en"),
                                current_user=ADMIN)
        got = sorted({r.get("usn") for r in resp.get("data") or [] if r.get("usn")})
        self.assertEqual(got, want, "the staff search bar must answer exactly the graduated list")

    # ── 4. reason categories ─────────────────────────────────────────────────
    def test_every_configured_category_is_filterable_and_matches_truth(self):
        for category in LC.REASON_CATEGORIES:
            with self.subTest(category=category):
                got = sorted(r["usn"] for r in RL.list_lifecycle(
                    reason_category=category, current_user=ADMIN)["data"])
                self.assertEqual(got, category_usns(category),
                                 f"filter {category!r} disagrees with the register")

    def test_category_filter_ignores_letter_case(self):
        want = category_usns("financial")
        self.assertTrue(want, "no student is recorded under a financial reason")
        for spelling in ("Financial", "FINANCIAL", " financial "):
            with self.subTest(spelling=spelling):
                got = sorted(r["usn"] for r in RL.list_lifecycle(
                    reason_category=spelling, current_user=ADMIN)["data"])
                self.assertEqual(got, want, f"{spelling!r} must find the financial rows")

    def test_unknown_category_is_refused_rather_than_answering_empty(self):
        with self.assertRaises(HTTPException) as ctx:
            RL.list_lifecycle(reason_category="not-a-reason", current_user=ADMIN)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("reason", str(ctx.exception.detail).lower())

    def test_written_category_is_visible_to_the_question_staff_ask(self):
        phrase = "show students who discontinued due to financial problems"
        want = category_usns("financial", [LC.STATUS_DROPOUT, LC.STATUS_TEMP_DISCONTINUED,
                                           LC.STATUS_DISCONTINUED_REVIEW])
        self.assertTrue(want, "no discontinued-family student has a financial reason")
        clear_cache(phrase)
        built = RQ._build_lifecycle_query(phrase)
        self.assertIsNotNone(built, f"{phrase!r} was not recognised")
        self.assertEqual(answered(built), want,
                         f"{phrase!r} must return the students registered for that reason")

    def test_write_paths_store_a_filterable_category(self):
        """A reason typed in the status dialog has to become filterable data —
        the category drives both the dropdown filter and the NL questions."""
        call(RL.change_status, S_TEMP, RL.StatusChangeRequest(
            to_status=LC.STATUS_TEMP_DISCONTINUED, reason="cannot pay the tuition fees"),
            current_user=ADMIN)
        stored = one("SELECT reason, reason_category FROM student_lifecycle_status WHERE usn=%s",
                     (S_TEMP,))
        self.assertEqual(stored["reason"], "cannot pay the tuition fees")
        self.assertEqual((stored["reason_category"] or "").lower(), "financial",
                         f"stored row is invisible to the financial filter: {stored}")
        listed = sorted(r["usn"] for r in RL.list_lifecycle(
            reason_category="financial", current_user=ADMIN)["data"])
        self.assertIn(S_TEMP, listed, "the status dialog must feed the category filter")

    def test_an_off_vocabulary_category_cannot_be_stored(self):
        before = one("SELECT reason_category FROM student_lifecycle_status WHERE usn=%s", (S_DROP,))
        with self.assertRaises(HTTPException) as ctx:
            call(RL.change_status, S_DROP, RL.StatusChangeRequest(
                to_status=LC.STATUS_DROPOUT, reason="left the college",
                reason_category="Administrative"), current_user=ADMIN)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("administrat", str(ctx.exception.detail).lower(),
                      "the error must name what was rejected")
        after = one("SELECT reason_category FROM student_lifecycle_status WHERE usn=%s", (S_DROP,))
        self.assertEqual((after or {}).get("reason_category"), (before or {}).get("reason_category"),
                         "a refused write must not touch the register")

    def test_classification_is_deterministic_and_never_invents_one_for_blanks(self):
        self.assertIsNone(classify_reason_category("   "))
        self.assertEqual(classify_reason_category("father died, no money for fees"), "financial")
        self.assertEqual(classify_reason_category("hospitalised for three months"), "medical")
        self.assertEqual(classify_reason_category("family shifted to Bangalore"), "relocation")
        self.assertEqual(classify_reason_category("failed two semesters"), "academic")
        self.assertEqual(classify_reason_category("just like that"), "other")

    # ── 5. transitions write history without touching anything else ──────────
    def test_status_change_appends_history_and_leaves_academic_data_untouched(self):
        write("INSERT INTO marks (usn,semester,sgpa,year) VALUES (%s,5,7.5,2025) "
              "ON DUPLICATE KEY UPDATE sgpa=7.5", (S_ACT,))
        write("INSERT INTO student_fees (usn,fee_type,year,status) VALUES (%s,'VTU',1,'Not Paid') "
              "ON DUPLICATE KEY UPDATE status='Not Paid'", (S_ACT,))
        marks_before = rows("SELECT semester,sgpa FROM marks WHERE usn=%s", (S_ACT,))
        fees_before = rows("SELECT fee_type,status FROM student_fees WHERE usn=%s", (S_ACT,))
        student_before = one("SELECT name,branch,admission_year,current_sem,phone,email "
                             "FROM students WHERE usn=%s", (S_ACT,))
        self.assertTrue(marks_before and fees_before, "the seeded student has no academic data to protect")

        out = call(RL.change_status, S_ACT, RL.StatusChangeRequest(
            to_status=LC.STATUS_DROPOUT, reason="financial problems",
            effective_date="2026-08-01"), current_user=ADMIN)
        self.assertEqual((out["from_status"], out["to_status"]),
                         (LC.STATUS_ACTIVE, LC.STATUS_DROPOUT))

        self.assertEqual(rows("SELECT semester,sgpa FROM marks WHERE usn=%s", (S_ACT,)),
                         marks_before, "a lifecycle change edited marks")
        self.assertEqual(rows("SELECT fee_type,status FROM student_fees WHERE usn=%s", (S_ACT,)),
                         fees_before, "a lifecycle change edited fees")
        after = one("SELECT name,branch,admission_year,current_sem,phone,email "
                    "FROM students WHERE usn=%s", (S_ACT,))
        self.assertEqual(after, student_before,
                         "a lifecycle change must not edit academic or personal data")

        history = events(S_ACT)
        self.assertEqual(len(history), 1, f"expected exactly one appended event: {history}")
        self.assertEqual((history[0]["from_status"], history[0]["to_status"]),
                         (LC.STATUS_ACTIVE, LC.STATUS_DROPOUT))
        self.assertEqual(history[0]["actor_username"], ADMIN["username"])
        self.assertEqual(history[0]["actor_role"], ADMIN["role"])

    # ── 6. who may do what ───────────────────────────────────────────────────
    def test_lifecycle_write_gates_are_enforced(self):
        # The handlers are called in-process elsewhere, so the role gate itself is
        # asserted directly: this is what the HTTP layer runs as a dependency.
        gates = {"status change": require_roles("Admin"),
                 "readmission decision": require_roles("Admin"),
                 "nl confirm": require_roles("Admin"),
                 "identity link": require_roles("Admin"),
                 "backlog clear": require_roles("Admin"),
                 "readmission request": require_roles("Staff", "Admin"),
                 "nl record preview": require_roles("Staff", "Admin"),
                 "register read": require_roles("Staff", "Admin")}
        for name, dep in gates.items():
            with self.subTest(gate=name):
                with self.assertRaises(HTTPException) as ctx:
                    dep(current_user=VIEWER)
                self.assertEqual(ctx.exception.status_code, 403)
        # Staff may record and read, but never commit a status or a decision.
        require_roles("Staff", "Admin")(current_user=STAFF)
        for name in ("status change", "readmission decision", "nl confirm"):
            with self.subTest(staff_refused=name):
                with self.assertRaises(HTTPException) as ctx:
                    gates[name](current_user=STAFF)
                self.assertEqual(ctx.exception.status_code, 403)

    # ── 7. natural-language recording from the search bar ────────────────────
    def test_record_phrases_are_parsed_in_every_shape_staff_type(self):
        cases = [
            (f"mark {S_CANCEL} as dropped out due to financial problems", LC.STATUS_DROPOUT,
             S_CANCEL, "financial"),
            (f"discontinue student {S_TEMP} because of an illness", LC.STATUS_TEMP_DISCONTINUED,
             S_TEMP, "medical"),
            (f"student {S_REJOIN} rejoined the college", LC.STATUS_REJOINED, S_REJOIN, None),
            (f"apply for readmission of {S_REQ}", LC.STATUS_READMISSION_REQUESTED, S_REQ, None),
            (f"graduate {S_OTHER} on 2026-05-30", LC.STATUS_GRADUATED, S_OTHER, None),
            (f"transfer the student {S_CANCEL}", LC.STATUS_TRANSFERRED, S_CANCEL, None),
            # mistyped and ungrammatical, exactly as staff type them
            (f"discontious student {S_TEMP} due to money problem", LC.STATUS_TEMP_DISCONTINUED,
             S_TEMP, "financial"),
            (f"{S_DROP} drop out reason family issue", LC.STATUS_DROPOUT, S_DROP, "family"),
        ]
        for phrase, want_status, want_usn, want_category in cases:
            with self.subTest(phrase=phrase):
                parsed = parse_lifecycle_command(phrase)
                self.assertEqual(parsed["target_status"], want_status,
                                 f"{phrase!r} read as {parsed['target_status']!r}")
                self.assertEqual(parsed["usn"], want_usn,
                                 f"{phrase!r} lost the identity of the student")
                if want_category is not None:
                    self.assertEqual(parsed["reason_category"], want_category,
                                     f"{phrase!r} reason classified as "
                                     f"{parsed['reason_category']!r}")

    def test_listing_questions_are_never_treated_as_records(self):
        for phrase in ("show all dropouts", "how many students discontinued",
                       "list students who rejoined", "number of graduated students"):
            with self.subTest(phrase=phrase):
                self.assertFalse(LC.is_lifecycle_record_command(phrase),
                                 f"{phrase!r} must stay a read")
        for phrase in (f"mark {S_TEMP} as discontinued", f"record dropout of {S_DROP}",
                       f"note {S_REJOIN} rejoined"):
            with self.subTest(phrase=phrase):
                self.assertTrue(LC.is_lifecycle_record_command(phrase),
                                f"{phrase!r} must be offered as a record")

    def test_recording_an_unknown_student_creates_nothing(self):
        preview = RL._prepare_lifecycle_payload(
            "mark 9ZZ99ZZ999 as dropped out", "en", None, ADMIN["username"])
        self.assertEqual(preview["action_required"], "no_record", str(preview))
        self.assertIsNone(one("SELECT usn FROM student_lifecycle_status WHERE usn=%s",
                              ("9ZZ99ZZ999",)),
                          "a preview must never create lifecycle data")

    def test_search_bar_sends_a_record_command_to_the_lifecycle_preview(self):
        phrase = f"mark {S_TEMP} as discontinued due to financial reasons"
        clear_cache(phrase)
        resp = RQ.generate_query(RQ.QueryRequest(natural_query=phrase, language="en"),
                                current_user=STAFF)
        self.assertEqual(resp.get("action_required"), "confirm", str(resp)[:300])
        self.assertEqual(resp.get("action_type"), "LIFECYCLE")
        self.assertEqual(resp.get("confirm_endpoint"), "/api/lifecycle/nl/confirm")
        self.assertEqual(resp.get("role_restricted"), "Admin",
                         "Staff may preview a lifecycle change but only Admin may commit it")
        self.assertEqual(resp.get("payload", {}).get("usn"), S_TEMP,
                         "the preview must carry the resolved student")
        self.assertFalse(events(S_TEMP), "previewing must write nothing")

    def test_a_record_command_by_student_name_keeps_the_name_intact(self):
        """Staff type a name, not a USN. Stripping the instruction words must not
        eat letters out of the name itself ('as' in Ashoka, 'a' in Rahul)."""
        cases = [
            ("mark Rahul Sharma as discontinued", "Rahul Sharma"),
            ("record dropout of Ashoka Prasad", "Ashoka Prasad"),
            ("discontinue Srinivasan due to illness", "Srinivasan"),
            ("note Ganesh Kumar rejoined", "Ganesh Kumar"),
        ]
        for phrase, want_name in cases:
            with self.subTest(phrase=phrase):
                parsed = parse_lifecycle_command(phrase)
                self.assertEqual(parsed["usn"], None, f"{phrase!r} invented a USN")
                self.assertEqual(parsed["target_text"], want_name,
                                 f"{phrase!r} searched for {parsed['target_text']!r} "
                                 f"instead of {want_name!r}")

    def test_an_ambiguous_name_asks_instead_of_recording(self):
        for usn in (S_REQ, S_APPR):
            write("UPDATE students SET name='Rahul Sharma' WHERE usn=%s", (usn,))
        out = RL._prepare_lifecycle_payload("mark Rahul Sharma as discontinued",
                                            "en", None, STAFF["username"])
        self.assertEqual(out["action_required"], "select_student", str(out))
        self.assertGreaterEqual(len(out["suggestions"]), 2)
        self.assertTrue(all(not events(u) for u in (S_REQ, S_APPR)),
                        "an ambiguous record request must write nothing")

    def test_a_repeated_record_is_not_stored_twice(self):
        """Staff retype the same record ('Medical' then 'medical'): one event."""
        def payload(category):
            return {"usn": S_TEMP, "to_status": LC.STATUS_TEMP_DISCONTINUED,
                    "reason": "medical", "reason_category": category,
                    "effective_date": "2026-07-01", "event_type": LC.EV_DISCONTINUE}

        def commit(category):
            p = payload(category)
            return call(RL.nl_confirm, RL.NlConfirmRequest(
                payload=p, confirmation_token=create_confirmation_token(
                    p, ADMIN["username"])), current_user=ADMIN)

        self.assertFalse(commit("Medical").get("deduplicated"),
                         "the first record must be stored")
        second = commit("medical")
        self.assertTrue(second.get("deduplicated"),
                        f"a repeated record differing only in letter case must be "
                        f"suppressed: {second}")
        self.assertEqual(len(events(S_TEMP)), 1, "the register must hold one event, not two")

    def test_the_status_button_suppresses_a_repeated_record_too(self):
        """The dashboard's own 'Change status' button must obey the same promise
        as the natural-language path, otherwise a double click writes two events."""
        def commit(category):
            return call(RL.change_status, S_REVIEW, RL.StatusChangeRequest(
                to_status=LC.STATUS_DISCONTINUED_REVIEW, reason="personal",
                reason_category=category, effective_date="2026-07-05"), current_user=ADMIN)

        self.assertFalse(commit("Personal").get("deduplicated"),
                         "the first record must be stored")
        second = commit("personal")
        self.assertTrue(second.get("deduplicated"),
                        f"a repeated status change must not add a second event: {second}")
        self.assertIsNone(second.get("undo_token"),
                          "a suppressed duplicate must not offer an undo it never earned")
        self.assertEqual(len(events(S_REVIEW)), 1, "the register holds two events for one record")

        moved = call(RL.change_status, S_REVIEW, RL.StatusChangeRequest(
            to_status=LC.STATUS_TEMP_DISCONTINUED, reason="medical",
            effective_date="2026-07-05"), current_user=ADMIN)
        self.assertFalse(moved.get("deduplicated"),
                         "a different status is a real change, not a duplicate")
        self.assertEqual(len(events(S_REVIEW)), 2)


class Phase5UndoStatusTests(unittest.TestCase):
    """Undo is the staff escape route for a wrongly recorded status, so the
    lifecycle register has to come back with it."""

    @classmethod
    def setUpClass(cls):
        seed()

    @classmethod
    def tearDownClass(cls):
        purge(MINE)
        ph = ",".join(["%s"] * len(ACTORS))
        write(f"DELETE FROM global_undo_snapshots WHERE performed_by IN ({ph})", ACTORS)

    def test_undoing_a_status_change_returns_the_student_to_the_previous_status(self):
        self.assertEqual(status_usns(LC.STATUS_ADMISSION_CANCELLED).count(S_CANCEL), 1)
        out = call(RL.change_status, S_CANCEL, RL.StatusChangeRequest(
            to_status=LC.STATUS_TEMP_DISCONTINUED, reason="entered by mistake",
            effective_date="2026-09-01"), current_user=ADMIN)
        self.assertEqual(out["to_status"], LC.STATUS_TEMP_DISCONTINUED)
        self.assertIn(S_CANCEL, status_usns(LC.STATUS_TEMP_DISCONTINUED))

        from routes_undo import restore_student
        restore_student(out["undo_token"], current_user=ADMIN)

        self.assertEqual(one("SELECT lifecycle_status FROM students WHERE usn=%s",
                             (S_CANCEL,))["lifecycle_status"], LC.STATUS_ADMISSION_CANCELLED,
                         "undo must put the student's own status back")
        self.assertNotIn(S_CANCEL, status_usns(LC.STATUS_TEMP_DISCONTINUED),
                         "the lifecycle register still shows the undone status")
        self.assertIn(S_CANCEL, status_usns(LC.STATUS_ADMISSION_CANCELLED),
                      "the undone student must be findable again as Admission Cancelled")
        # history stays as the audit trail, and it must still explain the register
        history = events(S_CANCEL)
        self.assertGreaterEqual(len(history), 2,
                                f"the correction was not recorded: {history}")
        self.assertEqual(history[-1]["to_status"], LC.STATUS_ADMISSION_CANCELLED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
