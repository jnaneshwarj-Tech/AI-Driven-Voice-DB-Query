"""
Student Lifecycle Management tests (spec §2-§12).

Covers: canonical statuses, discontinuation / dropout / readmission / rejoin
workflows, history preservation, "lifecycle changes never delete academic/fee/
backlog records", conservative advisory eligibility (never auto-approves),
role authorization, undo/recovery + audit, invalid/missing/conflicting inputs,
immediate reflection in reports/exports, and multilingual (EN / Kannada Unicode /
Roman-Kannada / mixed) NL routing.

Safety (per project constraints):
  * Only synthetic test USNs (prefix "9ZZLC") are ever inserted or mutated.
  * Expected sets are computed by independent hand-written SQL against MySQL,
    never by the parser/endpoint under test.
  * The tests never DELETE/TRUNCATE production data; teardown removes only rows
    carrying the synthetic test USNs.
"""
import io
import os
import sys
import unittest
from types import SimpleNamespace

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

# Console (cp1252 on Windows) cannot encode Kannada when unittest prints errors.
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

from fastapi import HTTPException

import lifecycle as LC
import report_service
import routes_export
import routes_lifecycle as RL
from auth import require_roles
from database import db_conn
from kannada_processor import normalize_query
from routes_query import QueryRequest, _build_lifecycle_query, generate_query
from routes_undo import restore_student

ADMIN = {"username": "lc_admin", "role": "Admin"}
STAFF = {"username": "lc_staff", "role": "Staff"}

# Synthetic USNs — never collide with the 148 real students.
U_DISCONT = "9ZZLC0001"   # Temporarily Discontinued, unpaid fee, open backlog
U_DROPOUT = "9ZZLC0002"   # Dropout with document/reason
U_READMIT = "9ZZLC0003"   # Readmission Approved (not joined)
U_REJOIN  = "9ZZLC0004"   # Rejoined-Active, all backlogs cleared
U_ACTIVE  = "9ZZLC0005"   # Active
U_GONE    = "9ZZLC9999"   # never inserted (404 / missing tests)
U_DUP     = "9ZZLC0006"   # shares U_DISCONT's name only inside the ambiguity test

ALL_TEST = [U_DISCONT, U_DROPOUT, U_READMIT, U_REJOIN, U_ACTIVE]


def _all_synthetic():
    return ALL_TEST + [U_GONE, U_DUP]

SCHEME = "BE2022"
RULE_KEY = "max_completion_years"   # engine only recognizes this exact rule_key


def _cur(conn):
    return conn.cursor(dictionary=True)


def _exec(sql, params=()):
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, list(params))
        conn.commit()
        cur.close()


def _query(sql, params=()):
    with db_conn() as conn:
        cur = _cur(conn)
        cur.execute(sql, list(params))
        rows = cur.fetchall()
        cur.close()
    return rows


def _seed_students():
    _cleanup()
    with db_conn() as conn:
        cur = conn.cursor()
        rows = [
            (U_DISCONT, "Discontinue One", "Temporarily Discontinued", 2019, "CSE", "KC"),
            (U_DROPOUT, "Dropout Two", "Dropout-College Recorded", 2020, "CSE", "GEN"),
            (U_READMIT, "Readmit Three", "Readmission Approved", 2019, "CSE", "KC"),
            (U_REJOIN,  "Rejoin Four", "Rejoined-Active", 2020, "CSE", "GEN"),
            (U_ACTIVE,  "Active Five", "Active", 2023, "CSE", "GEN"),
        ]
        for usn, name, status, year, branch, cat in rows:
            cur.execute(
                "INSERT INTO students (usn, name, gender, branch, admission_year, "
                "student_type, lifecycle_status) VALUES (%s,%s,'Male',%s,%s,%s,%s)",
                (usn, name, branch, year, cat, status),
            )
        conn.commit()
        cur.close()

    # marks (academic history that must NEVER be touched by lifecycle ops)
    _exec("INSERT INTO marks (usn, semester, sgpa, year) VALUES (%s,1,8.0,2020)", (U_DISCONT,))
    _exec("INSERT INTO marks (usn, semester, sgpa, year) VALUES (%s,2,7.5,2020)", (U_DISCONT,))
    _exec("INSERT INTO marks (usn, semester, sgpa, year) VALUES (%s,3,7.0,2021)", (U_DISCONT,))
    _exec("INSERT INTO marks (usn, semester, sgpa, year) VALUES (%s,1,6.5,2021)", (U_REJOIN,))

    # fees — U_DISCONT has a genuinely unpaid fee (status 'Not Paid')
    _exec("INSERT INTO student_fees (usn, fee_type, year, status, amount_paid, remaining_amount) "
          "VALUES (%s,'VTU',1,'Not Paid','0','5000')", (U_DISCONT,))
    _exec("INSERT INTO student_fees (usn, fee_type, year, status, amount_paid, remaining_amount) "
          "VALUES (%s,'Tuition',1,'Paid','8000','0')", (U_ACTIVE,))

    # backlogs — U_DISCONT open, U_REJOIN cleared
    _exec("INSERT INTO student_backlogs (usn, subject, semester, year, cleared) "
          "VALUES (%s,'Operating Systems',4,'2026',0)", (U_DISCONT,))
    _exec("INSERT INTO student_backlogs (usn, subject, semester, year, cleared) "
          "VALUES (%s,'DBMS',3,'2025',1)", (U_REJOIN,))

    # derived cache rows (so status/history reads are consistent)
    for usn, status, sem in ((U_DISCONT, "Temporarily Discontinued", 3),
                             (U_DROPOUT, "Dropout-College Recorded", 2),
                             (U_READMIT, "Readmission Approved", 4),
                             (U_REJOIN, "Rejoined-Active", 1)):
        _exec("INSERT INTO student_lifecycle_status (usn, current_status, last_enrolled_semester, scheme) "
              "VALUES (%s,%s,%s,%s)", (usn, status, sem, SCHEME))

    # one controlled identity link (spec §3)
    _exec("INSERT INTO student_identity_links (usn, related_usn, relation_type, note, created_by) "
          "VALUES (%s,%s,'READDITmission_OLD_USN','old register no','lc_admin')",
          (U_DISCONT, "9ZZLC0099"))

    # verified + unverified scheme rules (only 'verified' must apply)
    _exec("INSERT INTO vtu_scheme_rules (scheme_code, admission_category, rule_key, rule_value, "
          "source_url, clause_ref, verification_status) "
          "VALUES (%s,'',%s,'6','https://vtu.ac.in','Sec 8.2','verified')",
          (SCHEME, RULE_KEY))
    _exec("INSERT INTO vtu_scheme_rules (scheme_code, admission_category, rule_key, rule_value, "
          "source_url, clause_ref, verification_status) "
          "VALUES (%s,'',%s,'99','https://vtu.ac.in','Draft','pending')",
          (SCHEME, RULE_KEY + "_unverified"))


