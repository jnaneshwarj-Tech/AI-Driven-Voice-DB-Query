"""Master QA Phase 7 — permissions, the role policy and the PII mask.

What is pinned here is the part an HTTP probe cannot re-check on every future
run: one shared role policy for personal data, the doors that must refuse a
Viewer, undo ownership, the login brute-force guard and the audit/query-history
scoping. Expectations are computed in this process from the row that MySQL
holds, never from what the application chooses to answer.

The suite runs with MYSQL_DB=student_db_staging; only synthetic `9QQ…` USNs and
synthetic audit rows are written, and each test removes what it inserted.

Run:
    MYSQL_DB=student_db_staging PYTHONIOENCODING=utf-8 \\
        ./.venv/Scripts/python.exe -m unittest tests.test_master_phase7_security
"""
import datetime as dt
import os
import sys
import unittest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from fastapi import HTTPException

from database import db_conn
from auth import create_access_token, get_current_user
import auth as AUTH
import report_service as RS
import routes_auth
import routes_undo

ADMIN = {"username": "p7_admin", "role": "Admin"}
STAFF = {"username": "p7_staff", "role": "Staff"}
VIEWER = {"username": "p7_viewer", "role": "Viewer"}

USN = "9QQ24CS991"
AADHAR = "987654321098"
PHONE = "9000011122"
EMAIL = "probe.student@college.edu"


def rows(sql, params=()):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, list(params))
        out = cur.fetchall()
        cur.close()
    return out


def student_row():
    return {
        "usn": USN, "name": "Probe Student", "aadhar_no": AADHAR,
        "phone": PHONE, "email": EMAIL, "parents_phone": "9333344445",
        "emergency_contact_number": "9444455556", "district": "Kolar",
    }


def role_names(masked, original):
    return {k for k, v in masked.items()
            if k in original and str(v) != str(original[k]) and v is not None}


class MaskPolicyTest(unittest.TestCase):
    """One policy, applied everywhere personal data leaves the server."""

    def test_admin_is_the_only_role_that_sees_values_in_full(self):
        row = student_row()
        self.assertEqual(RS.mask_for_role(row, "Admin"), row)
        for role in ("Staff", "Viewer"):
            masked = RS.mask_for_role(row, role)
            for field in ("aadhar_no", "phone", "email", "parents_phone",
                          "emergency_contact_number"):
                self.assertNotEqual(str(masked[field]), str(row[field]),
                                    f"{role} must not read {field} in full")
            self.assertEqual(masked["name"], row["name"],
                             "a name is not sensitive and must stay readable")

    def test_only_the_tail_of_a_number_survives_the_mask(self):
        masked = RS.mask_for_role(student_row(), "Viewer")
        self.assertTrue(masked["aadhar_no"].endswith(AADHAR[-4:]))
        self.assertTrue(set(masked["aadhar_no"][:-4]) == {"*"})
        self.assertTrue(masked["phone"].endswith(PHONE[-4:]))

    def test_email_keeps_its_domain_but_not_its_local_part(self):
        masked = RS.mask_for_role(student_row(), "Viewer")
        self.assertTrue(masked["email"].endswith("@college.edu"))
        self.assertNotIn("probe.student", masked["email"])

    def test_a_contact_column_named_by_a_workbook_is_masked_too(self):
        """Sheet columns arrive with whatever heading the office typed."""
        row = {"usn": USN, "mahati_number": "9555566667",
               "whatsapp": "9666677778", "student_phone": "9777788889"}
        masked = RS.mask_for_role(row, "Viewer")
        for field in ("mahati_number", "whatsapp", "student_phone"):
            self.assertNotEqual(str(masked[field]), str(row[field]),
                                f"{field} is a contact number and must be masked")

    def test_staff_edit_exception_reveals_contacts_but_never_the_aadhaar(self):
        row = student_row()
        edit = RS.mask_for_role(row, "Staff", edit_context=True)
        self.assertEqual(str(edit["phone"]), str(row["phone"]),
                         "the clerk correcting a mistyped number must read it")
        self.assertEqual(str(edit["aadhar_no"])[:8], "*" * 8,
                         "no one at a counter needs to retype an Aadhaar")
        # A Viewer is never in an edit context: the exception is Staff only.
        self.assertNotEqual(str(RS.mask_for_role(row, "Viewer", edit_context=True)["phone"]),
                            str(row["phone"]))

    def test_change_history_values_follow_the_same_policy(self):
        self.assertEqual(RS.mask_value_for_role("phone", PHONE, "Staff"),
                         RS.mask_for_role({"phone": PHONE}, "Staff")["phone"])
        self.assertEqual(RS.mask_value_for_role("name", "Probe", "Viewer"), "Probe")
        self.assertTrue(RS.is_sensitive_field("aadhar_no"))
        self.assertTrue(RS.is_sensitive_field("Parents Phone"))
        self.assertFalse(RS.is_sensitive_field("branch"))


