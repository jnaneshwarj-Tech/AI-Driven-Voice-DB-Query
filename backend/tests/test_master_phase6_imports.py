"""Master QA Phase 6 — imports and data integrity.

Every import below is a REAL import: a genuine .xlsx / .csv byte stream is put
through `routes_files.upload_file` (step 1, cache only) and
`routes_files.update_database` (step 2, the transaction), and the result is
verified by reading MySQL in this process — the student row, `marks`,
`student_fees`, `student_backlogs`, `student_field_sources`, `dynamic_data`,
`field_registry`, `uploaded_files`, `upload_versions`, the undo snapshot and
`audit_log`. No expectation is taken from the API's own answer.

Only synthetic `9QQ…` USNs are written; the suite runs with
MYSQL_DB=student_db_staging, so the production schema is unreachable.

Run:
    MYSQL_DB=student_db_staging PYTHONIOENCODING=utf-8 \
        ./.venv/Scripts/python.exe -m unittest tests.test_master_phase6_imports
"""
import asyncio
import datetime as dt
import io
import json
import os
import re
import sys
import time
import unittest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from fastapi import HTTPException
from openpyxl import Workbook

from auth import require_roles
from database import db_conn
import routes_files as RF

ADMIN = {"username": "p6_admin", "role": "Admin"}
STAFF = {"username": "p6_staff", "role": "Staff"}
VIEWER = {"username": "p6_viewer", "role": "Student"}

# synthetic identities only — 9QQ is not a college code
U1 = "9QQ24CS921"
U2 = "9QQ24CS922"
U3 = "9QQ24CS923"
U4 = "9QQ24CS924"
BULK_BASE = 930          # 9QQ24CS930 … 9QQ24CS000+ for the 1000-row import
MINE = [U1, U2, U3, U4]

CHILD_TABLES = ("students", "marks", "student_fees", "student_backlogs",
                "student_field_sources", "addition_logs", "deletion_logs",
                "student_history", "student_lifecycle_status",
                "student_lifecycle_events")

HEAD = ["USN", "Student Name", "Date of Birth", "Phone", "Email", "District",
        "Gender", "CGPA", "Semester 3 SGPA", "Semester 4 SGPA", "VTU Fee 1",
        "Fee Pending", "Backlogs", "Grandfather farm size", "Blood Group"]
ROW1 = [U1, "Probe Import One", dt.date(2005, 6, 17), 9000007777,
        "p1@college.edu", "Kolar", "MALE", 8.25, 7.9, 8.4, "Paid", "5000",
        "Maths III, 5, 2024; Physics, 6, 2025", "4 acres", "O+"]


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


def val(usn, col):
    got = one(f"SELECT `{col}` AS v FROM students WHERE usn=%s", (usn,))
    return got["v"] if got else None


def count(sql, params=()):
    got = one(sql, params)
    return list(got.values())[0] if got else 0


def write(sql, params=()):
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, list(params))
        conn.commit()
        cur.close()


def xlsx_bytes(header, data_rows):
    wb = Workbook()
    ws = wb.active
    ws.append(list(header))
    for r in data_rows:
        ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def csv_bytes(header, data_rows, bom=False):
    buf = io.StringIO()
    if bom:
        buf.write("﻿")
    writer = __import__("csv").writer(buf)
    writer.writerow(list(header))
    for r in data_rows:
        writer.writerow(["" if c is None else c for c in r])
    return buf.getvalue().encode("utf-8-sig" if bom else "utf-8")


class FakeUpload:
    """Minimal UploadFile stand-in: the route only uses .filename and .read()."""

    def __init__(self, filename, content):
        self.filename = filename
        self.content_type = "application/octet-stream"
        self._content = content

    async def read(self):
        return self._content