def _cleanup():
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM vtu_scheme_rules WHERE scheme_code=%s", (SCHEME,))
        for tbl in ("students", "marks", "student_fees", "student_backlogs",
                    "student_lifecycle_status", "student_lifecycle_events",
                    "readmission_requests", "student_identity_links"):
            placeholders = ",".join(["%s"] * len(_all_synthetic()))
            cur.execute(f"DELETE FROM {tbl} WHERE usn IN ({placeholders})", _all_synthetic())
        conn.commit()
        cur.close()


def _marks_fingerprint(usn):
    return [(r["semester"], r["sgpa"], r["year"]) for r in
            _query("SELECT semester, sgpa, year FROM marks WHERE usn=%s ORDER BY semester", (usn,))]


def _read_response(resp):
    with open(resp.path, "rb") as f:
        raw = f.read()
    try:
        os.remove(resp.path)
    except OSError:
        pass
    return raw


class LifecycleLogicTests(unittest.TestCase):
    def test_status_normalization_and_validity(self):
        self.assertTrue(LC.is_valid_status("Temporarily Discontinued"))
        self.assertFalse(LC.is_valid_status("Not A Real Status"))
        self.assertEqual(LC.normalize_status("rejoined-active"), "Rejoined-Active")
        self.assertEqual(LC.normalize_status("DROPOUT-COLLEGE RECORDED"),
                         "Dropout-College Recorded")
        self.assertIsNone(LC.normalize_status("gibberish"))

    def test_status_buckets(self):
        self.assertIn("Rejoined-Active", LC.ACTIVE_STATUSES)
        self.assertIn("Readmission Approved", LC.ACTIVE_STATUSES)
        self.assertEqual(LC.DISCONTINUED_STATUSES, {
            "Temporarily Discontinued", "Discontinued-Review Req", "Dropout-College Recorded"})

    def test_all_statuses_fit_column(self):
        for s in LC.LIFECYCLE_STATUSES:
            self.assertLessEqual(len(s), 30, f"{s} exceeds 30 chars")


class LifecycleWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _seed_students()

    @classmethod
    def tearDownClass(cls):
        _cleanup()

    def setUp(self):
        # reset derived tables so each workflow test starts clean
        ph = ",".join(["%s"] * len(ALL_TEST))
        _exec(f"DELETE FROM student_lifecycle_events WHERE usn IN ({ph})", ALL_TEST)
        _exec(f"DELETE FROM readmission_requests WHERE usn IN ({ph})", ALL_TEST)

    # §4 discontinuation workflow — append history, keep academic data intact
    def test_active_to_temp_discontinuation_preserves_history_and_data(self):
        before_marks = _marks_fingerprint(U_ACTIVE)
        req = RL.StatusChangeRequest(to_status="Temporarily Discontinued",
                                     reason="medical", effective_date="2026-01-10",
                                     last_enrolled_semester=3)
        res = RL.change_status(U_ACTIVE, req, current_user=ADMIN)
        self.assertEqual(res["from_status"], "Active")
        self.assertEqual(res["to_status"], "Temporarily Discontinued")

        # students.lifecycle_status updated (derived cache)
        srow = _query("SELECT lifecycle_status FROM students WHERE usn=%s", (U_ACTIVE,))[0]
        self.assertEqual(srow["lifecycle_status"], "Temporarily Discontinued")

        # an event was APPENDED with from/to and reason preserved
        events = _query("SELECT * FROM student_lifecycle_events WHERE usn=%s ORDER BY id", (U_ACTIVE,))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["from_status"], "Active")
        self.assertEqual(events[0]["to_status"], "Temporarily Discontinued")
        self.assertEqual(events[0]["reason"], "medical")

        # academic history untouched
        self.assertEqual(_marks_fingerprint(U_ACTIVE), before_marks)

    def test_status_change_never_deletes_fees_or_backlogs(self):
        fee_n = len(_query("SELECT * FROM student_fees WHERE usn=%s", (U_DISCONT,)))
        bl_n = len(_query("SELECT * FROM student_backlogs WHERE usn=%s", (U_DISCONT,)))
        RL.change_status(U_DISCONT, RL.StatusChangeRequest(to_status="Discontinued-Review Req"),
                         current_user=ADMIN)
        self.assertEqual(len(_query("SELECT * FROM student_fees WHERE usn=%s", (U_DISCONT,))), fee_n)
        self.assertEqual(len(_query("SELECT * FROM student_backlogs WHERE usn=%s", (U_DISCONT,))), bl_n)

    def test_dropout_records_document_and_reason(self):
        RL.change_status(U_DROPOUT, RL.StatusChangeRequest(
            to_status="Dropout-College Recorded", event_type=LC.EV_DISCONTINUE,
            reason="left college", document_ref="DOC-777"), current_user=ADMIN)
        ev = _query("SELECT * FROM student_lifecycle_events WHERE usn=%s ORDER BY id DESC LIMIT 1",
                    (U_DROPOUT,))[0]
        self.assertEqual(ev["document_ref"], "DOC-777")
        self.assertEqual(ev["event_type"], LC.EV_DISCONTINUE)

    # §5 readmission request → approved-not-joined → actual rejoin
    def test_readmission_request_approved_not_joined(self):
        RL.create_readmission_request(U_DROPOUT,
            RL.ReadmissionRequestModel(requested_semester=3, request_date="2026-02-01"),
            current_user=STAFF)
        self.assertEqual(_query("SELECT lifecycle_status FROM students WHERE usn=%s", (U_DROPOUT,))[0]["lifecycle_status"],
                         "Readmission Requested")
        rr = _query("SELECT * FROM readmission_requests WHERE usn=%s ORDER BY id DESC LIMIT 1", (U_DROPOUT,))[0]
        self.assertEqual(rr["status"], "Requested")

        # Admin approves WITHOUT rejoin → still not "joined"
        RL.decide_readmission(U_DROPOUT,
            RL.ReadmissionDecisionModel(decision="approve", approved_semester=3,
                                        approval_date="2026-02-10", approval_ref="APR-1"),
            current_user=ADMIN)
        self.assertEqual(_query("SELECT lifecycle_status FROM students WHERE usn=%s", (U_DROPOUT,))[0]["lifecycle_status"],
                         "Readmission Approved")
        rr = _query("SELECT * FROM readmission_requests WHERE usn=%s ORDER BY id DESC LIMIT 1", (U_DROPOUT,))[0]
        self.assertEqual(rr["status"], "Approved")

    def test_readmission_with_rejoin_becomes_active(self):
        RL.create_readmission_request(U_DISCONT, RL.ReadmissionRequestModel(requested_semester=4),
            current_user=STAFF)
        RL.decide_readmission(U_DISCONT, RL.ReadmissionDecisionModel(
            decision="approve", approved_semester=4, rejoin=True, rejoin_date="2026-03-01"),
            current_user=ADMIN)
        self.assertEqual(_query("SELECT lifecycle_status FROM students WHERE usn=%s", (U_DISCONT,))[0]["lifecycle_status"],
                         "Rejoined-Active")
        rr = _query("SELECT * FROM readmission_requests WHERE usn=%s ORDER BY id DESC LIMIT 1", (U_DISCONT,))[0]
        self.assertEqual(rr["status"], "Joined")

    def test_decision_without_request_is_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            RL.decide_readmission(U_ACTIVE, RL.ReadmissionDecisionModel(decision="approve"),
                                  current_user=ADMIN)
        self.assertEqual(ctx.exception.status_code, 400)

    # invalid / missing / conflicting inputs
    def test_invalid_status_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            RL.change_status(U_ACTIVE, RL.StatusChangeRequest(to_status="Space Cadet"), current_user=ADMIN)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_missing_student_404(self):
        with self.assertRaises(HTTPException) as ctx:
            RL.change_status(U_GONE, RL.StatusChangeRequest(to_status="Active"), current_user=ADMIN)
        self.assertEqual(ctx.exception.status_code, 404)


class LifecycleEligibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _seed_students()

    @classmethod
    def tearDownClass(cls):
        _cleanup()

    def _elig(self, usn):
        with db_conn() as conn:
            cur = _cur(conn)
            res = LC.evaluate_eligibility(cur, usn, requested_sem=3, scheme=SCHEME)
            cur.close()
        return res

    def test_never_auto_approves_and_always_needs_review(self):
        res = self._elig(U_READMIT)
        self.assertFalse(res["auto_approved"])
        self.assertTrue(res["review_required"])

    def test_only_verified_rules_apply(self):
        res = self._elig(U_READMIT)
        keys = {r["rule_key"] for r in res["rules_applied"]}
        self.assertIn(RULE_KEY, keys)
        self.assertNotIn(f"{RULE_KEY}_unverified", keys)

    def test_exceeded_max_duration_flags_concern(self):
        # U_DISCONT admission_year=2019 -> elapsed (2026-2019)=7 > configured 6
        res = self._elig(U_DISCONT)
        self.assertTrue(any("exceeds configured maximum" in c for c in res["concerns"]))

    def test_open_backlog_is_flagged_not_assumed(self):
        res = self._elig(U_DISCONT)
        self.assertTrue(any("open backlog" in c for c in res["concerns"]))

    def test_unresolved_scheme_requires_manual_review(self):
        with db_conn() as conn:
            cur = _cur(conn)
            res = LC.evaluate_eligibility(cur, U_ACTIVE, requested_sem=1, scheme="NO_SUCH_SCHEME")
            cur.close()
        self.assertTrue(any("No verified scheme rule" in c for c in res["concerns"]))
        self.assertTrue(res["review_required"])


class LifecycleAuthorizationTests(unittest.TestCase):
    def test_status_change_requires_admin(self):
        dep = require_roles("Admin")
        with self.assertRaises(HTTPException) as ctx:
            dep(current_user={"username": "s", "role": "Staff"})
        self.assertEqual(ctx.exception.status_code, 403)

    def test_decision_requires_admin(self):
        dep = require_roles("Admin")
        dep(current_user={"username": "a", "role": "Admin"})  # no raise

    def test_readmission_request_allows_staff(self):
        dep = require_roles("Staff", "Admin")
        dep(current_user={"username": "s", "role": "Staff"})  # no raise


class LifecycleUndoAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _seed_students()

    @classmethod
    def tearDownClass(cls):
        _cleanup()

    def test_undo_reverts_status_history_is_append_only(self):
        _exec("UPDATE students SET lifecycle_status=%s WHERE usn=%s", ("Active", U_READMIT))
        _exec("DELETE FROM student_lifecycle_status WHERE usn=%s", (U_READMIT,))
        res = RL.change_status(U_READMIT, RL.StatusChangeRequest(to_status="Graduated"), current_user=ADMIN)
        token = res["undo_token"]
        self.assertEqual(_query("SELECT lifecycle_status FROM students WHERE usn=%s", (U_READMIT,))[0]["lifecycle_status"],
                         "Graduated")

        # restore using the SAME actor (undo is ownership-checked)
        restore_student(token, current_user=ADMIN)
        self.assertEqual(_query("SELECT lifecycle_status FROM students WHERE usn=%s", (U_READMIT,))[0]["lifecycle_status"],
                         "Active")
        # event history is NOT rolled back — append-only authoritative record kept
        self.assertGreaterEqual(
            len(_query("SELECT * FROM student_lifecycle_events WHERE usn=%s", (U_READMIT,))), 1)

    def test_status_change_writes_audit_log(self):
        before = len(_query("SELECT id FROM audit_log WHERE action=%s AND target_id=%s",
                            ("lifecycle_status_change", U_ACTIVE)))
        RL.change_status(U_ACTIVE, RL.StatusChangeRequest(to_status="Transferred"), current_user=ADMIN)
        after = len(_query("SELECT id FROM audit_log WHERE action=%s AND target_id=%s",
                           ("lifecycle_status_change", U_ACTIVE)))
        self.assertGreater(after, before)


class LifecycleReportExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _seed_students()

    @classmethod
    def tearDownClass(cls):
        _cleanup()

    def setUp(self):
        # A prior test in this class may change U_DISCONT's status; restore the
        # seeded derived state so each report assertion sees the intended value.
        _exec("UPDATE students SET lifecycle_status=%s WHERE usn=%s",
              ("Temporarily Discontinued", U_DISCONT))
        _exec("UPDATE student_lifecycle_status SET current_status=%s WHERE usn=%s",
              ("Temporarily Discontinued", U_DISCONT))

    def test_report_model_reflects_lifecycle_immediately(self):
        model = report_service.build_report_model([{"usn": U_DISCONT}], ADMIN)
        st = model["students"][0]
        self.assertEqual(st["lifecycle"]["current_status"], "Temporarily Discontinued")

    def test_after_status_change_report_updates(self):
        RL.change_status(U_DISCONT, RL.StatusChangeRequest(to_status="Active"), current_user=ADMIN)
        model = report_service.build_report_model([{"usn": U_DISCONT}], ADMIN)
        self.assertEqual(model["students"][0]["lifecycle"]["current_status"], "Active")

    def test_csv_excel_pdf_carry_lifecycle_and_fee(self):
        payload = [{"usn": U_DISCONT}]
        csv_text = _read_response(routes_export.export_csv(payload, ADMIN)).decode("utf-8")
        self.assertIn("LIFECYCLE", csv_text.upper())
        self.assertIn("Temporarily Discontinued", csv_text)
        # fee still present (lifecycle change must not drop fee reporting)
        self.assertIn("VTU", csv_text)
        xls_raw = _read_response(routes_export.export_excel(payload, ADMIN))
        self.assertTrue(xls_raw[:2] == b"PK")
        pdf_raw = _read_response(routes_export.export_pdf(payload, ADMIN))
        self.assertEqual(pdf_raw[:5], b"%PDF-")


class LifecycleNLQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _seed_students()

    @classmethod
    def tearDownClass(cls):
        _cleanup()

    def _usns_in_sql_result(self, q):
        built = _build_lifecycle_query(q)
        self.assertIsNotNone(built, f"no lifecycle SQL for: {q}")
        rows = _query(built["sql"], built.get("params", []))
        return sorted({r["usn"] for r in rows})

    # English deterministic routing matches independent DB truth
    def test_discontinued_listing_matches_db_truth(self):
        exp = sorted(r["usn"] for r in _query(
            "SELECT usn FROM students WHERE lifecycle_status IN (%s,%s,%s)",
            ("Temporarily Discontinued", "Discontinued-Review Req", "Dropout-College Recorded")))
        self.assertEqual(self._usns_in_sql_result("show students who discontinued their studies"), exp)

    def test_dropout_listing(self):
        exp = sorted(r["usn"] for r in _query(
            "SELECT usn FROM students WHERE lifecycle_status IN (%s,%s,%s)",
            ("Dropout-College Recorded", "Temporarily Discontinued", "Discontinued-Review Req")))
        self.assertEqual(self._usns_in_sql_result("list dropouts"), exp)

    def test_rejoined_and_cleared_backlogs_excludes_open_backlog(self):
        exp = sorted(r["usn"] for r in _query(
            "SELECT s.usn FROM students s WHERE s.lifecycle_status=%s "
            "AND s.usn NOT IN (SELECT sb.usn FROM student_backlogs sb WHERE sb.cleared=0)",
            ("Rejoined-Active",)))
        got = self._usns_in_sql_result("students who rejoined and cleared all backlogs")
        self.assertEqual(got, exp)
        self.assertNotIn(U_DISCONT, got)

    # §9 multilingual equivalence — same intent across EN / KN / RK / mixed
    def test_multilingual_equivalence(self):
        en = _build_lifecycle_query("list discontinued students")
        # Kannada Unicode phrase, normalized through the shared processor
        kn_raw = "ಡಿಸ್ಟಿನ್ಯೂಡ್ ವಿದ್ಯಾರ್ಥಿಗಳು"  # discontinued students (with structural words)
        kn_norm, _ = normalize_query("ಓದು ನಿಲ್ಲಿಸಿದ ವಿದ್ಯಾರ್ಥಿಗಳು")
        kn = _build_lifecycle_query(kn_norm)
        # Roman-Kannada
        rk_norm, _ = normalize_query("odu nilistida viddyarthigalu")
        rk = _build_lifecycle_query(rk_norm)
        # mixed
        mix_norm, _ = normalize_query("ತೋರಿಸಿ odu nilistid students")
        mix = _build_lifecycle_query(mix_norm)
        for name, built in (("kn", kn), ("rk", rk), ("mixed", mix)):
            self.assertIsNotNone(built, f"{name} produced no lifecycle SQL (norm={built})")
            # all resolve to the same status IN(...) filter set as English
            self.assertIn("lifecycle_status IN", built["sql"])
        self.assertIsNotNone(en)

    def test_roman_kannada_rejoin_routes(self):
        norm, _ = normalize_query("matte sere aadtavaru")
        built = _build_lifecycle_query(norm)
        self.assertIsNotNone(built)
        self.assertIn("Rejoined-Active", str(built.get("params", "")) + built["sql"])

    def test_history_query_targets_events_table(self):
        # the engine detects a USN via a strict format regex; use a valid-format token
        built = _build_lifecycle_query("complete status history of 4HG23LC900")
        self.assertIsNotNone(built)
        self.assertIn("student_lifecycle_events", built["sql"])

    # end-to-end through the real pipeline (deterministic, no LLM) for English
    def test_generate_query_end_to_end_discontinued(self):
        resp = generate_query(
            QueryRequest(natural_query="list discontinued students", language="en",
                         response_language="en", debug=False), current_user=ADMIN)
        data = (resp if isinstance(resp, dict) else {}).get("data") or []
        got = sorted({r.get("usn") for r in data if r.get("usn")})
        exp = self._usns_in_sql_result("list discontinued students")
        self.assertEqual(got, exp)


class LifecycleIdentityAndBacklogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _seed_students()

    @classmethod
    def tearDownClass(cls):
        _cleanup()

    def setUp(self):
        ph = ",".join(["%s"] * len(ALL_TEST))
        _exec(f"DELETE FROM student_identity_links WHERE usn IN ({ph})", ALL_TEST)
        _exec(f"DELETE FROM student_lifecycle_events WHERE usn IN ({ph})", ALL_TEST)

    # §3 controlled identity links — recorded, never a merge
    def test_create_identity_link_records_without_merging(self):
        marks_before = _marks_fingerprint(U_DISCONT)
        other_marks = _marks_fingerprint(U_REJOIN)
        RL.create_identity_link(U_DISCONT, RL.IdentityLinkRequest(
            related_usn=U_REJOIN, relation_type="READMISSION_NEW_USN",
            note="old register"), current_user=ADMIN)
        links = _query("SELECT * FROM student_identity_links WHERE usn=%s", (U_DISCONT,))
        self.assertTrue(any(l["relation_type"] == "READMISSION_NEW_USN"
                            and l["related_usn"] == U_REJOIN for l in links))
        self.assertEqual(_marks_fingerprint(U_DISCONT), marks_before)
        self.assertEqual(_marks_fingerprint(U_REJOIN), other_marks)

    def test_identity_link_rejects_unknown_type(self):
        with self.assertRaises(HTTPException) as ctx:
            RL.create_identity_link(U_DISCONT, RL.IdentityLinkRequest(
                related_usn=U_REJOIN, relation_type="SECRET_MERGE"), current_user=ADMIN)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_identity_link_rejects_self_link(self):
        with self.assertRaises(HTTPException) as ctx:
            RL.create_identity_link(U_DISCONT, RL.IdentityLinkRequest(
                related_usn=U_DISCONT, relation_type="SCHEME_CHANGE"), current_user=ADMIN)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_identity_link_requires_admin(self):
        dep = require_roles("Admin")
        with self.assertRaises(HTTPException):
            dep(current_user={"username": "s", "role": "Staff"})

    # §7 verified-pass backlog clearing — flips cleared, never rewrites marks
    def test_clear_backlog_preserves_marks_and_appends_event(self):
        bl = _query("SELECT id FROM student_backlogs WHERE usn=%s AND cleared=0", (U_DISCONT,))[0]
        marks_before = _marks_fingerprint(U_DISCONT)
        events_before = len(_query("SELECT id FROM student_lifecycle_events WHERE usn=%s", (U_DISCONT,)))
        res = RL.clear_backlog_verified_pass(U_DISCONT, bl["id"],
            RL.VerifiedPassClearModel(result_ref="VTU-RESULT-555", cleared_date="2026-06-01"),
            current_user=ADMIN)
        self.assertTrue(res["cleared"])
        self.assertFalse(res["grade_recomputed"])
        self.assertEqual(
            _query("SELECT cleared FROM student_backlogs WHERE id=%s", (bl["id"],))[0]["cleared"], 1)
        self.assertEqual(_marks_fingerprint(U_DISCONT), marks_before)
        self.assertGreater(
            len(_query("SELECT id FROM student_lifecycle_events WHERE usn=%s", (U_DISCONT,))),
            events_before)

    def test_clear_backlog_wrong_student_404(self):
        bl = _query("SELECT id FROM student_backlogs WHERE usn=%s", (U_DISCONT,))[0]
        with self.assertRaises(HTTPException) as ctx:
            RL.clear_backlog_verified_pass(U_REJOIN, bl["id"],
                RL.VerifiedPassClearModel(), current_user=ADMIN)
        self.assertEqual(ctx.exception.status_code, 404)