class HistoryEndpointTest(unittest.TestCase):
    """GET /api/undo/history/{usn} quotes old and new values; it must mask them."""

    def setUp(self):
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM student_history WHERE usn=%s", (USN,))
            cur.execute(
                "INSERT INTO student_history (usn, field_name, old_value, new_value, "
                "updated_by) VALUES (%s,'phone',%s,%s,'p7_staff'),"
                "(%s,'aadhar_no',%s,%s,'p7_staff'),"
                "(%s,'district','Kolar','Hassan','p7_staff')",
                (USN, "9000000000", PHONE, USN, "111122223333", AADHAR, USN))
            conn.commit()
            cur.close()

    def tearDown(self):
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM student_history WHERE usn=%s", (USN,))
            conn.commit()
            cur.close()

    def test_viewer_sees_no_full_value_of_a_contact_field(self):
        out = routes_undo.get_student_history(USN, dict(VIEWER))
        by_field = {r["field_name"]: r for r in out}
        self.assertIn("phone", by_field)
        for key in ("old_value", "new_value"):
            self.assertNotIn(str(PHONE), str(by_field["phone"][key]))
            self.assertNotIn(str(AADHAR), str(by_field["aadhar_no"][key]))
        self.assertEqual(by_field["district"]["new_value"], "Hassan",
                         "an ordinary field is shown as it was recorded")

    def test_admin_sees_the_history_the_table_holds(self):
        by_field = {r["field_name"]: r
                    for r in routes_undo.get_student_history(USN, dict(ADMIN))}
        self.assertEqual(str(by_field["phone"]["new_value"]), PHONE)


class TableReportMaskingTest(unittest.TestCase):
    """A report is built from rows the browser posted; the server still decides."""

    def test_student_list_report_masks_what_the_client_handed_in(self):
        posted = [dict(student_row())]
        for user in (STAFF, VIEWER):
            model = RS.build_table_report_model(posted, user, "student_list")
            record = model["records"][0]
            self.assertNotIn(AADHAR, str(record),
                             f"{user['role']} must not get a full Aadhaar in a report")
            self.assertNotIn(PHONE, str(record),
                             f"{user['role']} must not get a full phone in a report")
        admin = RS.build_table_report_model(posted, ADMIN, "student_list")["records"][0]
        self.assertIn(AADHAR, str(admin),
                      "Admin keeps the values, so the check above is not vacuous")


class UndoOwnershipTest(unittest.TestCase):
    def test_an_undo_belongs_to_the_operator_who_made_the_change(self):
        rec = {"operation_type": "UPDATE", "performed_by": "p7_staff"}
        self.assertTrue(routes_undo._may_act_on_undo(rec, {"username": "p7_staff",
                                                           "role": "Staff"}))
        self.assertFalse(routes_undo._may_act_on_undo(rec, {"username": "p7_admin",
                                                           "role": "Admin"}),
                         "Admin is not above the operator's own rollback of a data edit")
        self.assertFalse(routes_undo._may_act_on_undo(rec, VIEWER))

    def test_a_file_trash_restore_is_admin_managed(self):
        rec = {"operation_type": "FILE_DELETE", "performed_by": "p7_staff"}
        self.assertTrue(routes_undo._may_act_on_undo(rec, {"username": "p7_admin",
                                                           "role": "Admin"}))
        self.assertFalse(routes_undo._may_act_on_undo(rec, {"username": "p7_staff",
                                                           "role": "Staff"}),
                         "the person who deleted a file is not the one who restores it")