class Phase6ImportTests(unittest.TestCase):
    """Real upload → real transaction → SQL truth."""

    def setUp(self):
        self.files = []
        self.usns = list(MINE)

    def tearDown(self):
        for name in self.files:
            try:
                RF._remove_upload_cache(name)
            except HTTPException:
                pass
            write("DELETE FROM uploaded_files WHERE filename=%s", (name,))
            write("DELETE FROM upload_versions WHERE filename=%s", (name,))
            write("DELETE FROM audit_log WHERE target_id=%s", (name,))
        placeholders = ",".join(["%s"] * len(self.usns))
        for table in CHILD_TABLES:
            col = "usn" if table != "audit_log" else "target_id"
            try:
                write(f"DELETE FROM {table} WHERE {col} IN ({placeholders})",
                      tuple(self.usns))
            except Exception:
                pass
        write(f"DELETE FROM marks WHERE usn IN ({placeholders})", tuple(self.usns))
        # Snapshot payloads are big JSON blobs: match the four fixture USNs plus
        # the synthetic bulk prefix, instead of one table scan per bulk row.
        for pat in [f"%{u}%" for u in self.usns[:4]] + ["%9QQ24CQ%", "%9QQ24CS9%"]:
            write("DELETE FROM global_undo_snapshots WHERE snapshot_data LIKE %s", (pat,))
        write(
            "DELETE FROM field_registry WHERE canonical_name IN "
            "('grandfather_farm_size','fee_pending')")

    # ── plumbing ─────────────────────────────────────────────────────────────
    def upload(self, filename, content, user=ADMIN):
        self.files.append(filename)
        return asyncio.run(RF.upload_file(file=FakeUpload(filename, content),
                                         current_user=user))

    def commit(self, filename, user=ADMIN):
        return RF.update_database(filename, current_user=user)

    def import_file(self, filename, header, data_rows, user=ADMIN, ext="xlsx",
                    bom=False):
        content = (csv_bytes(header, data_rows, bom=bom) if ext == "csv"
                   else xlsx_bytes(header, data_rows))
        self.upload(filename, content, user=user)
        return self.commit(filename, user=user)

    # ── 1. the happy path really writes every kind of data ───────────────────
    def test_real_xlsx_import_lands_student_marks_fees_backlogs_and_books(self):
        result = self.import_file("p6_happy.xlsx", HEAD, [ROW1])
        self.assertTrue(result["success"])

        # students: values as MySQL holds them, read back independently
        self.assertEqual(val(U1, "name"), "Probe Import One")
        self.assertEqual(val(U1, "district"), "Kolar")
        self.assertEqual(val(U1, "blood_group"), "O+")
        self.assertEqual(str(val(U1, "dob")), "2005-06-17",
                         "an Excel date cell must land as a real date")
        self.assertEqual(str(val(U1, "phone")), "9000007777",
                         f"a numeric phone must not keep a decimal tail: {val(U1, 'phone')!r}")
        self.assertAlmostEqual(float(val(U1, "cgpa")), 8.25, places=2)
        self.assertEqual(val(U1, "source_file"), "p6_happy.xlsx")

        # marks — one row per semester column, keyed (usn, semester)
        marks = rows("SELECT semester, sgpa FROM marks WHERE usn=%s ORDER BY semester", (U1,))
        self.assertEqual([(m["semester"], float(m["sgpa"])) for m in marks],
                         [(3, 7.9), (4, 8.4)])

        # fees — the known fee heading must reach student_fees
        fees = rows("SELECT fee_type, year, status, amount_paid FROM student_fees WHERE usn=%s", (U1,))
        vtu = [f for f in fees if f["fee_type"] == "VTU" and f["year"] == 1]
        self.assertEqual([(f["status"], str(f["amount_paid"])) for f in vtu],
                         [("Paid", "None")], f"fee rows written: {fees}")


        # backlogs — dual storage: the text column AND parsed rows
        self.assertIn("Maths III", str(val(U1, "backlogs")))
        bl = rows("SELECT subject, semester, year FROM student_backlogs WHERE usn=%s ORDER BY id", (U1,))
        self.assertEqual([(b["subject"], b["semester"]) for b in bl],
                         [("Maths III", 5), ("Physics", 6)])

        # unknown heading: data, not schema — and never a SQL identifier
        dyn = json.loads(val(U1, "dynamic_data") or "{}")
        self.assertEqual(dyn.get("grandfather_farm_size"), "4 acres")
        self.assertIsNotNone(one("SELECT id FROM field_registry WHERE canonical_name=%s",
                                 ("grandfather_farm_size",)))
        cols = [r["Field"] for r in rows("SHOW COLUMNS FROM students")]
        self.assertNotIn("grandfather_farm_size", cols,
                         "an upload heading must never become a column")

        # provenance: the register of who said what, per field
        prov = rows("SELECT field_name, source_filename FROM student_field_sources "
                    "WHERE usn=%s AND is_active=1", (U1,))
        by_field = {p["field_name"]: p["source_filename"] for p in prov}
        self.assertEqual(by_field.get("district"), "p6_happy.xlsx")
        self.assertEqual(by_field.get("mark_sem_3_sgpa"), "p6_happy.xlsx")

        # bookkeeping the staff UI reads
        up = one("SELECT * FROM uploaded_files WHERE filename=%s", ("p6_happy.xlsx",))
        self.assertEqual(up["db_status"], "saved")
        self.assertEqual(up["row_count"], 1)
        self.assertEqual(up["uploaded_by"], "p6_admin")
        ver = one("SELECT * FROM upload_versions WHERE filename=%s", ("p6_happy.xlsx",))
        self.assertEqual(ver["status"], "success")
        self.assertEqual(ver["students_added"], 1)
        aud = one("SELECT action FROM audit_log WHERE target_id=%s AND action=%s",
                  ("p6_happy.xlsx", "UPLOAD_SUCCESS"))
        self.assertIsNotNone(aud)
        self.assertTrue(result["undo_available"],
                        "an import must be undoable — it writes over real records")

    # ── 2. re-importing the same file must not duplicate anything ────────────
    def test_reimporting_the_same_file_is_idempotent(self):
        self.import_file("p6_repeat.xlsx", HEAD, [ROW1])
        before = {
            "students": count("SELECT COUNT(*) c FROM students WHERE usn=%s", (U1,)),
            "marks": count("SELECT COUNT(*) c FROM marks WHERE usn=%s", (U1,)),
            "fees": count("SELECT COUNT(*) c FROM student_fees WHERE usn=%s", (U1,)),
            "backlogs": count("SELECT COUNT(*) c FROM student_backlogs WHERE usn=%s", (U1,)),
            "prov": count("SELECT COUNT(*) c FROM student_field_sources WHERE usn=%s", (U1,)),
        }
        second = self.import_file("p6_repeat.xlsx", HEAD, [ROW1])
        self.assertEqual(second["students_added"], 0)
        self.assertEqual(second["students_unchanged"], 1,
                         f"re-import said: {json.dumps(second, default=str)[:400]}")
        after = {
            "students": count("SELECT COUNT(*) c FROM students WHERE usn=%s", (U1,)),
            "marks": count("SELECT COUNT(*) c FROM marks WHERE usn=%s", (U1,)),
            "fees": count("SELECT COUNT(*) c FROM student_fees WHERE usn=%s", (U1,)),
            "backlogs": count("SELECT COUNT(*) c FROM student_backlogs WHERE usn=%s", (U1,)),
            "prov": count("SELECT COUNT(*) c FROM student_field_sources WHERE usn=%s", (U1,)),
        }
        self.assertEqual(before, after)

    # ── 3. the same USN twice in one file ────────────────────────────────────
    def test_same_usn_twice_in_one_file_keeps_one_student_and_all_marks(self):
        row_a = [U1, "Probe Import One", None, None, None, "Kolar", None, None,
                 7.9, None, None, None, None, None, None]
        row_b = [U1, "Probe Import One (edited)", None, None, None, "Chikkaballapur",
                 None, None, None, 8.4, None, None, None, None, None]
        result = self.import_file("p6_dup_in_file.xlsx", HEAD, [row_a, row_b])
        self.assertEqual(count("SELECT COUNT(*) c FROM students WHERE usn=%s", (U1,)), 1)
        self.assertEqual(result["duplicate_rows"], 1)
        self.assertEqual(result["students_added"], 1)
        # the later row's marks must not be lost by the duplicate flag
        sems = sorted(r["semester"] for r in rows("SELECT semester FROM marks WHERE usn=%s", (U1,)))
        self.assertEqual(sems, [3, 4],
                         "a duplicate row still contributes its own semester marks")

    # ── 4. invalid rows are rejected individually, valid ones still import ───
    def test_invalid_rows_are_rejected_and_reported_without_blocking_valid_rows(self):
        bad_space = ["9QQ 24CS922", "Probe Two", None, None, None, "Kolar",
                     None, None, None, None, None, None, None, None, None]
        no_usn = [None, "Probe Name Only", None, None, None, "Hassan", None,
                  None, None, None, None, None, None, None, None]
        good = [U3, "Probe Three", None, None, None, "Haveri", None, None,
                None, None, None, None, None, None, None]
        result = self.import_file("p6_invalid.xlsx", HEAD, [bad_space, no_usn, good])
        self.assertIsNone(one("SELECT usn FROM students WHERE usn=%s", ("9QQ 24CS922",)))
        self.assertEqual(count("SELECT COUNT(*) c FROM students WHERE name=%s",
                               ("Probe Name Only",)), 0,
                         "a name-only row in a file with no batch year must be "
                         "refused, never given an invented identity")
        self.assertEqual(val(U3, "district"), "Haveri",
                         "one bad row must not abort the good rows")
        self.assertEqual(result["invalid_rows"], 2)
        self.assertTrue(result["reconciled"],
                        f"row accounting lost rows: {result['total_accounted']}/{result['rows_parsed']}")
        reasons = {r["row_number"]: r["reason"] for r in result["rejected_rows"]}
        self.assertIn(1, reasons)
        self.assertTrue(reasons[1], "a rejected row must say why")

    # ── 5. a file with nothing valid must not open a transaction ─────────────
    def test_all_invalid_file_writes_nothing_at_all(self):
        snapshot = count("SELECT COUNT(*) c FROM students")
        with self.assertRaises(HTTPException) as ctx:
            self.import_file("p6_allbad.xlsx",
                             ["USN", "Student Name", "District"],
                             [["9QQ 24CS922", "Probe Two", "Kolar"],
                              ["X" * 120, "Probe Too Long", "Hassan"]])
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(count("SELECT COUNT(*) c FROM students"), snapshot)
        self.assertIsNone(one("SELECT usn FROM students WHERE usn=%s", (U2,)))
        self.assertIsNotNone(
            one("SELECT id FROM audit_log WHERE target_id=%s AND action=%s",
                ("p6_allbad.xlsx", "UPLOAD_VALIDATION_FAILED")))

    # ── 6. a blank cell in a later file must not erase a stored value ────────
    def test_blank_cell_in_a_later_file_does_not_erase_stored_data(self):
        self.import_file("p6_full.xlsx", HEAD, [ROW1])
        blank = [U1, "Probe Import One", None, "9888800000", None, None, None, None,
                 None, None, None, None, None, None, None]
        self.import_file("p6_blank.xlsx", HEAD, [blank])
        self.assertEqual(val(U1, "district"), "Kolar",
                         "an empty cell means 'nothing to say', not 'delete it'")
        self.assertEqual(val(U1, "phone"), "9888800000",
                         "the cell that WAS filled must still be written")
        self.assertEqual(val(U1, "blood_group"), "O+")
        self.assertEqual(sorted(r["semester"] for r in
                                rows("SELECT semester FROM marks WHERE usn=%s", (U1,))),
                         [3, 4], "a marks-free file must not drop academic history")

    # ── 6b. a marks-only sheet may omit the name, but only for a real student ─
    def test_marks_only_sheet_extends_an_existing_student_and_refuses_a_stranger(self):
        self.usns.append("9QQ24CS999")
        self.import_file("p6_full2.xlsx", HEAD, [ROW1])
        marks_only = ["USN", "Semester 5 SGPA"]
        self.import_file("p6_marks.xlsx", marks_only, [[U1, 7.1]])
        self.assertEqual(sorted(r["semester"] for r in
                                rows("SELECT semester FROM marks WHERE usn=%s", (U1,))),
                         [3, 4, 5])
        self.assertEqual(val(U1, "district"), "Kolar",
                         "a marks file must not blank the personal record")

        with self.assertRaises(HTTPException) as ctx:
            self.import_file("p6_marks_stranger.xlsx", marks_only, [["9QQ24CS999", 6.5]])
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIsNone(one("SELECT usn FROM students WHERE usn=%s", ("9QQ24CS999",)),
                          "an anonymous USN must never become a student")

    # ── 7. a corrected value overwrites and is reported as a conflict ────────
    def test_conflicting_value_overwrites_with_the_conflict_recorded(self):
        self.import_file("p6_v1.xlsx", HEAD, [ROW1])
        changed = list(ROW1)
        changed[5] = "Chikkaballapur"
        result = self.import_file("p6_v2.xlsx", HEAD, [changed])
        self.assertEqual(val(U1, "district"), "Chikkaballapur")
        self.assertEqual(result["students_updated"], 1)
        self.assertGreaterEqual(result["conflicts_count"], 1,
                                "overwriting a stored value must be visible, not silent")
        conflict = [c for c in result["conflicts"] if c["field"] == "district"]
        self.assertEqual((conflict[0]["old"], conflict[0]["new"]),
                         ("Kolar", "Chikkaballapur"))
        # the newer file owns the value now (latest active provenance row)
        self.assertEqual(
            one("SELECT source_filename FROM student_field_sources "
                "WHERE usn=%s AND field_name='district' AND is_active=1 "
                "ORDER BY uploaded_at DESC, id DESC LIMIT 1", (U1,))
            ["source_filename"], "p6_v2.xlsx")

    # ── 8. a mid-transaction failure rolls the whole import back ─────────────
    def test_mid_transaction_failure_rolls_back_completely(self):
        snapshot = count("SELECT COUNT(*) c FROM students")
        real_fees = RF._upsert_fees

        def explode(cur, usn, row):
            # second student blows up after the first was already written
            if usn == U2:
                raise RuntimeError("simulated driver failure in the import loop")
            return real_fees(cur, usn, row)

        original = RF._upsert_fees
        RF._upsert_fees = explode
        try:
            content = xlsx_bytes(HEAD, [ROW1, [U2, "Probe Two", None, None, None,
                                               "Kolar", None, None, None, None,
                                               None, None, None, None, None]])
            self.upload("p6_rollback.xlsx", content)
            with self.assertRaises(HTTPException) as ctx:
                self.commit("p6_rollback.xlsx")
        finally:
            RF._upsert_fees = original

        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("rolled back", str(ctx.exception.detail).lower())
        self.assertEqual(count("SELECT COUNT(*) c FROM students"), snapshot,
                         "a failed import must leave the table exactly as it was")
        self.assertIsNone(one("SELECT usn FROM students WHERE usn=%s", (U1,)),
                          "the row written before the failure must be undone too")
        ver = one("SELECT status FROM upload_versions WHERE filename=%s",
                  ("p6_rollback.xlsx",))
        self.assertEqual(ver["status"], "failed")
        self.assertIsNotNone(one("SELECT id FROM audit_log WHERE target_id=%s AND action=%s",
                                 ("p6_rollback.xlsx", "UPLOAD_FAILED")))

    # ── 9. messy fee vocabulary: money vs status vs unknown heading ─────────
    def test_fee_statuses_and_amounts_from_messy_cells(self):
        head = ["USN", "Student Name", "VTU Fee 1", "VTU Fee 2", "PD Fee 1",
                "Fee Tuition Paid", "Fee Pending"]
        self.import_file("p6_fees.xlsx", head,
                         [[U1, "Probe One", "Not Paid", "partially paid ", "paid",
                           "5000", "15000"]])
        got = rows("SELECT fee_type, year, status, amount_paid FROM student_fees "
                   "WHERE usn=%s", (U1,))
        keyed = {(f["fee_type"], f["year"]): f for f in got}
        self.assertIn(("VTU", 1), keyed, f"fee rows written: {got}")
        self.assertEqual(keyed[("VTU", 1)]["status"], "Not Paid")
        self.assertIn(("VTU", 2), keyed)
        self.assertEqual(keyed[("VTU", 2)]["status"].strip().lower(), "partially paid")
        self.assertIn(("PD", 1), keyed)
        # a fee heading the importer does not know must not vanish from the fee table
        self.assertIn("TUITION_PAID", [f["fee_type"] for f in got],
                      f"amount-bearing fee heading never reached student_fees: {got}")
        self.assertIn("PENDING", [f["fee_type"] for f in got],
                      "an unknown fee heading is invisible to every fee query")


    # ── 10. backlog text variants ───────────────────────────────────────────
    def test_backlog_text_variants_never_lose_a_reported_backlog(self):
        cases = [
            ("3", "3 backlog"),
            ("2.0", "2 backlogs"),
            ("Maths III, 5, 2024", "Maths III"),
            ("Physics IV*6,2025", "Physics IV"),
            ("Failed in 2 subjects this semester", "Failed in 2 subjects"),
        ]
        usns = ["9QQ24CS941", "9QQ24CS942", "9QQ24CS943", "9QQ24CS944", "9QQ24CS945"]
        self.usns.extend(usns)
        head = ["USN", "Student Name", "Backlogs"]
        self.import_file("p6_backlogs.xlsx", head,
                         [[usns[i], f"Probe {i}", cases[i][0]] for i in range(len(cases))])
        for usn, (typed, expected_subject) in zip(usns, cases):
            got = rows("SELECT subject FROM student_backlogs WHERE usn=%s", (usn,))
            self.assertTrue(got, f"backlog {typed!r} was reported but not stored for {usn}")
            self.assertIn(expected_subject, got[0]["subject"])
        # "no backlog" phrasings must not invent rows
        none_usns = ["9QQ24CS946", "9QQ24CS947"]
        self.usns.extend(none_usns)
        self.import_file("p6_no_backlogs.xlsx", head,
                         [[none_usns[0], "Probe A", "No"], [none_usns[1], "Probe B", "NIL"]])
        for usn in none_usns:
            self.assertEqual(
                count("SELECT COUNT(*) c FROM student_backlogs WHERE usn=%s", (usn,)), 0)

    # ── 11. dates, numbers and text as staff type them ──────────────────────
    def test_date_and_number_forms_land_as_the_column_type_requires(self):
        head = ["USN", "Student Name", "Date of Birth", "Phone", "Aadhar No", "CGPA"]
        self.import_file("p6_types.csv", head, [
            [U1, "Probe Dayfirst", "17-06-2005", "9000007777", "123456789012", "8.25"],
            [U2, "Probe ISO", "2005-06-17", "+91 9000007777", "1234 5678 9012", "7.5"],
            [U3, "Probe Garbage", "not a date", "9000007777.0", "2005-06-17", "9.999"],
        ], ext="csv")
        self.assertEqual(str(val(U1, "dob")), "2005-06-17")
        self.assertEqual(str(val(U2, "dob")), "2005-06-17")
        self.assertIsNone(val(U3, "dob"),
                          "an unparseable date must stay NULL, never become a guess")
        self.assertEqual(str(val(U1, "phone")), "9000007777")
        self.assertEqual(str(val(U3, "phone")), "9000007777",
                         f"trailing .0 survived: {val(U3, 'phone')!r}")
        self.assertEqual(str(val(U3, "aadhar_no")), "2005-06-17",
                         "recorded as typed: a wrong value in a wrong column must not be "
                         "silently dropped")
        self.assertAlmostEqual(float(val(U1, "cgpa")), 8.25, places=2)

    # ── 12. CSV encoding: BOM header and Kannada cells ──────────────────────
    def test_csv_with_bom_and_kannada_cells_imports_intact(self):
        head = ["USN", "Student Name", "District", "Father Name"]
        data = [[U1, "ಮನೋಜ ಕುಮಾರ್", "ಹಾಸನ", "ರಮೇಶ"],
                [U2, "Manoj Kumar", "Hassan", "Ramesh"]]
        self.import_file("p6_kannada.csv", head, data, ext="csv", bom=True)
        self.assertEqual(val(U1, "name"), "ಮನೋಜ ಕುಮಾರ್",
                         "Kannada script must survive the round trip byte for byte")
        self.assertEqual(val(U2, "name"), "Manoj Kumar")
        self.assertEqual(val(U2, "district"), "Hassan",
                         f"the BOM broke the first heading: {json.dumps(val(U1, 'district'), ensure_ascii=False)}")

    # ── 13. oversized values are truncated, never fatal ─────────────────────
    def test_overlong_values_are_truncated_instead_of_aborting_the_import(self):
        head = ["USN", "Student Name", "District"]
        self.import_file("p6_long.xlsx", head,
                         [[U1, "N" * 500, "D" * 300]])
        self.assertEqual(val(U1, "name"), "N" * 100)
        self.assertEqual(len(str(val(U1, "district"))), 100)

    # ── 14. hostile input stays data ────────────────────────────────────────
    def test_sql_shaped_cell_values_are_stored_as_text(self):
        head = ["USN", "Student Name", "District"]
        evil = "Robert'); DROP TABLE students;--"
        self.import_file("p6_evil.xlsx", head, [[U1, evil, "Kolar"]])
        self.assertEqual(val(U1, "name"), evil)
        self.assertEqual(val(U1, "district"), "Kolar")
        self.assertTrue(one("SELECT usn FROM students LIMIT 1"),
                        "the students table must still exist")

        tables_before = len(rows("SHOW TABLES"))
        self.assertEqual(tables_before, 36,
                         "the import must not create or drop tables")


    # ── 15. filenames are names, never paths ─────────────────────────────────
    def test_traversal_and_absolute_filenames_are_refused(self):
        import config
        upload_dir = os.path.realpath(config.settings.upload_dir_abs)
        hostile = ["../outside.xlsx", "..\\outside.xlsx",
                  "..\\..\\windows\\win.ini", "/etc/passwd",
                  "a/../../b.xlsx", "..", "", "C:\\Windows\\System32\\drivers\\etc\\hosts"]
        for name in hostile:
            try:
                resolved = os.path.realpath(RF._upload_path(name))
            except HTTPException as exc:
                self.assertEqual(exc.status_code, 400, name)
                continue
            self.assertEqual(os.path.dirname(resolved), upload_dir,
                             f"{name!r} escaped the upload directory")
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(upload_dir),
                                                    "outside.xlsx")))


    # ── 16. unreadable and unsupported uploads fail cleanly ─────────────────
    def test_empty_unsupported_and_disguised_files_are_refused_without_writes(self):
        snapshot = count("SELECT COUNT(*) c FROM students")
        with self.assertRaises(HTTPException) as ctx:
            self.upload("p6_empty.xlsx", b"")
        self.assertEqual(ctx.exception.status_code, 400)
        with self.assertRaises(HTTPException) as ctx:
            self.upload("p6_tool.exe", b"MZ\x90\x00")
        self.assertEqual(ctx.exception.status_code, 422)
        # a .xlsx whose bytes are really CSV must not import anything
        self.upload("p6_disguised.xlsx", b"USN,Student Name\n9QQ24CS922,Probe Two\n")
        with self.assertRaises(HTTPException) as ctx:
            self.commit("p6_disguised.xlsx")
        self.assertIn(ctx.exception.status_code, (422, 500))
        self.assertEqual(count("SELECT COUNT(*) c FROM students"), snapshot)
        self.assertIsNone(one("SELECT usn FROM students WHERE usn=%s", (U2,)))

    # ── 17. importing a file that is not in cache ───────────────────────────
    def test_import_of_an_unknown_filename_is_a_clean_404(self):
        with self.assertRaises(HTTPException) as ctx:
            self.commit("p6_never_uploaded.xlsx")
        self.assertEqual(ctx.exception.status_code, 404)

    # ── 18. a file with headers but no rows ─────────────────────────────────
    def test_header_only_file_is_refused_not_imported_empty(self):
        with self.assertRaises(HTTPException) as ctx:
            self.import_file("p6_headonly.xlsx", HEAD, [])
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIsNotNone(
            one("SELECT id FROM audit_log WHERE action=%s AND target_id=%s",
                ("UPLOAD_NO_DATA_ROWS", "p6_headonly.xlsx")),
            "a refusal must be visible to staff later, whichever guard rejected it")

    # ── 21. retiring one source file must not disfigure a shared student ─────
    def test_deleting_one_source_file_keeps_a_shared_student_identifiable(self):
        personal = ["USN", "Student Name", "District"]
        self.import_file("p6_own_a.xlsx", personal, [[U3, "Probe Three", "Haveri"]])
        self.import_file("p6_own_b.xlsx", ["USN", "Phone"], [[U3, "9888800000"]])
        self.assertEqual(val(U3, "district"), "Haveri")

        RF.delete_file("p6_own_a.xlsx", current_user=ADMIN)

        self.assertIsNotNone(one("SELECT usn FROM students WHERE usn=%s", (U3,)),
                             "another file still owns this student")
        self.assertEqual(val(U3, "phone"), "9888800000")
        self.assertEqual(val(U3, "name"), "Probe Three",
                         "a student row we deliberately keep must stay findable — "
                         "deleting one source file cannot leave it with no name")

    # ── 22. a file that introduced a student alone takes that student with it ─
    def test_deleting_the_only_source_file_retires_that_student_and_neighbours(self):
        personal = ["USN", "Student Name", "District", "Semester 1 SGPA"]
        self.import_file("p6_solo.xlsx", personal,
                         [[U3, "Probe Three", "Haveri", 7.0],
                          [U4, "Probe Four", "Kolar", 6.5]])
        self.import_file("p6_other.xlsx", personal, [[U4, "Probe Four", "Kolar", 6.5]])
        before = count("SELECT COUNT(*) c FROM students")

        RF.delete_file("p6_solo.xlsx", current_user=ADMIN)

        self.assertIsNone(one("SELECT usn FROM students WHERE usn=%s", (U3,)),
                          "the file that alone introduced the student was deleted")
        self.assertIsNotNone(one("SELECT usn FROM students WHERE usn=%s", (U4,)),
                             "another file still owns this one")
        self.assertEqual(count("SELECT COUNT(*) c FROM students"), before - 1)
        for table in ("marks", "student_fees", "student_backlogs"):
            self.assertEqual(count(f"SELECT COUNT(*) c FROM {table} WHERE usn=%s", (U3,)),
                             0, f"a retired student left orphan rows in {table}")
        self.assertEqual(count("SELECT COUNT(*) c FROM student_field_sources "
                               "WHERE usn=%s AND is_active=1", (U3,)), 0)

    # ── 23. the D0 family, at the import door: an expired-trash sweep may only
    #         retire students introduced by the file that was actually purged ──
    def test_expired_trash_purge_touches_no_other_student(self):
        seeded_before = count("SELECT COUNT(*) c FROM students "
                              "WHERE source_file IS NULL OR source_file NOT LIKE 'p6_%'")
        personal = ["USN", "Student Name", "District"]
        self.import_file("p6_trashed.xlsx", personal, [[U3, "Probe Three", "Haveri"]])
        # the file is now in Trash; make it older than the retention window
        write("UPDATE uploaded_files SET trashed_at=DATE_SUB(NOW(), INTERVAL 40 DAY), "
              "trash_path=NULL WHERE filename=%s", ("p6_trashed.xlsx",))
        total_before = count("SELECT COUNT(*) c FROM students")
        self.assertGreater(total_before, seeded_before, "fixture did not seed the file row")

        # any other upload runs the sweep on the write path (never on a read)
        self.import_file("p6_next.xlsx", personal, [[U4, "Probe Four", "Kolar"]])

        self.assertEqual(val(U4, "name"), "Probe Four", "the new import survived")
        self.assertEqual(
            count("SELECT COUNT(*) c FROM students "
                  "WHERE source_file IS NULL OR source_file NOT LIKE 'p6_%'"),
            seeded_before,
            "a trash sweep must not delete students it has no proof about (D0)")
        self.assertIsNone(one("SELECT usn FROM students WHERE usn=%s", (U3,)),
                          "the purged file's own student was meant to retire")
        self.assertIsNotNone(
            one("SELECT id FROM audit_log WHERE action=%s AND target_id LIKE %s",
                ("FILE_DATA_PURGE", "%" + U3 + "%")),
            "a data removal must be auditable")

        # …and recoverable: the sweep holds the BEFORE state in a committed
        # snapshot, so a mistaken retirement is not permanent.
        snap = one("SELECT undo_token, committed, snapshot_data FROM global_undo_snapshots "
                   "WHERE snapshot_data LIKE %s ORDER BY id DESC LIMIT 1",
                   ("%" + U3 + "%",))
        self.assertIsNotNone(snap, "a sweep removal must leave something to restore from")
        self.assertEqual(snap["committed"], 1,
                         "an uncommitted snapshot is refused by every restore door")
        self.assertIn("Probe Three", json.dumps(snap["snapshot_data"], default=str),
                      "the snapshot must hold the row as it was before it was removed")

        from routes_undo import restore_student
        restore_student(snap["undo_token"], current_user=ADMIN)
        self.assertEqual(val(U3, "name"), "Probe Three",
                         "undoing the sweep must bring the student back, not just claim to")
        self.assertEqual(val(U3, "district"), "Haveri")

    # ── 24. role gates on the import doors ──────────────────────────────────
    @staticmethod
    def _role_dependency(fn):
        """The require_roles closure FastAPI resolves for this route, plus the
        role set it actually enforces (read off the closure, not the docstring)."""
        for dep in (fn.__defaults__ or ()):
            inner = getattr(dep, "dependency", None)
            if inner is None or not getattr(inner, "__closure__", None):
                continue
            names = inner.__code__.co_freevars
            cells = [c.cell_contents for c in inner.__closure__]
            if "allowed_roles" in names:
                return inner, dict(zip(names, cells))["allowed_roles"]
        self.fail(f"{fn.__name__} has no role dependency to inspect")

    def test_role_gates_on_every_import_endpoint(self):
        doors = {
            RF.upload_file: {"staff", "admin"},
            RF.update_database: {"staff", "admin"},
            RF.delete_file: {"admin"},
            RF.list_trashed_files: {"admin"},
            RF.permanently_delete_trashed_file: {"admin"},
            RF.restore_trashed_file: {"admin"},
        }
        for fn, expected in doors.items():
            dep, roles = self._role_dependency(fn)
            self.assertEqual(roles, expected, f"{fn.__name__} admits {roles}")
            if "viewer" not in expected:
                with self.assertRaises(HTTPException) as ctx:
                    dep(current_user=VIEWER)
                self.assertEqual(ctx.exception.status_code, 403, fn.__name__)

        # Staff uploads (allowed) but the file stays out of the DB until imported
        self.upload("p6_staff.xlsx", xlsx_bytes(HEAD, [ROW1]), user=STAFF)
        self.assertIsNone(one("SELECT usn FROM students WHERE usn=%s", (U1,)))
        self.commit("p6_staff.xlsx", user=STAFF)
        self.assertEqual(val(U1, "name"), "Probe Import One")


    # ── 20. bulk import: 1000 students in one file, chunked ─────────────────
    def test_thousand_row_import_is_complete_and_exact(self):
        n = 1000
        # 9QQ is not a college code, so every bulk row is provably synthetic
        usns = [f"9QQ24CQ{i:04d}" for i in range(1000, 1000 + n)]
        self.usns.extend(usns)
        head = ["USN", "Student Name", "District", "Semester 1 SGPA"]
        data = [[usns[i], f"Bulk Student {i}", "Hassan" if i % 2 else "Kolar",
                 6.0 + (i % 40) / 10.0] for i in range(n)]
        started = time.time()
        result = self.import_file("p6_bulk1000.xlsx", head, data)
        elapsed = time.time() - started
        self.assertEqual(result["students_added"], n)
        self.assertEqual(result["rows_parsed"], n)
        self.assertTrue(result["reconciled"],
                        f"accounting drift: {result['total_accounted']}/{n}")
        self.assertEqual(count("SELECT COUNT(*) c FROM students WHERE usn LIKE '9QQ24CQ%'"), n)
        self.assertEqual(count("SELECT COUNT(*) c FROM marks WHERE usn LIKE '9QQ24CQ%'"), n)
        self.assertEqual(count("SELECT COUNT(DISTINCT district) c FROM students "
                               "WHERE usn LIKE '9QQ24CQ%'"), 2)
        # every semester must be present exactly once, no chunk-boundary loss
        dupes = rows("SELECT usn, COUNT(*) c FROM marks WHERE usn LIKE '9QQ24CQ%' "
                     "GROUP BY usn HAVING c <> 1")
        self.assertEqual(dupes, [])
        missing = [u for u in usns[:20] + usns[-20:]
                   if not one("SELECT usn FROM students WHERE usn=%s", (u,))]
        self.assertEqual(missing, [], "chunk boundary dropped rows")
        print(f"\n    [timing] 1000-row import: {elapsed:.1f}s "
              f"({n / max(elapsed, 0.001):.0f} rows/s)")

    # ── 25. undoing an import must remove every row that import wrote ────────
    def test_undoing_an_import_leaves_no_orphan_child_rows(self):
        head = ["USN", "Student Name", "Semester 3 SGPA", "VTU Fee 1",
                "Fee Pending", "Backlogs"]
        U5 = "9QQ24CS925"
        self.usns.append(U5)
        result = self.import_file("p6_undo_me.xlsx", head,
                                  [[U5, "Undo Probe Five", 7.5, "Paid", "1200",
                                    "Maths III, 5, 2024"]])
        self.assertEqual(result["students_added"], 1)
        # the import really wrote children in every table before we undo it
        self.assertEqual(count("SELECT COUNT(*) c FROM marks WHERE usn=%s", (U5,)), 1)
        self.assertEqual(count("SELECT COUNT(*) c FROM student_fees WHERE usn=%s", (U5,)), 2)
        self.assertEqual(count("SELECT COUNT(*) c FROM student_backlogs WHERE usn=%s",
                               (U5,)), 1)
        self.assertGreater(
            count("SELECT COUNT(*) c FROM student_field_sources WHERE usn=%s", (U5,)), 0,
            "the import must have booked provenance for the fields it wrote")
        token = result["restore_tokens"][0]["token"]

        from routes_undo import restore_student
        restore_student(token, current_user=ADMIN)

        for table in ("students", "marks", "student_fees", "student_backlogs",
                      "student_field_sources"):
            self.assertEqual(
                count(f"SELECT COUNT(*) c FROM {table} WHERE usn=%s", (U5,)), 0,
                f"undoing the import left orphan rows in {table}")

        # and the file card must stop claiming the data is in the database
        card = one("SELECT db_status FROM uploaded_files WHERE filename=%s",
                   ("p6_undo_me.xlsx",))
        self.assertIsNotNone(card, "the uploaded_files row must survive its undo")
        self.assertEqual(
            card["db_status"], "pending",
            "an undone import must not leave its file marked 'Imported'")

    # ── 26. an NL delete must not orphan the fee/arrears children either ─────
    def test_nl_delete_leaves_no_orphan_child_rows_and_undo_restores_them(self):
        import routes_query as RQ
        from routes_undo import restore_student

        head = ["USN", "Student Name", "VTU Fee 1", "Backlogs"]
        U6 = "9QQ24CS926"
        self.usns.append(U6)
        self.import_file("p6_nl_delete.xlsx", head,
                         [[U6, "Delete Probe Six", "Pending", "Physics, 6, 2025"]])
        self.assertEqual(count("SELECT COUNT(*) c FROM student_fees WHERE usn=%s", (U6,)), 1)
        self.assertEqual(count("SELECT COUNT(*) c FROM student_backlogs WHERE usn=%s",
                               (U6,)), 1)
        prov_before = count("SELECT COUNT(*) c FROM student_field_sources WHERE usn=%s",
                            (U6,))
        self.assertGreater(prov_before, 0)

        gen = RQ.generate_query(
            RQ.QueryRequest(natural_query=f"delete student {U6}", language="english"),
            current_user=ADMIN)
        self.assertEqual(gen["action_type"], "DELETE", f"not read as a delete: {gen}")
        RQ.execute_confirmed(
            RQ.ExecuteRequest(query_dict=gen["query_dict"],
                              original_query=f"delete student {U6}",
                              confirmed=True,
                              confirmation_token=gen["confirmation_token"]),
            current_user=ADMIN)

        for table in ("students", "marks", "student_fees", "student_backlogs",
                      "student_field_sources"):
            self.assertEqual(
                count(f"SELECT COUNT(*) c FROM {table} WHERE usn=%s", (U6,)), 0,
                f"the NL delete left orphan rows in {table}")

        # and the delete is still fully reversible: the fee and arrears rows
        # the snapshot held come back with the student.
        undo = one("SELECT undo_token FROM global_undo_snapshots "
                   "WHERE snapshot_data LIKE %s AND operation_type='DELETE' "
                   "AND committed=1 AND undone=0 ORDER BY id DESC LIMIT 1",
                   ("%" + U6 + "%",))
        self.assertIsNotNone(undo, "the NL delete must leave a committed snapshot")
        restore_student(undo["undo_token"], current_user=ADMIN)
        self.assertEqual(val(U6, "name"), "Delete Probe Six")
        self.assertEqual(count("SELECT COUNT(*) c FROM student_fees WHERE usn=%s", (U6,)), 1)
        self.assertEqual(count("SELECT COUNT(*) c FROM student_backlogs WHERE usn=%s",
                               (U6,)), 1)
        self.assertEqual(
            count("SELECT COUNT(*) c FROM student_field_sources WHERE usn=%s", (U6,)),
            prov_before, "the delete undo must bring the provenance rows back")


if __name__ == "__main__":
    unittest.main(verbosity=2)