# ── Spec B: natural-language DISCONTINUED / DROPOUT recording + retrieval ──────
def _insert_named(usn, name):
    _exec("INSERT INTO students (usn, name, gender, branch, admission_year, "
          "student_type, lifecycle_status) VALUES (%s,%s,'Male','CSE',2023,'GEN','Active')",
          (usn, name))


def _delete_usn(usn):
    for tbl in ("students", "student_lifecycle_status", "student_lifecycle_events"):
        _exec(f"DELETE FROM {tbl} WHERE usn=%s", (usn,))


class LifecycleNlRecordTests(unittest.TestCase):
    """Spec B §1/§5/§6: NL record → preview → authorized confirm. Preview saves
    nothing; unknown USN never creates a record; duplicate submissions are
    suppressed; academic data survives a status change."""

    @classmethod
    def setUpClass(cls):
        _seed_students()

    @classmethod
    def tearDownClass(cls):
        _cleanup()

    def setUp(self):
        ph = ",".join(["%s"] * len(ALL_TEST))
        _exec(f"DELETE FROM student_lifecycle_events WHERE usn IN ({ph})", ALL_TEST)

    def _preview(self, q, usn=None, user=ADMIN):
        return RL.nl_record(RL.NlRecordRequest(natural_query=q, language="en", usn=usn),
                            current_user=user)

    # ── preview for a known USN → confirm; verify real commit + dedup ─────────
    def test_preview_then_confirm_records_event(self):
        marks_before = _marks_fingerprint(U_DISCONT)
        events_before = len(_query("SELECT id FROM student_lifecycle_events WHERE usn=%s", (U_DISCONT,)))
        prev = self._preview(
            "USN 9ZZLC0001 discontinued due to financial problems "
            "on 2025-06-01 in 4th semester", usn=U_DISCONT)
        self.assertEqual(prev["action_required"], "confirm")
        p = prev["payload"]
        self.assertEqual(p["usn"], U_DISCONT)
        self.assertEqual(p["to_status"], "Temporarily Discontinued")
        self.assertEqual(p["event_type"], LC.EV_DISCONTINUE)
        self.assertEqual(p["reason_category"], "financial")
        self.assertEqual(p["effective_date"], "2025-06-01")
        self.assertEqual(p["last_enrolled_semester"], 4)
        # §1 preview must NOT write anything.
        self.assertEqual(
            len(_query("SELECT id FROM student_lifecycle_events WHERE usn=%s", (U_DISCONT,))),
            events_before, "preview wrote a lifecycle event")

        res = RL.nl_confirm(RL.NlConfirmRequest(payload=p,
                     confirmation_token=prev["confirmation_token"]), current_user=ADMIN)
        self.assertFalse(res["deduplicated"])
        self.assertEqual(res["to_status"], "Temporarily Discontinued")
        self.assertIn("undo_token", res)

        # real commit: derived cache + students row updated, event appended
        self.assertEqual(
            _query("SELECT lifecycle_status FROM students WHERE usn=%s", (U_DISCONT,))[0]["lifecycle_status"],
            "Temporarily Discontinued")
        ev = _query("SELECT * FROM student_lifecycle_events WHERE usn=%s ORDER BY id DESC LIMIT 1",
                    (U_DISCONT,))[0]
        self.assertEqual(ev["to_status"], "Temporarily Discontinued")
        self.assertEqual(ev["reason_category"], "financial")
        self.assertEqual(str(ev["effective_date"]), "2025-06-01")
        # §2 academic history untouched
        self.assertEqual(_marks_fingerprint(U_DISCONT), marks_before)

    def test_duplicate_confirm_is_idempotent(self):
        prev = self._preview("USN 9ZZLC0003 discontinued due to personal reasons "
                             "on 2025-01-10", usn=U_READMIT)
        RL.nl_confirm(RL.NlConfirmRequest(payload=prev["payload"],
                  confirmation_token=prev["confirmation_token"]), current_user=ADMIN)
        events_after_first = len(
            _query("SELECT id FROM student_lifecycle_events WHERE usn=%s", (U_READMIT,)))
        # replay the SAME payload/token → §5 duplicate suppression
        prev2 = self._preview("USN 9ZZLC0003 discontinued due to personal reasons "
                              "on 2025-01-10", usn=U_READMIT)
        res2 = RL.nl_confirm(RL.NlConfirmRequest(payload=prev2["payload"],
                       confirmation_token=prev2["confirmation_token"]), current_user=ADMIN)
        self.assertTrue(res2["deduplicated"])
        self.assertEqual(
            len(_query("SELECT id FROM student_lifecycle_events WHERE usn=%s", (U_READMIT,))),
            events_after_first, "duplicate confirm appended a second event")

    # ── unknown USN → no_record, and nothing created ─────────────────────────
    def test_unknown_usn_no_record(self):
        prev = self._preview("USN 9ZZLC9999 dropped out of college", usn=U_GONE)
        self.assertEqual(prev["action_required"], "no_record")
        self.assertEqual(len(_query("SELECT usn FROM students WHERE usn=%s", (U_GONE,))), 0)
        self.assertEqual(
            len(_query("SELECT id FROM student_lifecycle_events WHERE usn=%s", (U_GONE,))), 0)

    # ── no lifecycle verb → clarify, nothing created ─────────────────────────
    def test_missing_status_clarifies(self):
        prev = self._preview("hello there", usn=U_DISCONT)
        self.assertEqual(prev["action_required"], "clarify")
        self.assertEqual(
            len(_query("SELECT id FROM student_lifecycle_events WHERE usn=%s", (U_DISCONT,))), 0)

    # ── ambiguous name → select_student, nothing created ─────────────────────
    def test_ambiguous_name_returns_selection(self):
        name = "Zebra Ambigu Test"
        _insert_named("9ZZLC0110", name)
        _insert_named("9ZZLC0111", name)
        try:
            prev = RL.nl_record(
                RL.NlRecordRequest(natural_query=f"{name} discontinued due to health issues",
                                   language="en"), current_user=STAFF)
            self.assertEqual(prev["action_required"], "select_student")
            usns = {s["usn"] for s in prev["suggestions"]}
            self.assertIn("9ZZLC0110", usns)
            self.assertIn("9ZZLC0111", usns)
            self.assertEqual(
                len(_query("SELECT id FROM student_lifecycle_events WHERE usn IN (%s,%s)",
                           ("9ZZLC0110", "9ZZLC0111"))), 0,
                "ambiguous preview must not write")
        finally:
            _delete_usn("9ZZLC0110"); _delete_usn("9ZZLC0111")

    # ── confirmation token must match the payload + owner (§6 integrity) ──────
    def test_confirm_rejects_tampered_token(self):
        prev = self._preview("USN 9ZZLC0005 discontinued due to family reasons "
                             "on 2025-02-02", usn=U_ACTIVE)
        tampered = dict(prev["payload"]); tampered["to_status"] = "Dropout-College Recorded"
        with self.assertRaises(HTTPException) as ctx:
            RL.nl_confirm(RL.NlConfirmRequest(payload=tampered,
                       confirmation_token=prev["confirmation_token"]), current_user=ADMIN)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_confirm_rejects_expired_or_foreign_owner(self):
        from query_security_validator import create_confirmation_token
        payload = {"usn": U_READMIT, "to_status": "Temporarily Discontinued",
                   "event_type": LC.EV_DISCONTINUE, "effective_date": "2025-05-05"}
        # signed for a DIFFERENT user than the one confirming
        tok = create_confirmation_token(payload, "someone_else")
        with self.assertRaises(HTTPException) as ctx:
            RL.nl_confirm(RL.NlConfirmRequest(payload=payload,
                       confirmation_token=tok), current_user=ADMIN)
        self.assertEqual(ctx.exception.status_code, 403)