class LoginThrottleTest(unittest.TestCase):
    USER = "p7thrash"

    def tearDown(self):
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM audit_log WHERE action='LOGIN_FAILED' "
                        "AND username=%s", (self.USER,))
            conn.commit()
            cur.close()

    def _seed_failures(self, count):
        with db_conn() as conn:
            cur = conn.cursor()
            for _ in range(count):
                cur.execute(
                    "INSERT INTO audit_log (username, role, action, target_table, "
                    "summary, success, created_at) "
                    "VALUES (%s,'','LOGIN_FAILED','','seeded by test',0, "
                    "DATE_SUB(NOW(), INTERVAL 1 MINUTE))", (self.USER,))
            conn.commit()
            cur.close()

    def test_a_wrong_password_fails_once_without_locking_anyone(self):
        with self.assertRaises(HTTPException) as held:
            routes_auth.login(routes_auth.LoginRequest(
                username=self.USER, password="definitely-not-it"))
        self.assertEqual(held.exception.status_code, 401)

    def test_repeated_failures_on_one_account_are_refused_before_checking(self):
        self._seed_failures(routes_auth.LOGIN_MAX_FAILURES)
        with self.assertRaises(HTTPException) as held:
            routes_auth.login(routes_auth.LoginRequest(
                username=self.USER, password="definitely-not-it"))
        self.assertEqual(held.exception.status_code, 429)
        self.assertIn("Retry-After", getattr(held.exception, "headers", {}) or {})

    def test_the_guard_is_a_window_and_not_a_permanent_lockout(self):
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO audit_log (username, role, action, target_table, summary, "
                "success, created_at) VALUES (%s,'','LOGIN_FAILED','','older',"
                "0, DATE_SUB(NOW(), INTERVAL %s MINUTE))",
                (self.USER, routes_auth.LOGIN_WINDOW_MINUTES + 5))
            conn.commit()
            cur.close()
        try:
            routes_auth.login(routes_auth.LoginRequest(
                username=self.USER, password="definitely-not-it"))
            self.fail("an unknown account should never reach the token step")
        except HTTPException as held:
            self.assertEqual(held.status_code, 401,
                             "failures older than the window must not keep an "
                             "account locked out")


class RouteGuardInventoryTest(unittest.TestCase):
    """The dependency graph is the real authorisation table — read it."""

    PUBLIC = {"/", "/api/auth/login", "/api/auth/register", "/api/auth/forgot-password",
              "/api/auth/verify-reset-otp", "/api/auth/reset-password"}

    @classmethod
    def setUpClass(cls):
        import main
        cls.routes = []
        cls._collect(main.app.routes)

    @classmethod
    def _collect(cls, routes):
        for r in routes:
            original = getattr(r, "original_router", None)   # this build wraps routers
            if original is not None:
                cls._collect(original.routes)
                continue
            cls.routes.append(r)

    @staticmethod
    def _dependency_calls(route):
        found = []

        def walk(dep):
            if dep is None:
                return
            call = getattr(dep, "call", None)
            if callable(call):
                found.append(call)
            for sub in getattr(dep, "dependencies", []) or []:
                walk(sub)

        walk(getattr(route, "dependant", None))
        return found

    def _guard(self, route):
        for call in self._dependency_calls(route):
            if call is get_current_user:
                return {"*"}
            if getattr(call, "__name__", "") == "role_dependency":
                for cell in (call.__closure__ or ()):
                    try:
                        value = cell.cell_contents
                    except ValueError:
                        continue
                    if isinstance(value, (set, frozenset)) and value and all(
                            str(x).lower() in {"admin", "staff", "viewer"}
                            for x in value):
                        return {str(x).title() for x in value}
        return None

    def test_every_data_door_requires_a_token(self):
        unguarded = sorted({(r.path, ",".join(sorted(getattr(r, "methods", []) or [])))
                            for r in self.routes
                            if getattr(r, "path", "").startswith("/api/")
                            and r.path not in self.PUBLIC
                            and self._guard(r) is None})
        self.assertEqual(unguarded, [], "these endpoints answer without any auth")

    def test_write_and_operations_doors_are_not_open_to_a_viewer(self):
        must_refuse_viewer = [
            ("/api/undo/restore/{token}", "POST"),
            ("/api/query/sync-vtu", "POST"),
            ("/api/monitor/db-stats", "GET"),
            ("/api/monitor/performance", "GET"),
            ("/api/backup/audit-log", "GET"),
            ("/api/backup/upload-versions", "GET"),
            ("/api/backup/storage-status", "GET"),
        ]
        by_key = {(r.path, m): r for r in self.routes
                  for m in (getattr(r, "methods", None) or [])}
        for path, method in must_refuse_viewer:
            route = by_key.get((path, method))
            self.assertIsNotNone(route, f"{method} {path} is missing")
            guard = self._guard(route)
            self.assertIsNotNone(guard, f"{method} {path} has no auth dependency")
            self.assertNotIn("Viewer", guard,
                             f"{method} {path} still accepts a Viewer ({guard})")

    def test_the_api_schema_is_not_published_unauthenticated_by_default(self):
        paths = {getattr(r, "path", "") for r in self.routes}
        if os.getenv("API_DOCS", "").strip().lower() in ("1", "true", "yes"):
            self.skipTest("this run deliberately opened the docs with API_DOCS")
        for hidden in ("/docs", "/redoc", "/openapi.json"):
            self.assertNotIn(hidden, paths, f"{hidden} is reachable without a token")


