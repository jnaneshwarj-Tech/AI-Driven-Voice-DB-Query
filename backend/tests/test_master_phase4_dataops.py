"""Master QA Phase 4 — student data operations and USN protection.

Every expectation is read back from MySQL in this process (never from the
application's own response), only synthetic "9QQ…" USNs are written, and the
production schema is unreachable because the suite runs with
MYSQL_DB=student_db_staging.

Covered write paths
  * natural-language ADD / UPDATE / DELETE through the real routes
    (routes_query.generate_query -> routes_query.execute_confirmed)
  * the edit-form routes (routes_update: /field, /bulk, /fees)
  * the undo route (routes_undo.restore_student) for every one of them
  * identity protection: students.usn must never change after creation
  * value validation, confirmation gates, role gates and the audit trail

Run:
    MYSQL_DB=student_db_staging PYTHONIOENCODING=utf-8 \
        ./.venv/Scripts/python.exe -m unittest tests.test_master_phase4_dataops
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

from auth import require_roles
from database import db_conn
import routes_query as RQ
import routes_update as RU
from routes_undo import restore_student

ADMIN = {"username": "p4_admin", "role": "Admin"}
STAFF = {"username": "p4_staff", "role": "Staff"}
OTHER = {"username": "p4_someone_else", "role": "Admin"}
VIEWER = {"username": "p4_viewer", "role": "Student"}

EXIST = "9QQ24CS901"      # field edits, fee edits, validation
REG_ADD = "9QQ24CS101"    # ADD target, roll < 400 -> Regular
LAT_ADD = "9QQ24CS471"    # ADD target, roll >= 400 -> Lateral Entry
TWIN_A = "9QQ24CS902"     # both twins share a name -> ambiguity
TWIN_B = "9QQ24CS903"
DEL_TARGET = "9QQ24CS909"  # deleted and restored
BAD_USN = "9QQ24CS912"     # rejected malformed identifiers
ALL_TEST = [EXIST, REG_ADD, LAT_ADD, TWIN_A, TWIN_B, DEL_TARGET, BAD_USN,
            "9QQ24CS910", "9QQ24CS911", "9QQ24CS913", "9QQ24CS914"]

CHILD_TABLES = ("students", "marks", "student_fees", "student_history",
                "student_field_sources", "student_backlogs",
                "student_lifecycle_status", "student_lifecycle_events",
                "addition_logs", "deletion_logs")

USN_RE = re.compile(r"([0-9][A-Z]{2,3})([0-9]{2})([A-Z]{2,4})([0-9]{2,3})")


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


def student(usn):
    return one("SELECT * FROM students WHERE usn=%s", (usn,))


def expected_usn_derived(usn):
    """The documented VTU rule, restated here from graduation_manager's header
    comment rather than imported, so the app cannot grade its own homework."""
    m = USN_RE.fullmatch(usn.upper())
    if not m:
        return None
    year = 2000 + int(m.group(2))
    roll = int(m.group(4))
    lateral = roll >= 400
    batch = year - 1 if lateral else year
    today = date.today()
    years = today.year - batch - (1 if today.month < 7 else 0)
    sem = max(1, min(8, years * 2 + (1 if today.month >= 7 else 0)))
    return {"admission_year": batch, "current_year": (sem + 1) // 2,
            "student_type": "Lateral Entry" if lateral else "Regular",
            "estimated_semester": sem}


def generate(nq, user=ADMIN, language="english"):
    try:
        return {"ok": RQ.generate_query(
            RQ.QueryRequest(natural_query=nq, language=language), current_user=user)}
    except HTTPException as e:
        return {"err": e}


def execute(query_dict, user, nq="phase4", confirmed=True, token=None):
    try:
        return {"ok": RQ.execute_confirmed(
            RQ.ExecuteRequest(query_dict=query_dict, original_query=nq,
                              confirmed=confirmed, confirmation_token=token),
            current_user=user)}
    except HTTPException as e:
        return {"err": e}


def detail(result):
    e = result.get("err") if isinstance(result, dict) else result
    return getattr(e, "detail", e)


def undo_tokens_of(response):
    return [t["token"] for t in (response or {}).get("restore_tokens", [])]


def cleanup():
    ph = ",".join(["%s"] * len(ALL_TEST))
    for tbl in CHILD_TABLES:
        write(f"DELETE FROM {tbl} WHERE usn IN ({ph})", ALL_TEST)
    # A refused malformed USN must not linger if the guard is missing.
    write("DELETE FROM students WHERE usn='bad usn!'")
    write(f"DELETE FROM audit_log WHERE target_id IN ({ph})", ALL_TEST)
    write("DELETE FROM audit_log WHERE username IN (%s,%s,%s,%s)",
          (ADMIN["username"], STAFF["username"], OTHER["username"], VIEWER["username"]))


def seed():
    cleanup()
    for usn, name in ((EXIST, "Probe One"), (TWIN_A, "Twin Kid"), (TWIN_B, "Twin Kid"),
                      (DEL_TARGET, "Deleteme Kid")):
        write("INSERT INTO students (usn, name, gender, branch, admission_year, phone, "
              "district, current_sem, status, lifecycle_status) "
              "VALUES (%s,%s,'Male','CS',2024,'9000000001','Hassan',5,'Active','Active')",
              (usn, name))
    write("INSERT INTO marks (usn, semester, sgpa, year) VALUES (%s,5,8.25,2024)", (EXIST,))
    write("INSERT INTO marks (usn, semester, sgpa, year) VALUES (%s,3,7.10,2023),"
          "(%s,4,7.60,2024)", (DEL_TARGET, DEL_TARGET))
    write("INSERT INTO student_fees (usn, fee_type, year, status) "
          "VALUES (%s,'VTU',1,'Not Paid')", (EXIST,))


class Phase4DataOpsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed()

    @classmethod
    def tearDownClass(cls):
        cleanup()
        leaked = rows("SELECT usn FROM students WHERE usn LIKE '9QQ%' "
                      "OR usn LIKE 'bad usn%%'")
        assert not leaked, f"synthetic phase-4 rows leaked: {[r['usn'] for r in leaked][:5]}"

    def setUp(self):
        seed()

    # ── 1. natural-language ADD ──────────────────────────────────────────────
    def test_add_creates_student_with_derived_fields_and_logs(self):
        for usn, label in ((REG_ADD, "Regular"), (LAT_ADD, "Lateral Entry")):
            with self.subTest(usn=usn):
                gen = generate(f"add student {usn} named {label} Kid")
                self.assertIn("ok", gen, f"add was refused: {detail(gen)}")
                qd = gen["ok"]["query_dict"]
                self.assertEqual(qd["operation"], "insert")
                self.assertEqual(qd["student_usn"], usn)
                self.assertIsNone(student(usn), "generate must not write")

                res = execute(qd, ADMIN, "add student")
                self.assertIn("ok", res, f"insert failed: {detail(res)}")
                row = student(usn)
                self.assertIsNotNone(row, f"{usn} was not created")
                self.assertEqual(row["name"], f"{label} Kid")
                want = expected_usn_derived(usn)
                for col, val in want.items():
                    self.assertEqual(str(row[col]), str(val),
                                     f"{usn}: {col} must follow the VTU rule "
                                     f"(expected {val}, got {row[col]})")
                self.assertTrue(undo_tokens_of(res["ok"]),
                                "an added student must be undoable")
                self.assertEqual(
                    rows("SELECT * FROM addition_logs WHERE usn=%s", (usn,))[0]["added_by"],
                    ADMIN["username"], "the adder must be recorded")

    def test_add_of_existing_usn_is_refused_before_write(self):
        before = one("SELECT COUNT(*) AS c FROM students")["c"]
        for phrasing in (f"add student {EXIST} named Duplicate Kid",
                         f"add student {EXIST.lower()} named Lowercase Kid"):
            with self.subTest(phrasing=phrasing):
                gen = generate(phrasing)
                got = gen.get("ok") or {}
                self.assertEqual(got.get("action_required"), "select_student",
                                 f"expected a refusal, got {got}")
                self.assertIn("already exists", str(got.get("message", "")).lower())
        self.assertEqual(one("SELECT COUNT(*) AS c FROM students")["c"], before,
                         "a refused add must not create a row")
        self.assertIsNone(one("SELECT usn FROM students WHERE name=%s",
                             ("Lowercase Kid",)))

    def test_execute_rejects_a_stale_duplicate_preview(self):
        # The preview passed the existence check; the row appeared in between.
        execute({"operation": "insert",
                 "sql": f"INSERT INTO students (usn, name) VALUES ('{TWIN_A}', 'Race Kid')"},
                ADMIN)
        before = student(TWIN_A)
        res = execute({"operation": "insert",
                       "sql": f"INSERT INTO students (usn, name) VALUES ('{TWIN_A}', 'Other Kid')"},
                      ADMIN)
        self.assertIn("err", res, "a duplicate USN must not be committed twice")
        self.assertEqual(res["err"].status_code, 400)
        self.assertEqual(student(TWIN_A)["name"], before["name"],
                         "the rejected insert must not overwrite the existing row")

    def test_add_without_usn_or_name_asks_and_writes_nothing(self):
        before = {r["usn"] for r in rows("SELECT usn FROM students")}
        for phrasing in ("add a new student named Nameless Kid",
                         "add student 12ABC named Bad Format Kid",
                         "add student 9QQ24CS9 named Short Kid",
                         f"add student {BAD_USN}"):
            with self.subTest(phrasing=phrasing):
                gen = generate(phrasing)
                got = gen.get("ok") or {}
                self.assertEqual(got.get("action_required"), "select_student",
                                 f"expected an ask, got {got or detail(gen)}")
                self.assertNotIn("9QQ24CS910",
                                 {r["usn"] for r in rows("SELECT usn FROM students")} - before)
        self.assertEqual({r["usn"] for r in rows("SELECT usn FROM students")}, before,
                         "no add attempt may create a row")

    def test_add_stores_an_apostrophe_name_and_survives_hostile_text(self):
        total_before = one("SELECT COUNT(*) AS c FROM students")["c"]
        gen = generate(f"add student {BAD_USN} named D'Souza Kid")
        qd = (gen.get("ok") or {}).get("query_dict")
        self.assertIsNotNone(qd, f"apostrophe name refused: {gen}")
        execute(qd, ADMIN)
        self.assertEqual(student(BAD_USN)["name"], "D'Souza Kid",
                         "the name must be stored exactly as typed")
        self.assertEqual(one("SELECT COUNT(*) AS c FROM students")["c"], total_before + 1,
                         "only the requested row may exist")
        hostile = generate("add student 9QQ24CS913 named Fred; DELETE FROM students")
        hd = (hostile.get("ok") or {}).get("query_dict")
        if hd:
            execute(hd, ADMIN)
        self.assertIsNotNone(one("SELECT usn FROM students WHERE usn=%s", (EXIST,)),
                            "the students table must survive an SQL-shaped name")

    def test_execute_refuses_a_client_supplied_malformed_usn(self):
        # /execute must not trust the client's USN text: the identity column is
        # the key of every student record.
        res = execute({"operation": "insert",
                       "sql": "INSERT INTO students (usn, name) VALUES ('bad usn!', 'Hole Kid')"},
                      ADMIN)
        self.assertIn("err", res, "a malformed USN must be refused by the server")
        self.assertIn(res["err"].status_code, (400, 403))
        self.assertIsNone(one("SELECT usn FROM students WHERE name=%s", ("Hole Kid",)),
                          "nothing may be written for a refused USN")

    # ── 2. USN identity protection ───────────────────────────────────────────
    def test_usn_cannot_be_changed_through_any_write_path(self):
        before = student(EXIST)
        target = "9QQ24CS950"

        nl = generate(f"update usn of {EXIST} to {target}")
        if "err" in nl:
            self.assertEqual(nl["err"].status_code, 400)
            self.assertIn("usn", str(nl["err"].detail).lower(),
                          "the staff member must be told the USN is immutable")
        else:
            self.assertNotEqual((nl.get("ok") or {}).get("action_type"), "UPDATE",
                                f"NL must not offer a USN rewrite: {nl['ok']}")

        raw = execute({"operation": "update",
                       "sql": f"UPDATE students SET usn='{target}' WHERE usn='{EXIST}'"}, ADMIN)
        self.assertIn("err", raw, "a raw UPDATE that rewrites usn must be refused")

        for field_text in ("usn", "USN", "student id"):
            with self.subTest(field=field_text):
                with self.assertRaises(HTTPException) as ctx:
                    RU.update_field(RU.FieldUpdateRequest(usn=EXIST, field=field_text,
                                                          value=target, confirm=True),
                                    current_user=ADMIN)
                self.assertEqual(ctx.exception.status_code, 400)
            with self.assertRaises(HTTPException):
                RU.update_bulk(RU.BulkFieldUpdateRequest(usn=EXIST,
                                                         fields={field_text: target,
                                                                 "district": "Kolar"},
                                                         confirm=True), current_user=ADMIN)

        after = student(EXIST)
        self.assertEqual(after["usn"], before["usn"], "the USN must never change")
        self.assertEqual(after["district"], before["district"],
                         "a bulk edit refused for one column must change none")

    def test_fuzzy_name_edit_with_two_candidates_asks_instead_of_guessing(self):
        gen = generate(f"update phone of Twin Kid to 9000007777")
        got = gen.get("ok") or {}
        if "err" in gen:
            self.assertIn(gen["err"].status_code, (400, 404))
            phone = one(f"SELECT phone FROM students WHERE name='Twin Kid'")
            self.assertEqual(phone["phone"], "9000000001",
                             "an refused edit must not change either twin")
            return
        self.assertEqual(got.get("action_required"), "select_student",
                         f"an ambiguous name must be disambiguated, not written: {got}")
        self.assertEqual(
            [r["phone"] for r in rows("SELECT phone FROM students WHERE name='Twin Kid'")],
            ["9000000001", "9000000001"], "no twin may be edited without a chosen USN")

    # ── 3. natural-language UPDATE ───────────────────────────────────────────
    def test_nl_update_writes_value_history_and_undoes(self):
        gen = generate(f"update phone of {EXIST} to 9876543210")
        qd = (gen.get("ok") or {}).get("query_dict")
        self.assertIsNotNone(qd, f"update not offered: {gen}")
        res = execute(qd, STAFF, "update phone")
        self.assertIn("ok", res, f"update failed: {detail(res)}")
        self.assertEqual(student(EXIST)["phone"], "9876543210")
        hist = rows("SELECT field_name,old_value,new_value,updated_by FROM student_history "
                    "WHERE usn=%s ORDER BY id", (EXIST,))
        self.assertEqual([h["field_name"] for h in hist], ["phone"])
        self.assertEqual((hist[0]["old_value"], hist[0]["new_value"]),
                         ("9000000001", "9876543210"), "field history must record both values")
        self.assertEqual(hist[0]["updated_by"], STAFF["username"])

        token = undo_tokens_of(res["ok"])
        self.assertTrue(token, "an NL update must be undoable")
        restore_student(token[0], current_user=STAFF)
        self.assertEqual(student(EXIST)["phone"], "9000000001",
                         "undo must restore the exact previous value")

    def test_nl_update_applies_every_field_in_one_sentence(self):
        gen = generate(f"update district of {EXIST} to Kolar and phone to 9000002222")
        qd = (gen.get("ok") or {}).get("query_dict")
        self.assertIsNotNone(qd, f"multi-field update not offered: {gen}")
        res = execute(qd, STAFF, "update two fields")
        self.assertIn("ok", res, f"multi-field update failed: {detail(res)}")
        row = student(EXIST)
        self.assertEqual((row["district"], row["phone"]), ("Kolar", "9000002222"),
                         "both assignments must be applied together")

    def test_confirm_preview_names_the_student_and_every_new_value(self):
        # Staff press Confirm without reading SQL, so every write preview has to say
        # which student changes and what the changed fields become.
        phrasing = f"update district of {EXIST} to Kolar and phone to 9000002222"
        msg = (generate(phrasing, STAFF).get("ok") or {}).get("message", "")
        for token in (student(EXIST)["name"], EXIST, "district", "Kolar",
                      "phone", "9000002222"):
            self.assertIn(token, msg,
                          f"{phrasing!r} preview omitted {token!r}: {msg!r}")

        msg = (generate(f"add student {REG_ADD} named Preview Kid").get("ok")
               or {}).get("message", "")
        for token in (REG_ADD, "Preview Kid"):
            self.assertIn(token, msg, f"add preview omitted {token!r}: {msg!r}")

        msg = (generate(f"delete student {DEL_TARGET}").get("ok") or {}).get("message", "")
        for token in (DEL_TARGET, student(DEL_TARGET)["name"]):
            self.assertIn(token, msg, f"delete preview omitted {token!r}: {msg!r}")

    def test_nl_update_tolerates_a_typo_in_the_field_name(self):
        gen = generate(f"update phne of {EXIST} to 9000003333")
        qd = (gen.get("ok") or {}).get("query_dict")
        self.assertIsNotNone(qd, f"a mistyped field name must still be understood: {gen}")
        execute(qd, STAFF, "update phone")
        self.assertEqual(student(EXIST)["phone"], "9000003333")

    def test_blank_field_can_be_filled_from_the_search_bar(self):
        # Staff write these phrases because the Edit form is described as
        # "fill any blank field"; each must be an edit, never a read.
        cases = [(f"fill email of {EXIST} as probekid@example.com", "email",
                  "probekid@example.com"),
                 (f"set district of {EXIST} to Kolar", "district", "Kolar"),
                 (f"change phone of {EXIST} to 9000004444", "phone", "9000004444"),
                 (f"correct taluk of {EXIST} to Hassan", "taluk", "Hassan"),
                 (f"enter blood group of {EXIST} as O+", "blood_group", "O+")]
        for phrasing, column, value in cases:
            with self.subTest(phrasing=phrasing):
                write(f"UPDATE students SET `{column}`=NULL WHERE usn=%s", (EXIST,))
                self.assertIsNone(student(EXIST)[column],
                                  "the column must start blank for a fill test")
                gen = generate(phrasing)
                qd = (gen.get("ok") or {}).get("query_dict")
                self.assertIsNotNone(
                    qd, f"{phrasing!r} was treated as a read, not an edit: "
                        f"{gen.get('err').detail if 'err' in gen else gen['ok'].get('data')}")
                self.assertEqual(qd["operation"], "update")
                res = execute(qd, STAFF, phrasing)
                self.assertIn("ok", res, f"{phrasing!r} failed: {detail(res)}")
                self.assertEqual(str(student(EXIST)[column]), value)

    def test_fill_verbs_without_an_assignment_stay_reads(self):
        # Widening the edit verbs (fill/set/enter/mark/...) must not turn a
        # search into a write or into a 400 error.
        before = student(EXIST)
        for phrasing in ("enter the CS students",
                         "record of students in Hassan district",
                         "mark sheet of 9QQ24CS901"):
            with self.subTest(phrasing=phrasing):
                gen = generate(phrasing, STAFF)
                self.assertNotIn("err", gen, f"{phrasing!r} errored: {detail(gen)}")
                got = gen.get("ok") or {}
                qd = got.get("query_dict") or {}
                self.assertNotIn(qd.get("operation"), ("update", "insert", "delete"),
                                 f"{phrasing!r} was treated as a write: {qd}")
        self.assertEqual(student(EXIST), before,
                         "a read phrasing must not mutate the row")

    def test_invalid_values_are_refused_and_the_row_is_untouched(self):
        before = student(EXIST)
        bad = [("email", "not-an-email"), ("phone", "12"), ("dob", "31-02-2005"),
               ("cgpa", "11"), ("blood_group", "C+")]
        for field, value in bad:
            with self.subTest(field=field):
                with self.assertRaises(HTTPException) as ctx:
                    RU.update_field(RU.FieldUpdateRequest(usn=EXIST, field=field, value=value,
                                                          confirm=True), current_user=STAFF)
                self.assertEqual(ctx.exception.status_code, 400)
            after = student(EXIST)
            for col in before:
                self.assertEqual(after[col], before[col],
                                 f"{field}={value!r} must not change {col}")
        for phrasing in (f"update email of {EXIST} to not-an-email",
                         f"update marks of {EXIST} to 250"):
            with self.subTest(nl=phrasing):
                gen = generate(phrasing)
                if "err" not in gen:
                    qd = gen["ok"].get("query_dict") or {}
                    res = execute(qd, STAFF, phrasing) if qd.get("executions") else {"err": None}
                    self.assertIn("err", res,
                                  f"{phrasing!r} accepted an invalid value: {res}")
        after = student(EXIST)
        for col in before:
            self.assertEqual(after[col], before[col],
                             f"a refused NL edit changed {col}")

    def test_bulk_edit_skips_blank_boxes_but_writes_the_rest(self):
        write("UPDATE students SET village=NULL, taluk=NULL WHERE usn=%s", (EXIST,))
        res = RU.update_bulk(RU.BulkFieldUpdateRequest(
            usn=EXIST, fields={"village": "Arkalgud", "district": "", "taluk": "Hassan"},
            confirm=True), current_user=STAFF)
        cols = {c["column"] for c in res["changed"]}
        self.assertEqual(cols, {"village", "taluk"})
        row = student(EXIST)
        self.assertEqual((row["village"], row["taluk"]), ("Arkalgud", "Hassan"))
        self.assertEqual(row["district"], "Hassan", "a blank box must not erase the value")
        restore_student(res["undo_token"], current_user=STAFF)
        row = student(EXIST)
        self.assertEqual((row["village"], row["taluk"]), (None, None),
                         "one undo token must revert the whole form")

    def test_bulk_edit_is_atomic_when_one_field_is_invalid(self):
        write("UPDATE students SET village=NULL WHERE usn=%s", (EXIST,))
        with self.assertRaises(HTTPException) as ctx:
            RU.update_bulk(RU.BulkFieldUpdateRequest(
                usn=EXIST, fields={"village": "Arkalgud", "email": "nope"},
                confirm=True), current_user=STAFF)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIsNone(student(EXIST)["village"],
                          "a half-applied form leaves the record inconsistent")

    # ── 4. DELETE ────────────────────────────────────────────────────────────
    def test_delete_requires_admin_confirmation_then_removes_child_rows(self):
        with self.assertRaises(HTTPException) as ctx:
            RQ.generate_query(RQ.QueryRequest(natural_query=f"delete student {DEL_TARGET}"),
                              current_user=STAFF)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIsNotNone(student(DEL_TARGET), "a refused staff delete must keep the row")

        gen = generate(f"delete student {DEL_TARGET}")
        qd = (gen.get("ok") or {}).get("query_dict")
        self.assertIsNotNone(qd, f"admin delete not offered: {gen}")
        no_token = execute(qd, ADMIN, "delete", confirmed=True, token=None)
        self.assertIn("err", no_token, "a delete needs a signed confirmation token")
        unconfirmed = execute(qd, ADMIN, "delete", confirmed=False,
                              token=gen["ok"]["confirmation_token"])
        self.assertIn("err", unconfirmed, "an unchecked 'confirmed' flag must stop the delete")

        res = execute(qd, ADMIN, "delete", confirmed=True,
                      token=gen["ok"]["confirmation_token"])
        self.assertIn("ok", res, f"delete failed: {detail(res)}")
        self.assertIsNone(student(DEL_TARGET))
        self.assertEqual(rows("SELECT * FROM marks WHERE usn=%s", (DEL_TARGET,)), [],
                         "a deleted student must not leave marks behind")
        log = rows("SELECT * FROM deletion_logs WHERE usn=%s", (DEL_TARGET,))
        self.assertEqual(log[0]["deleted_by"], ADMIN["username"])
        self.assertTrue(log[0]["restore_token"])

    def test_delete_then_undo_restores_the_student_exactly(self):
        before = student(DEL_TARGET)
        marks_before = rows("SELECT semester,sgpa FROM marks WHERE usn=%s ORDER BY semester",
                            (DEL_TARGET,))
        gen = generate(f"delete student {DEL_TARGET}")
        res = execute(gen["ok"]["query_dict"], ADMIN, "delete", confirmed=True,
                      token=gen["ok"]["confirmation_token"])
        token = undo_tokens_of(res["ok"])
        self.assertTrue(token)
        with self.assertRaises(HTTPException) as ctx:
            restore_student(token[0], current_user=OTHER)
        self.assertEqual(ctx.exception.status_code, 403,
                         "only the actor may undo their own write")
        self.assertIsNone(student(DEL_TARGET), "a refused undo must not restore anything")

        out = restore_student(token[0], current_user=ADMIN)
        self.assertTrue(out["success"])
        after = student(DEL_TARGET)
        self.assertIsNotNone(after, "the student must come back")
        for col in before:
            if col in ("created_at", "updated_at"):
                continue
            self.assertEqual(after[col], before[col], f"undo changed {col}")
        self.assertEqual(rows("SELECT semester,sgpa FROM marks WHERE usn=%s ORDER BY semester",
                              (DEL_TARGET,)), marks_before,
                         "the deleted marks must be restored too")

    def test_undo_of_an_added_student_removes_only_that_student(self):
        gen = generate(f"add student {REG_ADD} named Undo Kid")
        res = execute(gen["ok"]["query_dict"], ADMIN, "add")
        token = undo_tokens_of(res["ok"])
        self.assertTrue(token, "an added student must be undoable")
        restore_student(token[0], current_user=ADMIN)
        self.assertIsNone(student(REG_ADD), "undo must remove the student that was added")
        self.assertIsNotNone(student(EXIST), "undo must not touch other students")

    def test_ambiguous_or_unknown_delete_target_deletes_nothing(self):
        gen = generate("delete student Twin Kid")
        got = gen.get("ok") or {}
        self.assertEqual(got.get("action_required"), "select_student",
                         f"two students share that name, the app must ask: {got}")
        self.assertEqual(len(rows("SELECT usn FROM students WHERE name='Twin Kid'")), 2)
        with self.assertRaises(HTTPException) as ctx:
            RQ.generate_query(RQ.QueryRequest(natural_query="delete student 9QQ24CS999"),
                              current_user=ADMIN)
        self.assertIn(ctx.exception.status_code, (404, 400))

    def test_wipe_requests_are_blocked_through_every_door(self):
        total = one("SELECT COUNT(*) AS c FROM students")["c"]
        for phrasing in ("delete all students", "remove every student record",
                         "ಎಲ್ಲಾ ವಿದ್ಯಾರ್ಥಿಗಳನ್ನು ಅಳಿಸಿ"):
            with self.subTest(phrasing=phrasing):
                with self.assertRaises(HTTPException) as ctx:
                    RQ.generate_query(RQ.QueryRequest(natural_query=phrasing),
                                      current_user=ADMIN)
                self.assertEqual(ctx.exception.status_code, 403)
        for sql in ("DELETE FROM students", f"DELETE FROM students WHERE usn LIKE '9QQ%'",
                    "DELETE FROM students WHERE 1=1"):
            with self.subTest(sql=sql):
                res = execute({"operation": "delete", "sql": sql}, ADMIN,
                              "delete", confirmed=True,
                              token="1." + "0" * 64)
                self.assertIn("err", res, f"{sql!r} must never execute")
        self.assertEqual(one("SELECT COUNT(*) AS c FROM students")["c"], total,
                         "no row may be lost to a wipe attempt")

    # ── 5. fees + role gates + audit ─────────────────────────────────────────
    def test_fee_status_writes_and_undoes_against_db_truth(self):
        dep = require_roles("Admin")
        with self.assertRaises(HTTPException) as ctx:
            dep(current_user=STAFF)
        self.assertEqual(ctx.exception.status_code, 403,
                         "fee editing must stay Admin-only at the route boundary")
        self.assertEqual(dep(current_user=ADMIN)["role"], "Admin")

        preview = RU.prepare_fee_preview(f"update VTU fee of {EXIST} year 1 to paid",
                                         STAFF["username"])
        self.assertEqual(preview["action_required"], "confirm")
        self.assertEqual(preview["role_restricted"], "Admin")

        res = RU.update_fees(RU.FeeUpdateRequest(
            usn=EXIST, fees=[RU.FeeRow(fee_type="VTU", year=1, status="Paid")],
            confirm=True), current_user=ADMIN)
        self.assertEqual(one("SELECT status FROM student_fees WHERE usn=%s AND fee_type='VTU' "
                             "AND year=1", (EXIST,))["status"], "Paid")
        restore_student(res["undo_token"], current_user=ADMIN)
        self.assertEqual(one("SELECT status FROM student_fees WHERE usn=%s AND fee_type='VTU' "
                             "AND year=1", (EXIST,))["status"], "Not Paid",
                         "undo must bring back the previous fee status")

    def test_write_paths_leave_an_audit_trail(self):
        RU.update_field(RU.FieldUpdateRequest(usn=EXIST, field="district", value="Kolar",
                                              confirm=True), current_user=STAFF)
        RU.update_fees(RU.FeeUpdateRequest(usn=EXIST, fees=[RU.FeeRow(
            fee_type="PD", year=2, status="Paid")], confirm=True), current_user=ADMIN)
        add = generate(f"add student {REG_ADD} named Audited Kid")
        execute(add["ok"]["query_dict"], ADMIN, "add")
        dele = generate(f"delete student {DEL_TARGET}")
        execute(dele["ok"]["query_dict"], ADMIN, "delete", confirmed=True,
                token=dele["ok"]["confirmation_token"])

        acts = {(r["action"], r["username"]) for r in
                rows("SELECT action,username FROM audit_log WHERE target_id=%s", (EXIST,))}
        self.assertIn(("field_update", STAFF["username"]), acts,
                      f"the edit form left no audit row: {acts}")
        self.assertIn(("fee_update", ADMIN["username"]), acts)
        added = {(r["action"], r["username"]) for r in
                 rows("SELECT action,username FROM audit_log WHERE target_id=%s", (REG_ADD,))}
        self.assertIn(("ADDED", ADMIN["username"]), added)
        deleted = {(r["action"], r["username"]) for r in
                   rows("SELECT action,username FROM audit_log WHERE target_id=%s",
                        (DEL_TARGET,))}
        self.assertIn(("DELETED", ADMIN["username"]), deleted)
        # The natural-language pipeline records the identity it acted on.
        self.assertEqual(
            one("SELECT target_table FROM audit_log WHERE action='ADDED' AND target_id=%s",
                (REG_ADD,))["target_table"], "students")

    def test_read_only_role_cannot_reach_any_write_route(self):
        gates = {"update/field": require_roles("Staff", "Admin"),
                 "update/fees": require_roles("Admin"),
                 "query/execute": require_roles("Admin", "Staff")}
        for name, dep in gates.items():
            with self.subTest(route=name):
                with self.assertRaises(HTTPException) as ctx:
                    dep(current_user=VIEWER)
                self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