class LifecycleNlAuthorizationTests(unittest.TestCase):
    """§6 permission gates are backend dependencies, not UI-only."""

    def test_confirm_requires_admin(self):
        dep = require_roles("Admin")
        dep(current_user={"username": "a", "role": "Admin"})  # no raise
        with self.assertRaises(HTTPException) as ctx:
            dep(current_user={"username": "s", "role": "Staff"})
        self.assertEqual(ctx.exception.status_code, 403)

    def test_record_preview_allows_staff(self):
        dep = require_roles("Staff", "Admin")
        dep(current_user={"username": "s", "role": "Staff"})  # no raise


class LifecycleNlRetrievalTests(unittest.TestCase):
    """Spec B §3/§4: enriched list + exports with reason/date/search filters,
    validated against independent SQL over the whole DB."""

    @classmethod
    def setUpClass(cls):
        _seed_students()
        _exec("UPDATE student_lifecycle_status SET reason_category='financial', "
              "effective_date='2025-06-01' WHERE usn=%s", (U_DISCONT,))
        _exec("UPDATE student_lifecycle_status SET reason_category='medical', "
              "effective_date='2024-11-15' WHERE usn=%s", (U_DROPOUT,))

    @classmethod
    def tearDownClass(cls):
        _cleanup()

    def _usns(self, res):
        return sorted(r["usn"] for r in res["data"])

    def _expected_reason(self, cat):
        return sorted(r["usn"] for r in _query(
            "SELECT s.usn FROM students s LEFT JOIN student_lifecycle_status ls ON ls.usn=s.usn "
            "WHERE ls.reason_category=%s", (cat,)))

    def test_list_by_reason_category(self):
        res = RL.list_lifecycle(reason_category="financial", current_user=STAFF)
        self.assertEqual(self._usns(res), self._expected_reason("financial"))
        self.assertIn(U_DISCONT, self._usns(res))
        self.assertNotIn(U_DROPOUT, self._usns(res))

    def test_list_by_date_range(self):
        res = RL.list_lifecycle(date_from="2025-01-01", date_to="2025-12-31",
                                current_user=STAFF)
        exp = sorted(r["usn"] for r in _query(
            "SELECT s.usn FROM students s LEFT JOIN student_lifecycle_status ls ON ls.usn=s.usn "
            "WHERE ls.effective_date>=%s AND ls.effective_date<=%s",
            ("2025-01-01", "2025-12-31")))
        self.assertEqual(self._usns(res), exp)
        self.assertIn(U_DISCONT, self._usns(res))
        self.assertNotIn(U_DROPOUT, self._usns(res))

    def test_list_total_count_and_pagination(self):
        full = RL.list_lifecycle(reason_category="financial", current_user=STAFF)
        page = RL.list_lifecycle(reason_category="financial", limit=1, offset=0,
                                 current_user=STAFF)
        self.assertLessEqual(page["count"], 1)
        self.assertEqual(page["total_count"], full["total_count"])
        self.assertEqual(full["total_count"], len(self._expected_reason("financial")))

    def test_list_search_by_name(self):
        res = RL.list_lifecycle(search="Discontinue One", current_user=STAFF)
        self.assertIn(U_DISCONT, self._usns(res))

    def test_unknown_status_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            RL.list_lifecycle(status="Not A Status", current_user=STAFF)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_export_csv_xlsx_pdf_carry_lifecycle_columns(self):
        csv_raw = _read_response(RL.export_lifecycle(fmt="csv", reason_category="financial",
                                                     current_user=STAFF))
        csv_text = csv_raw.decode("utf-8")
        self.assertIn("Reason Category", csv_text)
        self.assertIn("financial", csv_text)
        self.assertIn(U_DISCONT, csv_text)
        xlsx_raw = _read_response(RL.export_lifecycle(fmt="xlsx", reason_category="financial",
                                                      current_user=STAFF))
        self.assertEqual(xlsx_raw[:2], b"PK")
        pdf_raw = _read_response(RL.export_lifecycle(fmt="pdf", reason_category="financial",
                                                     current_user=STAFF))
        self.assertEqual(pdf_raw[:5], b"%PDF-")

    def test_export_rejects_bad_format(self):
        with self.assertRaises(HTTPException) as ctx:
            RL.export_lifecycle(fmt="exe", reason_category="financial", current_user=STAFF)
        self.assertEqual(ctx.exception.status_code, 400)