class TokenHygieneTest(unittest.TestCase):
    def test_a_token_signed_with_another_key_is_not_accepted(self):
        from jose import jwt as _jwt
        forged = _jwt.encode({"sub": "p7_admin", "role": "Admin"}, "not-the-secret",
                             algorithm="HS256")
        with self.assertRaises(HTTPException):
            get_current_user(forged)

    def test_a_none_algorithm_token_is_not_accepted(self):
        import base64
        import json as _json

        def b64(value):
            return base64.urlsafe_b64encode(
                _json.dumps(value).encode()).rstrip(b"=").decode()

        forged = f"{b64({'alg': 'none', 'typ': 'JWT'})}." \
                 f"{b64({'sub': 'p7_admin', 'role': 'Admin'})}."
        with self.assertRaises(HTTPException):
            get_current_user(forged)

    def test_an_empty_secret_refuses_to_issue_a_token(self):
        # settings is a frozen pydantic model, so the module pointer is swapped,
        # not the field: what is under test is the guard, not the config object.
        class _NoSecret:
            JWT_SECRET_KEY = "   "
            JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 5

        original = AUTH.settings
        try:
            AUTH.settings = _NoSecret()
            with self.assertRaises(HTTPException) as held:
                create_access_token({"sub": "p7_admin", "role": "Admin"})
            self.assertEqual(held.exception.status_code, 503)
            with self.assertRaises(HTTPException) as held:
                get_current_user("anything")
            self.assertEqual(held.exception.status_code, 503,
                             "with no secret configured, no token can be trusted")
        finally:
            AUTH.settings = original

class QueryCachePrivacyTest(unittest.TestCase):
    """A saved answer is reused across roles; the copy must not leak."""

    def test_history_is_scoped_to_the_callers_role(self):
        import routes_query
        marker = f"p7 probe question {int(dt.datetime.now().timestamp())}"
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO query_history (natural_query, generated_query, "
                "user_role) VALUES (%s,'SELECT 1','Admin')", (marker,))
            conn.commit()
            cur.close()
        try:
            admin_rows = routes_query.get_history(
                limit=500, current_user=dict(ADMIN))
            staff_rows = routes_query.get_history(
                limit=500, current_user=dict(STAFF))
            self.assertTrue(any(r["natural_query"] == marker for r in admin_rows),
                            "Admin is the auditor and sees the trail")
            self.assertFalse(any(r["natural_query"] == marker for r in staff_rows),
                             "a question is another operator's working notes")
        finally:
            with db_conn() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM query_history WHERE natural_query=%s",
                            (marker,))
                conn.commit()
                cur.close()


class ReadingRoleAccessTest(unittest.TestCase):
    """A Viewer is a reader: the NL door must answer them, and only them-masked."""

    def setUp(self):
        from query_security_validator import validate_sql_query
        self.validate = validate_sql_query

    def test_a_viewer_select_passes_the_security_validator(self):
        plan = {"operation": "select",
                "sql": "SELECT * FROM students WHERE usn=%s", "params": [USN]}
        for role in ("Admin", "Staff", "Viewer", "Student"):
            got = self.validate(dict(plan), role)
            self.assertTrue(got["is_valid"], f"{role}: {got['reason']}")

    def test_a_viewer_is_refused_because_of_the_role_and_not_the_wording(self):
        for op, sql in (("update", "UPDATE students SET phone=%s WHERE usn=%s"),
                        ("insert", "INSERT INTO students (usn, name) VALUES (%s, %s)")):
            got = self.validate({"operation": op, "sql": sql, "params": []}, "Viewer")
            self.assertFalse(got["is_valid"], sql)
            self.assertIn("Role", got["reason"],
                          f"a reader must be refused on the role, not the sentence: {got}")

    def test_the_write_rules_still_hold_for_staff_and_admin(self):
        staff_delete = self.validate(
            {"operation": "delete", "sql": "DELETE FROM students WHERE usn=%s",
             "params": [USN]}, "Staff")
        self.assertFalse(staff_delete["is_valid"])
        self.assertIn("Admin", staff_delete["reason"])


