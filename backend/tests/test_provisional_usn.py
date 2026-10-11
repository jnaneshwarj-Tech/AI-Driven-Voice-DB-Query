"""
test_provisional_usn.py — no-USN (name-only) file uploads get temporary VTU USNs.

Feature: when a student file carries names but no USN column, the import assigns
a provisional VTU-format USN (e.g. 4HG26CS001) whose batch year comes from a
'20YY' token in the filename, with serials allocated in ASCENDING NAME ORDER.

Test policy (mirrors the project Testing Rule):
  * The allocation/sort/skip logic is verified as pure functions against an
    in-memory FakeCursor — expected values are computed independently of the
    code under test, with no writes to the shared MySQL database.
  * One DB integration test writes a single synthetic USN (prefix '9ZZ', never a
    real college code) via the real upsert path, asserts the persisted
    usn_provisional flag against actual MySQL, and deletes exactly that row.
  * No production student is ever inserted, mutated, or removed.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from database import db_conn
from graduation_manager import parse_usn_full
import routes_files as RF


class FakeCursor:
    """Emulates the three read-only queries _assign_provisional_usns/_infer_usn_scheme issue."""
    def __init__(self, dominant_prefix=None, dominant_branch=None, existing_usns=()):
        self._dominant_prefix = dominant_prefix
        self._dominant_branch = dominant_branch
        self._existing = list(existing_usns)
        self._last = ""

    def execute(self, sql, params=()):
        self._last = " ".join(sql.split())

    def fetchone(self):
        s = self._last
        if s.startswith("SELECT LEFT(usn,3)"):
            return {"p": self._dominant_prefix, "c": 1} if self._dominant_prefix else None
        if s.startswith("SELECT SUBSTRING(usn,6,2)"):
            return {"b": self._dominant_branch, "c": 1} if self._dominant_branch else None
        return None

    def fetchall(self):
        if self._last.startswith("SELECT usn FROM students WHERE usn LIKE"):
            return [{"usn": u} for u in self._existing]
        return []


class BatchYearTests(unittest.TestCase):
    def test_two_digit_slot_extracted(self):
        self.assertEqual(RF._batch_year_from_filename("2026 batch.xlsx"), "26")
        self.assertEqual(RF._batch_year_from_filename("BE 2025 CS students.csv"), "25")

    def test_no_year_returns_none(self):
        self.assertIsNone(RF._batch_year_from_filename("roster-final.xlsx"))
        self.assertIsNone(RF._batch_year_from_filename(""))


class BranchCodeTests(unittest.TestCase):
    def test_common_branches_map(self):
        self.assertEqual(RF._map_branch_code("CSE"), "CS")
        self.assertEqual(RF._map_branch_code("Computer Science and Engineering"), "CS")
        self.assertEqual(RF._map_branch_code("ECE"), "EC")
        self.assertEqual(RF._map_branch_code("Mechanical"), "ME")

    def test_unknown_or_empty(self):
        self.assertIsNone(RF._map_branch_code(""))
        self.assertIsNone(RF._map_branch_code(None))
        self.assertIsNone(RF._map_branch_code("Zoology"))


class ProvisionalAllocationTests(unittest.TestCase):
    def test_ascending_name_order_allocates_serials(self):
        rows = [{"name": "Zara", "usn": ""}, {"name": "Amit", "usn": ""}, {"name": "Meera", "usn": ""}]
        cur = FakeCursor(dominant_prefix="4HG", dominant_branch="CS", existing_usns=())
        assigned = RF._assign_provisional_usns(cur, rows, "2026 batch.xlsx")
        # Independent truth: order by ascending name -> Amit, Meera, Zara -> 001,002,003
        self.assertEqual(rows[1]["usn"], "4HG26CS001")  # Amit
        self.assertEqual(rows[2]["usn"], "4HG26CS002")  # Meera
        self.assertEqual(rows[0]["usn"], "4HG26CS003")  # Zara
        self.assertEqual(set(assigned), {"4HG26CS001", "4HG26CS002", "4HG26CS003"})
        self.assertEqual(assigned["4HG26CS001"], "Amit")

    def test_skips_serials_already_in_db(self):
        rows = [{"name": "Ann", "usn": ""}, {"name": "Bob", "usn": ""}]
        cur = FakeCursor(dominant_prefix="4HG", dominant_branch="CS",
                         existing_usns=["4HG26CS001", "4HG26CS002"])
        RF._assign_provisional_usns(cur, rows, "2026 batch.xlsx")
        self.assertEqual(rows[0]["usn"], "4HG26CS003")  # Ann
        self.assertEqual(rows[1]["usn"], "4HG26CS004")  # Bob

    def test_real_usns_in_same_file_are_reserved(self):
        rows = [{"name": "Arun", "usn": "4HG26CS001"}, {"name": "Bala", "usn": ""}]
        cur = FakeCursor(dominant_prefix="4HG", dominant_branch="CS", existing_usns=())
        RF._assign_provisional_usns(cur, rows, "2026 batch.xlsx")
        self.assertEqual(rows[0]["usn"], "4HG26CS001")  # untouched real USN
        self.assertEqual(rows[1]["usn"], "4HG26CS002")  # Bala skips 001

    def test_no_batch_year_leaves_rows_unchanged(self):
        rows = [{"name": "Sita", "usn": ""}]
        cur = FakeCursor(dominant_prefix="4HG", dominant_branch="CS")
        assigned = RF._assign_provisional_usns(cur, rows, "class-roster.xlsx")
        self.assertEqual(assigned, {})
        self.assertEqual(rows[0]["usn"], "")  # not invented

    def test_placeholder_name_is_not_provisioned(self):
        # A row whose only 'name' is a null placeholder ('None') is not a real
        # student; we must not fabricate a USN for it.
        rows = [{"name": "None", "usn": ""}]
        cur = FakeCursor(dominant_prefix="4HG", dominant_branch="CS")
        assigned = RF._assign_provisional_usns(cur, rows, "2026 batch.xlsx")
        self.assertEqual(assigned, {})
        self.assertEqual(rows[0]["usn"], "")

    def test_existing_usn_rows_never_reassigned(self):
        rows = [{"name": "Has", "usn": "4HG23CS010"}, {"name": "Nila", "usn": ""}]
        cur = FakeCursor(dominant_prefix="4HG", dominant_branch="CS", existing_usns=())
        assigned = RF._assign_provisional_usns(cur, rows, "2026 batch.xlsx")
        self.assertEqual(rows[0]["usn"], "4HG23CS010")
        self.assertEqual(rows[1]["usn"], "4HG26CS001")
        self.assertEqual(list(assigned), ["4HG26CS001"])

    def test_default_scheme_is_4hg_cs(self):
        # No dominant prefix/branch evident -> defaults 4HG / CS.
        rows = [{"name": "Kiran", "usn": ""}]
        cur = FakeCursor(dominant_prefix=None, dominant_branch=None, existing_usns=())
        RF._assign_provisional_usns(cur, rows, "2026 batch.xlsx")
        self.assertEqual(rows[0]["usn"], "4HG26CS001")

    def test_generated_usn_is_regular_2026_batch(self):
        parsed = parse_usn_full("4HG26CS001")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["admission_batch"], 2026)
        self.assertEqual(parsed["student_type"], "Regular")
        self.assertEqual(parsed["roll_number"], 1)
        self.assertTrue(parsed["college_code"] == "HG")


PROVISIONAL_SYNTH_USN = "9ZZ26CS777"  # degree 9 / college ZZ — never a real code


class ProvisionalUpsertDBTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        cls._cleanup()

    @staticmethod
    def _cleanup():
        with db_conn() as conn:
            cur = conn.cursor()
            for tbl in ("students", "student_field_sources"):
                cur.execute(f"DELETE FROM {tbl} WHERE usn=%s", (PROVISIONAL_SYNTH_USN,))
            conn.commit()
            cur.close()

    def test_upsert_marks_provisional_flag(self):
        self._cleanup()
        payload = {"name": "Provisional One", "branch": "CSE", "gender": "Male"}
        try:
            with db_conn() as conn:
                conn.autocommit = False
                cur = conn.cursor(dictionary=True)
                result, _ = RF._upsert_student(
                    cur, PROVISIONAL_SYNTH_USN, payload,
                    source_filename="provisional-test.xlsx", import_id=None, provisional=True,
                )
                conn.commit()
                cur.close()
            self.assertEqual(result, "added")
            with db_conn() as conn:
                cur = conn.cursor(dictionary=True)
                cur.execute("SELECT usn, name, usn_provisional FROM students WHERE usn=%s",
                            (PROVISIONAL_SYNTH_USN,))
                row = cur.fetchone()
                cur.close()
            self.assertIsNotNone(row, "synthetic provisional student was not persisted")
            self.assertEqual(row["name"], "Provisional One")
            self.assertEqual(int(row["usn_provisional"]), 1)
        finally:
            self._cleanup()
        # Confirm the row is truly gone (no leak into production data).
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM students WHERE usn=%s", (PROVISIONAL_SYNTH_USN,))
            self.assertEqual(cur.fetchone()[0], 0)
            cur.close()


if __name__ == "__main__":
    unittest.main()
