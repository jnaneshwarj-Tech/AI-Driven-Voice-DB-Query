"""
Field & Fee update tests (spec: "fill any blank field", "update fee status",
"discontinue/dropout and reverse", "test every possibility of update").

Safety (per project constraints):
  * Only synthetic test USNs (prefix "9ZZUP") are ever inserted or mutated.
  * Expected values are read back independently from MySQL, never from the code
    under test.
  * Teardown removes only rows carrying the synthetic test USNs.
"""
import io
import os
import sys
import unittest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

# This module prints only ASCII, so it deliberately does NOT re-wrap sys.stdout
# (some sibling test modules already redirect it; wrapping again can close the
# shared buffer mid-run). Keep stdout exactly as the rest of the suite left it.

from fastapi import HTTPException

import lifecycle as LC
import routes_update as RU
from auth import require_roles
from database import db_conn
from routes_query import _is_searchbar_lifecycle_record
from routes_undo import restore_student

ADMIN = {"username": "up_admin", "role": "Admin"}
STAFF = {"username": "up_staff", "role": "Staff"}
VIEWER = {"username": "up_viewer", "role": "Student"}

U_A = "9ZZUP0001"   # blank email/phone, one unpaid VTU fee + tuition
U_B = "9ZZUP0002"   # for bulk + identifier-block cases
U_GONE = "9ZZUP9999"
ALL_TEST = [U_A, U_B, U_GONE]


def _exec(sql, params=()):
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, list(params))
        conn.commit()
        cur.close()


def _query(sql, params=()):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, list(params))
        rows = cur.fetchall()
        cur.close()
    return rows


def _fee_status(usn, fee_type, year):
    rows = _query("SELECT status FROM student_fees WHERE usn=%s AND fee_type=%s AND year=%s",
                  (usn, fee_type, year))
    return rows[0]["status"] if rows else None


def _seed():
    _cleanup()
    with db_conn() as conn:
        cur = conn.cursor()
        for usn, name in ((U_A, "Update One"), (U_B, "Update Two")):
            cur.execute(
                "INSERT INTO students (usn, name, gender, branch, admission_year, email, phone) "
                "VALUES (%s,%s,'Male','CSE',2023,NULL,NULL)", (usn, name))
        cur.execute(
            "UPDATE students SET dob=%s WHERE usn=%s", ("2005-05-05", U_A))
        conn.commit()
        cur.close()
    # VTU year1 unpaid, tuition remaining — will be flipped by the fee tests
    _exec("INSERT INTO student_fees (usn, fee_type, year, status, amount_paid, remaining_amount) "
          "VALUES (%s,'VTU',1,'Not Paid','0','5000')", (U_A,))
    _exec("INSERT INTO student_fees (usn, fee_type, year, status) VALUES (%s,'TUITION_REMAINING',0,'No')",
          (U_A,))


def _cleanup():
    with db_conn() as conn:
        cur = conn.cursor()
        ph = ",".join(["%s"] * len(ALL_TEST))
        for tbl in ("students", "marks", "student_fees", "student_history",
                    "student_lifecycle_status", "student_lifecycle_events"):
            cur.execute(f"DELETE FROM {tbl} WHERE usn IN ({ph})", ALL_TEST)
        cur.execute("DELETE FROM audit_log WHERE target_id IN (%s)" % ph, ALL_TEST)
        conn.commit()
        cur.close()


class FieldEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _seed()

    @classmethod
    def tearDownClass(cls):
        _cleanup()

    def setUp(self):
        _seed()

    def test_fill_blank_field(self):
        self.assertIsNone(_query("SELECT email FROM students WHERE usn=%s", (U_A,))[0]["email"])
        res = RU.update_field(
            RU.FieldUpdateRequest(usn=U_A, field="email", value="a@b.com", confirm=True),
            current_user=STAFF)
        self.assertEqual(res["changed"][0]["column"], "email")
        self.assertEqual(_query("SELECT email FROM students WHERE usn=%s", (U_A,))[0]["email"], "a@b.com")

    def test_update_existing_value(self):
        RU.update_field(RU.FieldUpdateRequest(usn=U_A, field="phone", value="9876543210",
                                              confirm=True), current_user=STAFF)
        RU.update_field(RU.FieldUpdateRequest(usn=U_A, field="phone", value="9111111111",
                                              confirm=True), current_user=STAFF)
        self.assertEqual(_query("SELECT phone FROM students WHERE usn=%s", (U_A,))[0]["phone"],
                         "9111111111")

    def test_confirmation_required(self):
        with self.assertRaises(HTTPException) as ctx:
            RU.update_field(RU.FieldUpdateRequest(usn=U_A, field="email", value="x@y.com",
                                                  confirm=False), current_user=STAFF)
        self.assertEqual(ctx.exception.status_code, 428)

    def test_empty_value_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            RU.update_field(RU.FieldUpdateRequest(usn=U_A, field="email", value="   ",
                                                  confirm=True), current_user=STAFF)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_invalid_email_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            RU.update_field(RU.FieldUpdateRequest(usn=U_A, field="email", value="not-an-email",
                                                  confirm=True), current_user=STAFF)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_identifier_and_lifecycle_columns_blocked(self):
        for field in ("usn", "status", "lifecycle_status", "id"):
            with self.assertRaises(HTTPException, msg=field) as ctx:
                RU.update_field(RU.FieldUpdateRequest(usn=U_A, field=field, value="zzz",
                                                      confirm=True), current_user=STAFF)
            self.assertEqual(ctx.exception.status_code, 400)

    def test_unknown_field_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            RU.update_field(RU.FieldUpdateRequest(usn=U_A, field="quantum_spin", value="1",
                                                  confirm=True), current_user=STAFF)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_missing_student_404(self):
        with self.assertRaises(HTTPException) as ctx:
            RU.update_field(RU.FieldUpdateRequest(usn=U_GONE, field="email", value="a@b.com",
                                                  confirm=True), current_user=STAFF)
        self.assertIn(ctx.exception.status_code, (404, 400))

    def test_write_requires_staff_or_admin(self):
        dep = require_roles("Staff", "Admin")
        # Viewer is rejected by the dependency itself.
        with self.assertRaises(HTTPException) as ctx:
            dep(current_user=VIEWER)
        self.assertEqual(ctx.exception.status_code, 403)
        # Staff/Admin pass.
        self.assertEqual(dep(current_user=STAFF)["role"], "Staff")
        self.assertEqual(dep(current_user=ADMIN)["role"], "Admin")

    def test_undo_reverts_field(self):
        _exec("UPDATE students SET village=%s WHERE usn=%s", (None, U_B))
        res = RU.update_field(RU.FieldUpdateRequest(usn=U_B, field="village", value="Hubballi",
                                                    confirm=True), current_user=STAFF)
        self.assertEqual(_query("SELECT village FROM students WHERE usn=%s", (U_B,))[0]["village"],
                         "Hubballi")
        restore_student(res["undo_token"], current_user=STAFF)
        self.assertIsNone(_query("SELECT village FROM students WHERE usn=%s", (U_B,))[0]["village"])

    def test_bulk_updates_many_but_skips_blanks(self):
        res = RU.update_bulk(
            RU.BulkFieldUpdateRequest(
                usn=U_B, fields={"taluk": "Hubballi", "district": "", "state": "Karnataka"},
                confirm=True), current_user=STAFF)
        cols = {c["column"] for c in res["changed"]}
        self.assertIn("taluk", cols)
        self.assertIn("state", cols)
        self.assertNotIn("district", cols)
        self.assertEqual(_query("SELECT district FROM students WHERE usn=%s", (U_B,))[0]["district"], None)

    def test_editable_fields_schema(self):
        schema = RU.get_editable_fields(U_A, current_user=STAFF)
        names = {f["column"] for f in schema["editable_fields"]}
        self.assertNotIn("usn", names)
        self.assertNotIn("lifecycle_status", names)
        self.assertIn("email", names)


class FeeEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _seed()

    @classmethod
    def tearDownClass(cls):
        _cleanup()

    def setUp(self):
        _seed()

    def test_admin_updates_vtu_status(self):
        req = RU.FeeUpdateRequest(usn=U_A, confirm=True,
                                  fees=[RU.FeeRow(fee_type="VTU", year=1, status="Paid")])
        res = RU.update_fees(req, current_user=ADMIN)
        self.assertEqual(res["results"][0]["verified_label"], "Paid")
        self.assertEqual(_fee_status(U_A, "VTU", 1), "Paid")

    def test_partial_to_paid_yearwise(self):
        RU.update_fees(RU.FeeUpdateRequest(usn=U_A, confirm=True,
                     fees=[RU.FeeRow(fee_type="VTU", year=1, status="Partially Paid")]), current_user=ADMIN)
        self.assertEqual(_fee_status(U_A, "VTU", 1), "Partially Paid")
        RU.update_fees(RU.FeeUpdateRequest(usn=U_A, confirm=True,
                     fees=[RU.FeeRow(fee_type="VTU", year=1, status="Paid", amount_paid="5000")]),
                     current_user=ADMIN)
        self.assertEqual(_fee_status(U_A, "VTU", 1), "Paid")

    def test_tuition_admin_only_field(self):
        RU.update_fees(RU.FeeUpdateRequest(usn=U_A, confirm=True,
                     fees=[RU.FeeRow(fee_type="TUITION_REMAINING", year=0, status="No")]),
                     current_user=ADMIN)
        self.assertEqual(_fee_status(U_A, "TUITION_REMAINING", 0), "No")

    def test_fee_update_requires_admin(self):
        dep = require_roles("Admin")
        with self.assertRaises(HTTPException) as ctx:
            dep(current_user=STAFF)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_fee_confirmation_required(self):
        with self.assertRaises(HTTPException) as ctx:
            RU.update_fees(RU.FeeUpdateRequest(usn=U_A, confirm=False,
                         fees=[RU.FeeRow(fee_type="VTU", year=1, status="Paid")]), current_user=ADMIN)
        self.assertEqual(ctx.exception.status_code, 428)

    def test_unknown_fee_type_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            RU.update_fees(RU.FeeUpdateRequest(usn=U_A, confirm=True,
                         fees=[RU.FeeRow(fee_type="LIBRARY", year=1, status="Paid")]), current_user=ADMIN)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_invalid_year_for_vtu_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            RU.update_fees(RU.FeeUpdateRequest(usn=U_A, confirm=True,
                         fees=[RU.FeeRow(fee_type="VTU", year=0, status="Paid")]), current_user=ADMIN)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_unverifiable_status_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            RU.update_fees(RU.FeeUpdateRequest(usn=U_A, confirm=True,
                         fees=[RU.FeeRow(fee_type="VTU", year=1, status="maybe later")]),
                         current_user=ADMIN)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_undo_reverts_fee(self):
        self.assertEqual(_fee_status(U_A, "VTU", 1), "Not Paid")
        res = RU.update_fees(RU.FeeUpdateRequest(usn=U_A, confirm=True,
                    fees=[RU.FeeRow(fee_type="VTU", year=1, status="Paid")]), current_user=ADMIN)
        self.assertEqual(_fee_status(U_A, "VTU", 1), "Paid")
        restore_student(res["undo_token"], current_user=ADMIN)
        self.assertEqual(_fee_status(U_A, "VTU", 1), "Not Paid")

    def test_insert_new_fee_row(self):
        RU.update_fees(RU.FeeUpdateRequest(usn=U_A, confirm=True,
                    fees=[RU.FeeRow(fee_type="PD", year=2, status="Paid")]), current_user=ADMIN)
        self.assertEqual(_fee_status(U_A, "PD", 2), "Paid")


