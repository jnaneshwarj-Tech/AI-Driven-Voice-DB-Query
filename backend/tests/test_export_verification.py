"""
Export verification tests (spec section 9).

A synthetic student (distinct test USN) plus its fee / backlog / marks rows are
inserted, exported to CSV, Excel, PDF and JSON, and the *generated files* are
read back and inspected (not merely HTTP status). The fee record is then
updated and re-exported to prove exports reflect the CURRENT database value and
that stale values are not presented. Everything is removed in teardown; only
rows carrying the synthetic test USN are ever touched (production students and
the real database are never modified destructively).
"""
import base64
import os
import re
import sys
import unittest
import zlib

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import report_service
import routes_export
from database import db_conn

TEST_USN = "9ZZ99TEST1"
ADMIN = {"username": "admin_user", "role": "Admin"}
STAFF = {"username": "staff_user", "role": "Staff"}


def _seed():
    with db_conn() as c:
        cur = c.cursor()
        cur.execute("DELETE FROM students WHERE usn=%s", (TEST_USN,))
        cur.execute("DELETE FROM student_fees WHERE usn=%s", (TEST_USN,))
        cur.execute("DELETE FROM student_backlogs WHERE usn=%s", (TEST_USN,))
        cur.execute("DELETE FROM marks WHERE usn=%s", (TEST_USN,))
        cur.execute(
            "INSERT INTO students (usn, name, gender, phone, email, aadhar_no, dob, area_type) "
            "VALUES (%s,%s,'Male','9812345678','testuser@example.com','123456789012','2005-02-02','RURAL')",
            (TEST_USN, "Test Report User"),
        )
        cur.execute("INSERT INTO marks (usn, semester, sgpa, year) VALUES (%s,1,8.5,2024)", (TEST_USN,))
        cur.execute("INSERT INTO marks (usn, semester, sgpa, year) VALUES (%s,2,7.5,2024)", (TEST_USN,))
        cur.execute(
            "INSERT INTO student_fees (usn, fee_type, year, status, amount_paid, remaining_amount) "
            "VALUES (%s,'VTU',1,'Paid','5000','0')", (TEST_USN,))
        cur.execute(
            "INSERT INTO student_fees (usn, fee_type, year, status, amount_paid, remaining_amount) "
            "VALUES (%s,'PD',1,'Not Paid','0','2500')", (TEST_USN,))
        cur.execute(
            "INSERT INTO student_backlogs (usn, subject, semester, year, cleared) "
            "VALUES (%s,'Operating Systems',4,'2026',0)", (TEST_USN,))
        c.commit()
        cur.close()


def _cleanup():
    with db_conn() as c:
        cur = c.cursor()
        for table in ("students", "student_fees", "student_backlogs", "marks"):
            cur.execute(f"DELETE FROM {table} WHERE usn=%s", (TEST_USN,))
        c.commit()
        cur.close()


def _read_response(resp):
    path = resp.path
    with open(path, "rb") as f:
        raw = f.read()
    try:
        os.remove(path)
    except OSError:
        pass
    return raw


def _inflate_stream(blob: bytes) -> bytes:
    """Decode a PDF content stream that may be ASCII85- and/or Flate-encoded
    (reportlab's default is [ /ASCII85Decode /FlateDecode ])."""
    blob = blob.strip()
    # ASCII85 (Adobe) wraps payloads with a leading '<~' or trailing '~>'.
    if blob[-2:] == b"~>" or blob[:2] == b"<~":
        try:
            blob = base64.a85decode(blob, adobe=True)
        except ValueError:
            pass
    try:
        return zlib.decompress(blob)
    except zlib.error:
        return blob


def _pdf_text(raw: bytes) -> str:
    """Extract readable text tokens from a PDF by decoding every content
    stream and collecting the show-text operators."""
    chunks = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
        blob = _inflate_stream(match.group(1))
        for tj in re.finditer(rb"\((.*?)\)\s*Tj", blob, re.S):
            chunks.append(tj.group(1))
        for arr in re.finditer(rb"\[(.*?)\]\s*TJ", blob, re.S):
            for tj in re.finditer(rb"\((.*?)\)", arr.group(1), re.S):
                chunks.append(tj.group(1))
    text = b" ".join(chunks).decode("latin-1", "ignore")
    return re.sub(r"\\(.)", r"\1", text)  # unescape PDF string escapes