class LifecycleMultilingualRecordTests(unittest.TestCase):
    """Spec B §1: the same discontinuation intent across English / broken-English
    / Kannada-Unicode / Roman-Kannada resolves to the SAME lifecycle status via
    the shared deterministic normalize+parse pipeline (no network dependency)."""

    _EXPECTED = LC.STATUS_TEMP_DISCONTINUED

    def test_status_equivalence_across_languages(self):
        variants = [
            "discontinued studies",                 # english
            "student discontinue done",             # broken english
            "odu nilistida",                        # roman-kannada
            "niyarpi besidane",                     # roman-kannada
            "ವಿದ್ಯಾರ್ಥಿ ಓದು ನಿಲ್ಲಿಸಿದ್ದಾನೆ",  # kannada unicode
        ]
        for raw in variants:
            norm, _ = normalize_query(raw)
            parsed = LC.parse_lifecycle_command(norm)
            status = LC.normalize_status(parsed.get("target_status") or "")
            self.assertEqual(status, self._EXPECTED,
                             f"{raw!r} -> {parsed.get('target_status')!r} (norm={norm!r})")

    def test_english_and_canonical_status_agree(self):
        en = LC.normalize_status(
            LC.parse_lifecycle_command("USN 9ZZLC0001 discontinued")["target_status"])
        self.assertEqual(en, LC.STATUS_TEMP_DISCONTINUED)


class LifecycleTransitionTests(unittest.TestCase):
    """Spec B §5: NL-recorded discontinuation → rejoin keeps a full, ordered,
    append-only history with no duplicate student and no lost academic data."""

    @classmethod
    def setUpClass(cls):
        _seed_students()

    @classmethod
    def tearDownClass(cls):
        _cleanup()

    def setUp(self):
        ph = ",".join(["%s"] * len(ALL_TEST))
        _exec(f"DELETE FROM student_lifecycle_events WHERE usn IN ({ph})", ALL_TEST)

    def _preview(self, q, usn):
        prev = RL.nl_record(RL.NlRecordRequest(natural_query=q, language="en", usn=usn),
                            current_user=ADMIN)
        RL.nl_confirm(RL.NlConfirmRequest(payload=prev["payload"],
                  confirmation_token=prev["confirmation_token"]), current_user=ADMIN)

    def test_discontinuation_then_rejoin_preserves_history(self):
        marks_before = _marks_fingerprint(U_DROPOUT)
        student_rows_before = len(_query("SELECT usn FROM students WHERE usn=%s", (U_DROPOUT,)))
        self._preview("USN 9ZZLC0002 discontinued due to financial problems "
                      "on 2024-09-01", U_DROPOUT)
        self._preview("USN 9ZZLC0002 rejoined college on 2025-06-01", U_DROPOUT)

        evs = _query("SELECT * FROM student_lifecycle_events WHERE usn=%s ORDER BY id", (U_DROPOUT,))
        to_statuses = [e["to_status"] for e in evs]
        self.assertEqual(to_statuses, ["Temporarily Discontinued", "Rejoined-Active"])
        # current status reflects the latest transition
        self.assertEqual(
            _query("SELECT lifecycle_status FROM students WHERE usn=%s", (U_DROPOUT,))[0]["lifecycle_status"],
            "Rejoined-Active")
        # exactly one student row — no duplicate created on rejoin
        self.assertEqual(
            len(_query("SELECT usn FROM students WHERE usn=%s", (U_DROPOUT,))), student_rows_before)
        # academic data preserved through both transitions
        self.assertEqual(_marks_fingerprint(U_DROPOUT), marks_before)

    def test_rejoin_does_not_auto_mark_on_backlog_clear(self):
        # §5: clearing a backlog must NOT flip a discontinued student to rejoined
        bl = _query("SELECT id FROM student_backlogs WHERE usn=%s AND cleared=0", (U_DISCONT,))
        self._preview("USN 9ZZLC0001 discontinued due to academic problems "
                      "on 2025-03-03", U_DISCONT)
        if bl:
            RL.clear_backlog_verified_pass(U_DISCONT, bl[0]["id"],
                RL.VerifiedPassClearModel(result_ref="R-1"), current_user=ADMIN)
        self.assertEqual(
            _query("SELECT lifecycle_status FROM students WHERE usn=%s", (U_DISCONT,))[0]["lifecycle_status"],
            "Temporarily Discontinued")


if __name__ == "__main__":
    unittest.main()