class RouteShadowingTest(unittest.TestCase):
    """FastAPI matches in declaration order, so a static path written after a
    dynamic one at the same position is never reachable (D60: /profile/search
    was swallowed by /profile/{usn} and answered 'Student not found' forever)."""

    @classmethod
    def setUpClass(cls):
        import main
        import re as _re
        cls.routes = []
        cls._collect(main.app.routes)
        cls._re = _re

    @classmethod
    def _collect(cls, routes):
        for r in routes:
            original = getattr(r, "original_router", None)
            if original is not None:
                cls._collect(original.routes)
                continue
            if getattr(r, "path", None):
                cls.routes.append(r)

    def test_no_declared_path_is_swallowed_by_an_earlier_parameterised_one(self):
        def regex(path):
            return "^" + self._re.sub(r"\{[^/}]+\}", "[^/]+", path) + "$"

        shadowed = []
        for i, earlier in enumerate(self.routes):
            if "{" not in getattr(earlier, "path", ""):
                continue
            compiled = self._re.compile(regex(earlier.path))
            methods = set(getattr(earlier, "methods", []) or [])
            for later in self.routes[:0] + self.routes[i + 1:]:
                lp = getattr(later, "path", "")
                if "{" in lp or lp == earlier.path:
                    continue
                if not (set(getattr(later, "methods", []) or []) & methods):
                    continue
                if compiled.match(lp):
                    shadowed.append(f"{sorted(methods)} {lp} is hidden behind {earlier.path}")
        self.assertEqual(shadowed, [], "\n".join(shadowed))

    def test_the_name_search_door_is_the_one_that_answers(self):
        """Walk the routes the way the framework does: the first GET that matches
        /api/query/profile/search must be the search handler, not the USN one."""
        import routes_query
        winner = None
        for r in self.routes:
            if not (set(getattr(r, "methods", []) or []) & {"GET"}):
                continue
            if self._re.compile("^" + self._re.sub(r"\{[^/}]+\}", "[^/]+", r.path) + "$"
                                ).match("/api/query/profile/search"):
                winner = r
                break
        self.assertIsNotNone(winner, "no door matches the search URL at all")
        self.assertIs(winner.endpoint, routes_query.search_student_profiles,
                      f"{winner.path} resolves first and swallows the search door")


class OtpLogProductionGateTest(unittest.TestCase):
    """Without SMTP the reset code used to be printed to the console and the
    request reported as delivered — in production that puts a live password
    reset token in the server log and tells the user to watch their inbox."""

    def _send(self, app_env, mail_user="   ", mail_pass=""):
        import email_service
        import os
        real = (email_service.settings.MAIL_USERNAME, email_service.settings.MAIL_PASSWORD)
        env = os.environ.get("APP_ENV")
        email_service.settings.MAIL_USERNAME = mail_user
        email_service.settings.MAIL_PASSWORD = mail_pass
        os.environ["APP_ENV"] = app_env
        try:
            return email_service.send_otp_email("probe@college.edu", "p7probe", "123456")
        except email_service.EmailDeliveryError as exc:
            return exc
        finally:
            (email_service.settings.MAIL_USERNAME,
             email_service.settings.MAIL_PASSWORD) = real
            if env is None:
                os.environ.pop("APP_ENV", None)
            else:
                os.environ["APP_ENV"] = env

    def test_production_without_smtp_refuses_instead_of_logging_the_code(self):
        got = self._send("production")
        self.assertIsInstance(got, email_err(), str(got)[:120])
        self.assertNotIn("123456", str(got))

    def test_development_still_prints_the_code_for_the_developer(self):
        self.assertIsNone(self._send("development"))


def email_err():
    import email_service
    return email_service.EmailDeliveryError


if __name__ == "__main__":
    unittest.main(verbosity=2)