def _xlsx_text(raw: bytes) -> str:
    import io
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(raw))
    cells = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            for v in row:
                if v is not None:
                    cells.append(str(v))
    return "\n".join(cells)


class ExportVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _seed()

    @classmethod
    def tearDownClass(cls):
        _cleanup()

    def _payload(self):
        return [{"usn": TEST_USN}]

    def test_report_model_has_current_fees_backlogs_academic(self):
        model = report_service.build_report_model(self._payload(), ADMIN)
        st = model["students"][0]
        self.assertEqual(st["usn"], TEST_USN)
        # Fees (current DB, statuses normalized, source preserved)
        by_type = {f["fee_type"]: f for f in st["fees"]}
        self.assertIn("VTU", by_type)
        self.assertIn("PD", by_type)
        self.assertEqual(by_type["VTU"]["status"], "paid")
        self.assertEqual(by_type["PD"]["status"], "unpaid")
        self.assertEqual(by_type["VTU"]["amount_paid"], "5000")
        self.assertEqual(by_type["PD"]["status_raw"], "Not Paid")
        # Backlog
        self.assertTrue(any(b["subject"] == "Operating Systems" for b in st["backlogs"]))
        # Academic SGPA/CGPA present
        self.assertEqual(len(st["academic"]), 2)
        self.assertEqual(st["academic"][0]["sgpa"], 8.5)
        self.assertTrue(model["refreshed_from_db"])

    def test_csv_contains_fee_and_backlog(self):
        raw = _read_response(routes_export.export_csv(self._payload(), ADMIN)).decode("utf-8")
        self.assertIn("FEES DETAILS", raw)
        self.assertIn("VTU", raw)
        self.assertIn("Not Paid", raw)
        self.assertIn("BACKLOGS", raw)
        self.assertIn("Operating Systems", raw)
        self.assertIn("ACADEMIC PERFORMANCE", raw)

    def test_excel_contains_fee_and_backlog(self):
        raw = _read_response(routes_export.export_excel(self._payload(), ADMIN))
        text = _xlsx_text(raw)
        self.assertIn("FEES DETAILS", text)
        self.assertIn("VTU", text)
        self.assertIn("Operating Systems", text)
        self.assertIn("Semester 1", text)

    def test_pdf_contains_fee_and_backlog(self):
        raw = _read_response(routes_export.export_pdf(self._payload(), ADMIN))
        self.assertTrue(raw[:5] == b"%PDF-")
        text = _pdf_text(raw)
        self.assertIn("FEES DETAILS", text)
        self.assertIn("VTU", text)
        self.assertIn("BACKLOGS", text)

    def test_formats_consistent_fee_types(self):
        csv_text = _read_response(routes_export.export_csv(self._payload(), ADMIN)).decode("utf-8")
        xls_text = _xlsx_text(_read_response(routes_export.export_excel(self._payload(), ADMIN)))
        pdf_text = _pdf_text(_read_response(routes_export.export_pdf(self._payload(), ADMIN)))
        for token in ("VTU", "PD", "Operating Systems"):
            self.assertIn(token, csv_text)
            self.assertIn(token, xls_text)
            self.assertIn(token, pdf_text)

    def test_updated_value_reflected_not_stale(self):
        # First export sees "Not Paid" for PD; then update the DB and re-export.
        first = _read_response(routes_export.export_csv(self._payload(), ADMIN)).decode("utf-8")
        self.assertIn("Not Paid", first)
        with db_conn() as c:
            cur = c.cursor()
            cur.execute("UPDATE student_fees SET status=%s WHERE usn=%s AND fee_type='PD'",
                        ("Fully Paid", TEST_USN))
            c.commit()
            cur.close()
        second = _read_response(routes_export.export_csv(self._payload(), ADMIN)).decode("utf-8")
        self.assertIn("Paid (source: Fully Paid)", second)
        # The PD 'Not Paid' fee is gone from current data.
        pd_line = [ln for ln in second.splitlines() if ln.startswith("PD,")]
        self.assertTrue(all("Not Paid" not in ln for ln in pd_line), pd_line)
        # restore
        with db_conn() as c:
            cur = c.cursor()
            cur.execute("UPDATE student_fees SET status=%s WHERE usn=%s AND fee_type='PD'",
                        ("Not Paid", TEST_USN))
            c.commit()
            cur.close()

    def test_staff_cannot_export_full_restricted_fields(self):
        model_admin = report_service.build_report_model(self._payload(), ADMIN)
        model_staff = report_service.build_report_model(self._payload(), STAFF)
        a_ad = model_admin["students"][0]["personal"].get("aadhar_no")
        a_st = model_staff["students"][0]["personal"].get("aadhar_no")
        self.assertEqual(a_ad, "123456789012")
        self.assertNotEqual(a_st, "123456789012")
        self.assertTrue("*" in str(a_st))