class DynamicDataSyncTests(unittest.TestCase):
    """`students.dynamic_data` is the workbook-imported copy of the same fee and
    village answers, and report_service renders it next to the authoritative
    rows. If an update only writes student_fees / students.village, one report
    ends up stating both the new value and the old one — which reads to staff as
    "the update didn't happen". (Regression seen on a real student: student_fees
    said VTU year 4 Paid while dynamic_data still said Not Paid.)"""

    DYN = ('{"fee_vtu_1": "Not Paid", "fee_pd_2": "Paid", "fee_tuition_paid": "28000",'
           ' "village_name_town": "Javoor", "parents_number": "9008175110",'
           ' "timestamp": "2026-10-06 16:56:10.932000"}')

    def setUp(self):
        _seed()
        _exec("UPDATE students SET dynamic_data=%s WHERE usn=%s", (self.DYN, U_A))

    def _dyn(self, usn=U_A):
        import json
        raw = _query("SELECT dynamic_data FROM students WHERE usn=%s", (usn,))[0]["dynamic_data"]
        return json.loads(raw) if raw else {}

    def test_fee_update_syncs_existing_dynamic_key(self):
        RU.update_fees(RU.FeeUpdateRequest(usn=U_A, confirm=True,
                     fees=[RU.FeeRow(fee_type="VTU", year=1, status="Paid")]), current_user=ADMIN)
        self.assertEqual(_fee_status(U_A, "VTU", 1), "Paid")
        self.assertEqual(self._dyn()["fee_vtu_1"], "Paid",
                         "dynamic_data kept the stale fee status")

    def test_village_update_syncs_dynamic_key(self):
        RU.update_field(RU.FieldUpdateRequest(usn=U_A, field="village", value="Arasanti",
                                              confirm=True), current_user=STAFF)
        self.assertEqual(_query("SELECT village FROM students WHERE usn=%s", (U_A,))[0]["village"],
                         "Arasanti")
        self.assertEqual(self._dyn()["village_name_town"], "Arasanti")

    def test_sync_never_invents_absent_keys(self):
        # fee_vtu_4 was not imported; the report must not grow a phantom column.
        RU.update_fees(RU.FeeUpdateRequest(usn=U_A, confirm=True,
                     fees=[RU.FeeRow(fee_type="VTU", year=4, status="Paid")]), current_user=ADMIN)
        self.assertEqual(_fee_status(U_A, "VTU", 4), "Paid")
        self.assertNotIn("fee_vtu_4", self._dyn())

    def test_unrelated_dynamic_keys_survive(self):
        RU.update_fees(RU.FeeUpdateRequest(usn=U_A, confirm=True,
                     fees=[RU.FeeRow(fee_type="VTU", year=1, status="Paid")]), current_user=ADMIN)
        d = self._dyn()
        self.assertEqual(d["parents_number"], "9008175110")
        self.assertEqual(d["fee_pd_2"], "Paid")
        self.assertIn("timestamp", d)

    def test_undo_restores_dynamic_data(self):
        res = RU.update_fees(RU.FeeUpdateRequest(usn=U_A, confirm=True,
                           fees=[RU.FeeRow(fee_type="VTU", year=1, status="Paid")]),
                           current_user=ADMIN)
        restore_student(res["undo_token"], current_user=ADMIN)
        self.assertEqual(self._dyn().get("fee_vtu_1"), "Not Paid",
                         "undo left dynamic_data carrying the new value")


class LifecycleStatusAliasTests(unittest.TestCase):
    """The canonical statuses are hyphenated report labels, but a caller typing
    the plain word must not get a bare 400 ('Dropout' was rejected because the
    canonical is 'Dropout-College Recorded'). Ambiguous words stay rejected."""

    def test_short_forms_resolve(self):
        self.assertEqual(LC.normalize_status("dropout"), LC.STATUS_DROPOUT)
        self.assertEqual(LC.normalize_status("Dropout"), LC.STATUS_DROPOUT)
        self.assertEqual(LC.normalize_status("rejoined"), LC.STATUS_REJOINED)
        self.assertEqual(LC.normalize_status("temporarily discontinued"),
                         LC.STATUS_TEMP_DISCONTINUED)

    def test_canonical_still_exact(self):
        for status in LC.LIFECYCLE_STATUSES:
            self.assertEqual(LC.normalize_status(status), status)

    def test_ambiguous_and_garbage_rejected(self):
        for bad in ("", "nonsense", "discontinue", "readmission", "college"):
            self.assertIsNone(LC.normalize_status(bad), f"{bad!r} must not resolve")


class NLFeeParseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _seed()

    @classmethod
    def tearDownClass(cls):
        _cleanup()

    def test_parse_vtu_year_status(self):
        p = RU.parse_fee_command("update VTU fee of 9ZZUP0001 year 2 to Paid")
        self.assertEqual(p["fee_type"], "VTU")
        self.assertEqual(p["year"], 2)
        self.assertEqual(p["status"], "Paid")

    def test_parse_tuition_paid(self):
        p = RU.parse_fee_command("mark tuition fee paid of 9ZZUP0001 as Yes")
        self.assertEqual(p["fee_type"], "TUITION_PAID")
        self.assertEqual(p["year"], 0)

    def test_parse_not_paid(self):
        p = RU.parse_fee_command("set IDP 3rd year fee of 9ZZUP0001 to Not Paid")
        self.assertEqual(p["fee_type"], "IDP")
        self.assertEqual(p["year"], 3)
        self.assertEqual(p["status"], "Not Paid")

    def test_reads_are_not_parsed(self):
        self.assertIsNone(RU.parse_fee_command("list students whose fees are pending"))
        self.assertIsNone(RU.parse_fee_command("show total fees paid"))

    def test_non_tuition_needs_year(self):
        self.assertIsNone(RU.parse_fee_command("update VTU fee of 9ZZUP0001 to Paid"))

    def test_preview_resolves_student(self):
        prev = RU.prepare_fee_preview("update VTU fee of 9ZZUP0001 year 1 to Paid", "up_admin")
        self.assertEqual(prev["action_required"], "confirm")
        self.assertEqual(prev["action_type"], "FEE_UPDATE")
        self.assertEqual(prev["confirm_endpoint"], "/api/update/fees")
        self.assertEqual(prev["payload"]["usn"], U_A)
        self.assertEqual(prev["payload"]["fees"][0]["fee_type"], "VTU")

    def test_preview_unknown_usn_no_write(self):
        prev = RU.prepare_fee_preview("update VTU fee of 9ZZUP7777 year 1 to Paid", "up_admin")
        self.assertEqual(prev["action_required"], "no_record")


class NLLifecycleRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _seed()

    @classmethod
    def tearDownClass(cls):
        _cleanup()

    def test_read_is_not_routed_as_record(self):
        # The loose library call can flag these, but the search-bar gate requires
        # a record verb or a USN, so plain reads stay reads.
        self.assertFalse(_is_searchbar_lifecycle_record("discontinued students"))
        self.assertFalse(_is_searchbar_lifecycle_record("students who rejoined"))

    def test_record_with_usn_or_verb_is_routed(self):
        self.assertTrue(_is_searchbar_lifecycle_record("discontinue USN 9ZZUP0001"))
        self.assertTrue(_is_searchbar_lifecycle_record("mark 9ZZUP0001 as dropout due to medical"))
        self.assertTrue(_is_searchbar_lifecycle_record("mark Manoj discontinued"))


class LifecycleTransitionTests(unittest.TestCase):
    def test_active_can_discontinue_and_dropout(self):
        to = {a["to_status"] for a in LC.next_actions(LC.STATUS_ACTIVE)}
        self.assertIn(LC.STATUS_TEMP_DISCONTINUED, to)
        self.assertIn(LC.STATUS_DROPOUT, to)

    def test_discontinued_and_dropout_reverse_to_active(self):
        self.assertTrue(LC.is_transition_allowed(LC.STATUS_TEMP_DISCONTINUED, LC.STATUS_ACTIVE))
        self.assertTrue(LC.is_transition_allowed(LC.STATUS_DROPOUT, LC.STATUS_ACTIVE))
        rev = {a["to_status"] for a in LC.next_actions(LC.STATUS_DROPOUT)}
        self.assertIn(LC.STATUS_ACTIVE, rev)

    def test_same_status_allowed(self):
        self.assertTrue(LC.is_transition_allowed(LC.STATUS_ACTIVE, LC.STATUS_ACTIVE))

    def test_terminal_only_correction(self):
        self.assertTrue(LC.is_transition_allowed(LC.STATUS_GRADUATED, LC.STATUS_ACTIVE))
        self.assertFalse(LC.is_transition_allowed(LC.STATUS_GRADUATED, LC.STATUS_TEMP_DISCONTINUED))

    def test_invalid_to_status(self):
        self.assertFalse(LC.is_transition_allowed(LC.STATUS_ACTIVE, "Space Cadet"))


if __name__ == "__main__":
    unittest.main()