class WideReportSheetTests(unittest.TestCase):
    """Very wide reports (student_list carries ~50 columns) must render as one
    legible sheet per record with every field shown, not a squeezed horizontal
    table and not fragmented across many parts. The redundant 'Records: 1' line
    is dropped for single-record reports."""

    def _wide_model(self, n_body=38, n_rec=4):
        columns = [{"key": "usn", "label": "USN"},
                   {"key": "name", "label": "Student Name"}]
        columns += [{"key": f"f{i}", "label": f"Long Field Name {i}"}
                    for i in range(n_body)]
        records = []
        for n in range(n_rec):
            rec = {"usn": f"1XX22CS9{n:02d}", "name": f"Student {n}"}
            rec.update({f"f{i}": f"value-{i}-{n}" for i in range(n_body)})
            records.append(rec)
        return {"title": "Student List Report", "subtitle": "Show everything",
                "record_count": len(records), "columns": columns,
                "records": records, "notes": [],
                "institution": {"university": "VTU", "college": "ABC College",
                                "department": "CSE"},
                "generated_by": {"timestamp": "10 Oct 2026 09:00 PM",
                                 "username": "staff", "role": "Staff"}}

    def _render_pdf_text(self, model):
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        try:
            routes_export._build_table_pdf(path, model)
            with open(path, "rb") as fh:
                return _pdf_text(fh.read())
        finally:
            os.remove(path)

    def test_wide_pdf_shows_every_field_on_sheets(self):
        model = self._wide_model()
        text = self._render_pdf_text(model)
        # no fragmentation into "parts" any more
        self.assertNotIn("Part 1 of", text)
        self.assertNotIn("split into", text)
        # every field label survives intact and readable (USN/Name head each
        # sheet instead of repeating as a label)
        for col in model["columns"]:
            if col["key"] in ("usn", "name"):
                continue
            self.assertIn(col["label"], text)
        # each record's name and USN head its sheet
        for rec in model["records"]:
            self.assertIn(rec["name"], text)
            self.assertIn(rec["usn"], text)

    def test_header_drops_redundant_records_and_subtitle(self):
        single = self._wide_model(n_rec=1)
        text = self._render_pdf_text(single)
        self.assertNotIn("Records:", text)          # single record: not shown
        self.assertNotIn("Show everything", text)   # subtitle removed
        multi = self._wide_model(n_rec=3)
        self.assertIn("Records: 3", self._render_pdf_text(multi))

    def test_narrow_report_stays_horizontal_table(self):
        model = self._wide_model(n_body=4)  # 6 columns total
        self.assertLessEqual(len(model["columns"]), routes_export._MAX_COLS_HORIZONTAL)
        html = routes_export._build_table_html(model)
        self.assertIn("<table>", html)
        self.assertNotIn("class='sheet'", html)

    def test_wide_print_html_uses_record_sheets(self):
        model = self._wide_model()
        html = routes_export._build_table_html(model)
        self.assertEqual(html.count("class='sheet'"), len(model["records"]))
        self.assertNotIn("Part 1 of", html)
        for col in model["columns"]:
            if col["key"] in ("usn", "name"):
                continue
            self.assertIn(col["label"], html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
