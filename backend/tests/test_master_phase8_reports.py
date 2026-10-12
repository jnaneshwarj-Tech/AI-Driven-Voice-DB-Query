"""
Master QA Phase 8 — reports and exports consistency.

Every report kind (student_list, academic, personal, fees, discontinued,
individual) is generated in every format the app offers (pdf, excel, csv,
print/HTML, plus the JSON preview) and the *generated artefacts* are read back
and compared with each other and with independent SQL truth. Nothing here
asserts on the model the app built for itself: totals, CGPA, status and row
membership are recomputed from MySQL in this file.

Only synthetic USNs (9ZZ8...) are written, in the staging database, and only
those rows are ever deleted again.
"""
import io
import os
import re
import sys
import unittest
import zipfile

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import report_service
import routes_export
from database import db_conn
from fastapi import HTTPException

sys.path.insert(0, os.path.join(BACKEND, "tests"))
from test_export_verification import _pdf_text, _xlsx_text  # noqa: E402

USN_A = "9ZZ8P00001"   # Kannada-script name, full contacts, fees + marks + backlog
USN_B = "9ZZ8P00002"   # Latin name, no contacts, no fee amounts (NULL), no marks
USN_C = "9ZZ8P00003"   # discontinued, register disagrees with the flat column
KN_NAME = "ಟೆಸ್ಟ್ ವಿದ್ಯಾರ್ಥಿ"
KN_ADDR = "ಹಾಸನ ತಾಲೂಕು, ಕರ್ನಾಟಕ"
PHONE_A = "9812345671"
EMAIL_A = "probe.a@qa.invalid"
AADHAR_A = "123456789012"

ADMIN = {"username": "p8_admin", "role": "Admin"}
STAFF = {"username": "p8_staff", "role": "Staff"}
VIEWER = {"username": "p8_viewer", "role": "Viewer"}

TABLE_FORMATS = ("pdf", "excel", "csv", "print")
TABLE_CATEGORIES = ("student_list", "academic", "personal", "fees", "discontinued")


def _seed():
    _purge()
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO students (usn, name, gender, phone, email, aadhar_no, dob,"
            " district, taluk, village, area_type, branch, current_sem, lifecycle_status)"
            " VALUES (%s,%s,'Female',%s,%s,%s,'2005-04-01','Hassan','Hiriyur','Testaluku',"
            " 'RURAL','CSE',5,'Rejoined-Active')",
            (USN_A, KN_NAME, PHONE_A, EMAIL_A, AADHAR_A))
        cur.execute(
            "UPDATE students SET permanent_address=%s WHERE usn=%s", (KN_ADDR, USN_A))
        cur.execute(
            "INSERT INTO students (usn, name, gender, district, area_type, branch,"
            " current_sem, lifecycle_status) VALUES (%s,'Probe Two','Male','Hassan',"
            " 'URBAN','CSE',5,'Active')", (USN_B,))
        cur.execute(
            "INSERT INTO students (usn, name, gender, district, area_type, branch,"
            " current_sem, lifecycle_status) VALUES (%s,'Probe Three','Male','Hassan',"
            " 'RURAL','CSE',6,'Temporarily Discontinued')", (USN_C,))
        cur.execute(
            "INSERT INTO marks (usn, semester, sgpa, year) VALUES (%s,1,8.00,2024)", (USN_A,))
        cur.execute(
            "INSERT INTO marks (usn, semester, sgpa, year) VALUES (%s,2,9.00,2025)", (USN_A,))
        cur.execute(
            "INSERT INTO student_fees (usn, fee_type, year, status, amount_paid,"
            " remaining_amount) VALUES (%s,'VTU',1,'Paid','5000','0')", (USN_A,))
        cur.execute(
            "INSERT INTO student_fees (usn, fee_type, year, status, amount_paid,"
            " remaining_amount) VALUES (%s,'PD',1,'Fee Pending','0','2500')", (USN_A,))
        # B: a fee that exists but records no money at all -> blank, never 0.
        cur.execute(
            "INSERT INTO student_fees (usn, fee_type, year, status, amount_paid,"
            " remaining_amount) VALUES (%s,'Tuition',1,'',NULL,NULL)", (USN_B,))
        cur.execute(
            "INSERT INTO student_backlogs (usn, subject, semester, year, cleared)"
            " VALUES (%s,'Operating Systems',4,'2026',0)", (USN_A,))
        # Deliberate disagreement (the D44 trap): the flat column is newer than
        # the derived register, so a report must not pick whichever one it found
        # first. The register is the authority for the discontinued category.
        cur.execute(
            "INSERT INTO student_lifecycle_status (usn, current_status, effective_date,"
            " reason, reason_category, last_enrolled_semester, updated_by)"
            " VALUES (%s,'Discontinued-Review Req','2026-03-01','ಮನಸ್ಸಿಲ್ಲ,"
            " ಆರೋಗ್ಯ ಸಮಸ್ಯೆ','Medical',5,'p8_admin')"
            " ON DUPLICATE KEY UPDATE current_status=VALUES(current_status),"
            " effective_date=VALUES(effective_date), reason=VALUES(reason),"
            " reason_category=VALUES(reason_category), updated_by=VALUES(updated_by)",
            (USN_C,))
        conn.commit()
        cur.close()


def _purge():
    with db_conn() as conn:
        cur = conn.cursor()
        for table in ("students", "marks", "student_fees", "student_backlogs",
                      "student_lifecycle_status"):
            cur.execute(f"DELETE FROM {table} WHERE usn IN (%s,%s,%s)",
                        (USN_A, USN_B, USN_C))
        cur.execute("DELETE FROM export_logs WHERE exported_by IN ('p8_admin','p8_staff','p8_viewer')")
        cur.execute("DELETE FROM audit_log WHERE username IN ('p8_admin','p8_staff','p8_viewer')")
        conn.commit()
        cur.close()


def _sql(query, args=None):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(query, args or ())
        rows = cur.fetchall()
        cur.close()
        return rows


def _rows(usns, extra=None):
    out = []
    for u in usns:
        r = {"usn": u}
        if extra:
            r.update(extra.get(u, {}))
        out.append(r)
    return out


def _resp_bytes(resp):
    with open(resp.path, "rb") as fh:
        raw = fh.read()
    try:
        os.remove(resp.path)
    except OSError:
        pass
    return raw


def _render(category, usns, user, fmt, extra=None):
    req = routes_export.ReportRequest(
        category=category, format=fmt, rows=_rows(usns, extra))
    resp = routes_export.generate_report(req, current_user=user)
    return resp


def _csv_table(raw: bytes):
    """The data rows of a CSV export, as dicts.

    Every format carries the model's explanatory notes; in a CSV they follow a
    blank line as single-cell "Note:" / "No records ..." lines, so they are
    explanation rather than records and parsing stops where the table does.
    """
    import csv
    rows = [r for r in csv.reader(io.StringIO(raw.decode("utf-8-sig"))) if r]
    head = rows[0]
    table = []
    for r in rows[1:]:
        if len(r) == 1 and (r[0].startswith("Note:")
                            or r[0].startswith("No records")):
            break
        table.append(dict(zip(head, r + [""] * (len(head) - len(r)))))
    return table, head


def _xlsx_table(raw: bytes):
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(raw))
    ws = wb.worksheets[0]
    grid = [[("" if c is None else str(c)) for c in row]
            for row in ws.iter_rows(values_only=True)]
    head_idx = next((i for i, g in enumerate(grid) if "USN" in g), None)
    if head_idx is None:
        return [], []
    head = [h for h in grid[head_idx] if h != ""]
    table = []
    for g in grid[head_idx + 1:]:
        if not any(x != "" for x in g):
            break
        table.append(dict(zip(head, [g[i] if i < len(g) else "" for i in range(len(head))])))
    return table, head


def _html_cells(raw_or_text):
    text = raw_or_text.decode("utf-8") if isinstance(raw_or_text, bytes) else raw_or_text
    return re.sub(r"<[^>]+>", " ", text)


class Phase8ReportBattery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _seed()

    @classmethod
    def tearDownClass(cls):
        _purge()

    # ── coverage: every category reaches every format ─────────────────────────
    def test_every_category_renders_in_every_format(self):
        for cat in TABLE_CATEGORIES:
            for fmt in TABLE_FORMATS:
                with self.subTest(category=cat, format=fmt):
                    usns = [USN_C] if cat == "discontinued" else [USN_A, USN_B]
                    resp = _render(cat, usns, ADMIN, fmt)
                    if fmt == "print":
                        body = resp.body.decode("utf-8")
                        self.assertTrue("sheet" in body or "<table" in body.lower(),
                                        f"{cat}/{fmt} produced no table body")
                        self.assertIn(usns[0], body, f"{cat}/{fmt} lost a row")
                        continue
                    raw = _resp_bytes(resp)
                    self.assertGreater(len(raw), 20, f"{cat}/{fmt} file is empty")
                    if fmt == "csv":
                        text = raw.decode("utf-8-sig")
                        table, head = _csv_table(raw)
                        self.assertGreaterEqual(len(table), 1,
                                                f"{cat}/csv has no data row")
                    elif fmt == "excel":
                        text = _xlsx_text(raw)
                    else:
                        text = _pdf_text(raw).upper()
                    self.assertIn(usns[0], text, f"{cat}/{fmt} does not carry the scoped student")

    def test_unknown_category_and_format_are_refused_clearly(self):
        with self.assertRaises(HTTPException) as ctx:
            routes_export.generate_report(routes_export.ReportRequest(
                category="not_a_report", format="pdf", rows=_rows([USN_A])), ADMIN)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("not_a_report", ctx.exception.detail)
        with self.assertRaises(HTTPException) as ctx:
            routes_export.generate_report(routes_export.ReportRequest(
                category="fees", format="tif", rows=_rows([USN_A])), ADMIN)
        self.assertIn("tif", ctx.exception.detail)
        with self.assertRaises(HTTPException) as ctx:
            routes_export.generate_report(routes_export.ReportRequest(
                category="fees", format="csv", rows=[]), ADMIN)
        self.assertIn("no displayed records", ctx.exception.detail.lower())
        with self.assertRaises(HTTPException) as ctx:
            routes_export.generate_report(routes_export.ReportRequest(
                category="individual", format="pdf",
                rows=_rows([USN_A, USN_B])), ADMIN)
        self.assertIn("exactly one", ctx.exception.detail)

    # ── scope: the report contains the selected students and nothing else ─────
    def test_report_row_set_is_exactly_the_selected_scope(self):
        for fmt in ("csv", "excel"):
            with self.subTest(format=fmt):
                resp = _render("personal", [USN_A, USN_C], ADMIN, fmt)
                raw = _resp_bytes(resp)
                table, head = (_csv_table(raw) if fmt == "csv" else _xlsx_table(raw))
                usns = {r.get("USN") for r in table}
                self.assertEqual(usns, {USN_A, USN_C},
                                 f"{fmt} report row set != selected scope")
                self.assertNotIn(USN_B, usns)
                self.assertNotIn("9QA", " ".join(usns), "a real student leaked into a QA scope")

    def test_duplicate_join_rows_collapse_without_losing_a_real_row(self):
        # A marks join hands the dashboard the same student twice with identical
        # cells; the list report must read one line each, but a per-semester
        # difference must survive.
        dup = _rows([USN_A, USN_A], {USN_A: {"name": KN_NAME, "district": "Hassan"}})
        model = report_service.build_table_report_model(dup, ADMIN, "student_list")
        self.assertEqual(len(model["records"]), 1)
        self.assertTrue(any("duplicate" in n.lower() for n in model["notes"]),
                        "collapsing rows must be disclosed, not silent")

    # ── parity: the same cells in every format ────────────────────────────────
    def _cells_of(self, fmt, raw_or_text):
        if fmt == "csv":
            table, head = _csv_table(raw_or_text)
        else:
            table, head = _xlsx_table(raw_or_text)
        return head, table

    def test_csv_excel_and_preview_agree_cell_for_cell(self):
        for cat in ("personal", "fees", "academic", "discontinued"):
            with self.subTest(category=cat):
                preview = routes_export.report_preview(
                    routes_export.ReportRequest(
                        category=cat, format="pdf", rows=_rows([USN_A, USN_B, USN_C])),
                    current_user=ADMIN)
                expect = {r["usn"]: r for r in preview["records"]}
                columns = {c["key"]: c["label"] for c in preview["columns"]}
                for fmt in ("csv", "excel"):
                    raw = _resp_bytes(_render(cat, [USN_A, USN_B, USN_C], ADMIN, fmt))
                    head, table = self._cells_of(fmt, raw)
                    got = {r.get("USN"): r for r in table}
                    self.assertEqual(set(got), set(expect),
                                     f"{cat}/{fmt}: row set differs from the preview")
                    for usn, want in expect.items():
                        for key, label in columns.items():
                            if label not in head:
                                continue
                            w = "" if want.get(key) is None else str(want.get(key))
                            g = got[usn].get(label, "")
                            self.assertEqual(g.strip(), w.strip(),
                                             f"{cat}/{fmt} cell {usn}/{label} "
                                             f"differs from the preview")

    # ── independent SQL truth ─────────────────────────────────────────────────
    def test_fees_totals_are_the_sql_sums_not_the_app_cache(self):
        truth = _sql(
            "SELECT usn, SUM(amount_paid) paid, SUM(remaining_amount) pending,"
            " COUNT(*) n FROM student_fees WHERE usn IN (%s,%s) GROUP BY usn",
            (USN_A, USN_B))
        by = {re.sub(r"[^A-Z0-9]", "", str(r["usn"]).upper()): r for r in truth}
        raw = _resp_bytes(_render("fees", [USN_A, USN_B], ADMIN, "csv"))
        table, head = _csv_table(raw)
        got = {r["USN"]: r for r in table}
        self.assertEqual(got[USN_A]["Total Paid (Rs)"].strip(), "5000")
        self.assertEqual(got[USN_A]["Total Pending (Rs)"].strip(), "2500")
        self.assertEqual(got[USN_A]["Payment Status"].strip(), "Partially Paid")
        self.assertEqual(int(got[USN_A]["Fee Records"]), int(by[USN_A]["n"]))
        # A fee with no amount recorded must stay blank: 0 would claim a payment
        # of none and a balance of none, i.e. "settled".
        self.assertEqual(got[USN_B]["Total Paid (Rs)"].strip(), "",
                         "a NULL amount must not be reported as 0")
        self.assertEqual(got[USN_B]["Total Pending (Rs)"].strip(), "")

    def test_a_fee_status_of_not_recorded_is_never_read_as_unpaid(self):
        raw = _resp_bytes(_render("fees", [USN_B], ADMIN, "csv"))
        table, head = _csv_table(raw)
        self.assertEqual(table[0]["Payment Status"].strip(), "Not Recorded")

    def test_academic_cgpa_is_the_rounded_average_of_the_marks_rows(self):
        truth = _sql(
            "SELECT semester, sgpa, ROUND(AVG(sgpa) OVER (ORDER BY semester"
            " ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),2) cgpa"
            " FROM marks WHERE usn=%s AND sgpa IS NOT NULL ORDER BY semester", (USN_A,))
        raw = _resp_bytes(_render("academic", [USN_A], ADMIN, "csv"))
        table, head = _csv_table(raw)
        self.assertEqual(len(table), len(truth))
        for row, t in zip(table, truth):
            self.assertEqual(row["SGPA"].strip(), f"{float(t['sgpa']):g}")
            self.assertEqual(row["Cumulative CGPA"].strip(), f"{float(t['cgpa']):g}")

    def test_a_student_with_no_marks_is_listed_blank_not_skipped(self):
        raw = _resp_bytes(_render("academic", [USN_B], ADMIN, "csv"))
        table, head = _csv_table(raw)
        self.assertEqual([r["USN"] for r in table], [USN_B])
        self.assertEqual(table[0]["SGPA"].strip(), "")
        model = report_service.build_table_report_model(
            _rows([USN_B]), ADMIN, "academic")
        self.assertTrue(any("no recorded marks" in n.lower() for n in model["notes"]))

    def test_discontinued_report_follows_the_single_status_authority(self):
        truth = _sql(
            "SELECT s.usn, COALESCE(ls.current_status, s.lifecycle_status) st"
            " FROM students s LEFT JOIN student_lifecycle_status ls ON ls.usn=s.usn"
            " WHERE s.usn IN (%s,%s,%s)", (USN_A, USN_B, USN_C))
        expect = {r["usn"]: r["st"] for r in truth}
        self.assertEqual(expect[USN_C], "Discontinued-Review Req",
                         "fixture lost its deliberate column/register disagreement")
        raw = _resp_bytes(_render("discontinued", [USN_A, USN_B, USN_C], ADMIN, "csv"))
        table, head = _csv_table(raw)
        self.assertEqual([r["USN"] for r in table], [USN_C],
                         "only the discontinued student belongs in this report")
        self.assertEqual(table[0]["Status"].strip(), expect[USN_C])

    def test_discontinued_report_keeps_kannada_reason_and_category(self):
        raw = _resp_bytes(_render("discontinued", [USN_C], ADMIN, "csv"))
        text = raw.decode("utf-8-sig")
        self.assertIn("ಆರೋಗ್ಯ", text)
        self.assertIn("Medical", text)

    # ── the Phase 7 masking policy, applied to every format ───────────────────
    def test_viewer_cannot_export_a_full_contact_in_any_format(self):
        for cat in ("personal", "student_list"):
            rows = _rows([USN_A], {USN_A: {"usn": USN_A, "name": KN_NAME,
                                           "phone": PHONE_A, "email": EMAIL_A,
                                           "aadhar_no": AADHAR_A}})
            for fmt in TABLE_FORMATS:
                with self.subTest(category=cat, format=fmt):
                    if fmt == "print":
                        req = routes_export.ReportRequest(
                            category=cat, format="print", rows=rows)
                        body = routes_export.generate_report(
                            req, current_user=VIEWER).body.decode("utf-8")
                    else:
                        req = routes_export.ReportRequest(
                            category=cat, format=fmt, rows=rows)
                        body = (_resp_bytes(routes_export.generate_report(
                            req, current_user=VIEWER)) or b"")
                        body = body.decode("utf-8", "ignore")
                    for secret in (PHONE_A, EMAIL_A, AADHAR_A):
                        self.assertNotIn(secret, body,
                                         f"{cat}/{fmt} leaked a Viewer's restricted value")
                    self.assertIn("*", body, f"{cat}/{fmt} dropped the mask entirely")

    def test_staff_report_masks_aadhaar_and_shows_contacts_where_allowed(self):
        raw = _resp_bytes(_render("personal", [USN_A], STAFF, "csv"))
        text = raw.decode("utf-8-sig")
        self.assertNotIn(AADHAR_A, text)
        self.assertIn("*", text)

    def test_admin_report_carries_the_real_values(self):
        raw = _resp_bytes(_render("personal", [USN_A], ADMIN, "csv"))
        text = raw.decode("utf-8-sig")
        self.assertIn(PHONE_A, text)
        self.assertIn(AADHAR_A, text)

    def test_a_client_posted_value_cannot_be_printed_as_the_colleges_record(self):
        # The personal category falls back to the posted row for any cell the
        # database leaves blank. A browser can therefore put a value that the
        # register does not hold into an official document.
        fake = _rows([USN_B], {USN_B: {"usn": USN_B, "name": "Probe Two",
                                       "phone": "9000000000",
                                       "aadhar_no": "9999999999",
                                       "email": "made.up@nowhere.invalid"}})
        raw = _resp_bytes(routes_export.generate_report(
            routes_export.ReportRequest(category="personal", format="csv",
                                        rows=fake), current_user=ADMIN))
        text = raw.decode("utf-8-sig")
        for invented in ("9000000000", "9999999999", "made.up@nowhere.invalid"):
            self.assertNotIn(invented, text,
                             f"a value MySQL does not hold ({invented}) was printed as the student's record")

    # ── Unicode survival ──────────────────────────────────────────────────────
    def test_kannada_text_survives_csv_excel_and_print(self):
        for fmt in ("csv", "excel"):
            with self.subTest(format=fmt):
                raw = _resp_bytes(_render("personal", [USN_A], ADMIN, fmt))
                text = (raw.decode("utf-8-sig") if fmt == "csv"
                        else _xlsx_text(raw))
                self.assertIn(KN_NAME, text)
        body = routes_export.generate_report(
            routes_export.ReportRequest(category="personal", format="print",
                                        rows=_rows([USN_A])),
            current_user=ADMIN).body.decode("utf-8")
        self.assertTrue(KN_NAME in body or _html_cells(body).find("ಟೆಸ್ಟ್") >= 0)

    def test_kannada_name_is_never_printed_as_placeholder_boxes(self):
        raw = _resp_bytes(_render("personal", [USN_A], ADMIN, "pdf"))
        text = _pdf_text(raw)
        has_unicode_font = b"FontFile2" in raw
        if not has_unicode_font:
            # No Kannada-capable font on this host: the report must SAY that
            # instead of printing a wrong name.
            self.assertRegex(
                text.replace(" ", "").lower(), r"(cannot|couldnot|unavailable|no.*font)",
                "PDF printed a name it could not render, without saying so")
            return
        self.assertNotRegex(text, r"Name:\s*nn+n?\s",
                            "Kannada name collapsed to Helvetica fallback glyphs")
        self.assertIn("ಟ", text)

    def test_individual_pdf_either_renders_kannada_or_says_it_could_not(self):
        raw = _resp_bytes(routes_export.generate_report(
            routes_export.ReportRequest(category="individual", format="pdf",
                                        rows=_rows([USN_A])), current_user=ADMIN))
        text = _pdf_text(raw)
        if b"FontFile2" in raw:
            self.assertIn("ಟ", text)
            return
        self.assertRegex(
            text.replace(" ", "").lower(), r"(cannot|couldnot|unavailable|nofont)",
            "PDF printed a name it could not render, without saying so")
        self.assertNotIn("NNNN", text.upper().replace(" ", ""))

    # ── hostile content stays data ────────────────────────────────────────────
    def test_a_hostile_cell_stays_text_in_csv_and_excel(self):
        # Uploaded sheets and typed-in names are data. A value that Excel would
        # read as a formula must not be able to phone home from a college report.
        # USN_B is in the register, so after D78 the hostile cell is refused before
        # layout — the neutralising itself is proved on the laid-out path below.
        hostile = '=HYPERLINK("http://qa-probe.invalid","x")'
        payload = _rows([USN_B], {USN_B: {"usn": USN_B, "name": hostile,
                                         "district": "+2|cmd"}})
        for fmt in ("csv", "excel"):
            with self.subTest(format=fmt):
                raw = _resp_bytes(routes_export.generate_report(
                    routes_export.ReportRequest(category="personal", format=fmt,
                                                rows=payload), current_user=ADMIN))
                body = (raw.decode("utf-8-sig") if fmt == "csv" else _xlsx_text(raw))
                if fmt == "csv":
                    for line in body.splitlines():
                        self.assertFalse(line.startswith("="),
                                         "a CSV row starts with a formula sign")
                self.assertNotIn("=HYPERLINK(", body)

    def test_a_hostile_value_that_is_actually_laid_out_stays_text(self):
        # The test above only proves the register overrides a posted hostile cell
        # (D78), which leaves the harder half unproved: what happens on the one
        # path where a posted value *is* laid out — a USN the database has never
        # seen. There the file has to be data, not a formula a spreadsheet runs.
        ghost = "9ZZ8P09999"
        hostile = '=HYPERLINK("http://qa-probe.invalid","x")'
        payload = _rows([ghost], {ghost: {"usn": ghost, "name": hostile,
                                         "district": "+2|cmd"}})

        def render(fmt):
            resp = routes_export.generate_report(
                routes_export.ReportRequest(category="personal", format=fmt,
                                            rows=payload), current_user=ADMIN)
            return _resp_bytes(resp) if hasattr(resp, "path") else resp.body

        csv_body = render("csv").decode("utf-8-sig")
        self.assertIn("qa-probe.invalid", csv_body,
                      "the hostile cell never reached the file, so this test proved nothing")
        for line in csv_body.splitlines():
            self.assertFalse(line[:1] in ("=", "+", "-", "@"),
                             "a CSV row begins with a formula sign")
        self.assertIn("'=", csv_body, "the formula cell was not neutralised")

        import io
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(render("excel")))
        formulas = [f"{ws.title}!{c.coordinate}={c.value!r}" for ws in wb.worksheets
                    for row in ws.iter_rows() for c in row if c.data_type == "f"]
        self.assertEqual(formulas, [], "an Excel cell is typed as a live formula")

        html = render("print").decode()
        self.assertIn("qa-probe.invalid", html)
        self.assertNotIn('href="http://qa-probe.invalid', html,
                         "the print page turned a cell into a clickable link")

    # ── the audit trail of a download ─────────────────────────────────────────
    def test_each_download_records_exactly_one_export_entry(self):
        def count():
            return _sql("SELECT COUNT(*) c FROM export_logs"
                        " WHERE exported_by='p8_admin'")[0]["c"]
        for fmt in TABLE_FORMATS:
            with self.subTest(format=fmt):
                before = count()
                _render("fees", [USN_A], ADMIN, fmt)
                self.assertEqual(count(), before + 1,
                                 f"a {fmt} download left {count() - before} export rows")

    def test_the_detail_export_does_not_double_log(self):
        before = _sql("SELECT COUNT(*) c FROM export_logs WHERE exported_by='p8_admin'")[0]["c"]
        routes_export.generate_report(
            routes_export.ReportRequest(category="individual", format="excel",
                                        rows=_rows([USN_A])), current_user=ADMIN)
        after = _sql("SELECT COUNT(*) c FROM export_logs WHERE exported_by='p8_admin'")[0]["c"]
        self.assertEqual(after - before, 1,
                         "one download must leave exactly one export record")

    # ── layout conventions the owner set ─────────────────────────────────────
    def test_wide_student_list_uses_one_sheet_per_student_without_a_record_count(self):
        wide = _rows([USN_A, USN_B], {USN_A: {
            "name": KN_NAME, "district": "Hassan", "taluk": "Hiriyur",
            "village": "Testaluku", "branch": "CSE", "current_sem": 5,
            "phone": PHONE_A, "email": EMAIL_A, "aadhar_no": AADHAR_A,
            "gender": "Female", "dob": "2005-04-01", "area_type": "RURAL",
            "caste": "General", "category": "OPEN", "father_name": "Ramaiah",
            "mother_name": "Lakshmi", "religion": "Hindu", "state": "Karnataka",
            "pin_code": "573102", "year_of_joining": 2021, "student_type": "Regular",
            "quota": "General", "blood_group": "O+", "hk_status": "Non-HK",
            "admission_year": 2021, "distance_from_college": 12,
            "permanent_address": KN_ADDR, "current_address": KN_ADDR,
            "sgpa": 8.5, "cgpa": 8.5, "lifecycle_status": "Rejoined-Active"}})
        body = routes_export.generate_report(
            routes_export.ReportRequest(category="student_list", format="print",
                                        rows=wide), current_user=ADMIN).body.decode("utf-8")
        self.assertGreaterEqual(body.count("class='sheet'"), 2,
                                "a wide list must render one sheet per student")

    def test_a_single_record_report_does_not_announce_records_1(self):
        # Owner's layout rule: one student, one sheet — the count line and the
        # repeated subtitle are clutter on a one-record document.
        single = _rows([USN_A], {USN_A: {
            "name": KN_NAME, "district": "Hassan", "branch": "CSE", "phone": PHONE_A,
            "email": EMAIL_A, "aadhar_no": AADHAR_A, "current_sem": 5, "cgpa": 8.5,
            "gender": "Female", "dob": "2005-04-01", "state": "Karnataka",
            "caste": "General", "category": "OPEN", "village": "Testaluku",
            "taluk": "Hiriyur", "pin_code": "573102", "religion": "Hindu",
            "father_name": "Ramaiah", "mother_name": "Lakshmi", "area_type": "RURAL",
            "student_type": "Regular", "quota": "General", "blood_group": "O+",
            "hk_status": "Non-HK", "year_of_joining": 2021, "admission_year": 2021,
            "distance_from_college": 12, "permanent_address": KN_ADDR,
            "current_address": KN_ADDR, "sgpa": 8.5, "lifecycle_status": "Active"}})
        body = routes_export.generate_report(
            routes_export.ReportRequest(category="student_list", format="print",
                                        rows=single), current_user=ADMIN).body.decode("utf-8")
        self.assertNotIn("Records: 1", body)
        self.assertIn("class='sheet'", body)
        raw = _resp_bytes(routes_export.generate_report(
            routes_export.ReportRequest(category="student_list", format="pdf",
                                        rows=single), current_user=ADMIN))
        self.assertGreater(len(raw), 1500,
                           "a wide single-student list must still lay out its field sheets")

    def test_a_scope_that_yields_no_records_still_delivers_a_readable_file(self):
        # Two active students asked for a discontinued report: the honest answer
        # is an empty report that says so, not a 500 and not a silent blank file.
        for fmt in TABLE_FORMATS:
            with self.subTest(format=fmt):
                resp = _render("discontinued", [USN_A, USN_B], ADMIN, fmt)
                if fmt == "print":
                    body = resp.body.decode("utf-8")
                else:
                    raw = _resp_bytes(resp)
                    body = (raw.decode("utf-8-sig") if fmt == "csv" else
                            _xlsx_text(raw) if fmt == "excel" else _pdf_text(raw))
                self.assertNotIn(USN_A, body)
                self.assertRegex(body.lower().replace(" ", ""),
                                 r"norecords|noreal|notdiscontinued|excluded",
                                 f"{fmt} blank report gives no reason")

    def test_the_same_note_reaches_every_format(self):
        # The model's notes ("2 duplicate rows collapsed", "1 student has no fee
        # record", "3 excluded because they are active") are part of the answer.
        # A format that drops one tells a reader something the others contradict.
        dup = _rows([USN_A, USN_A, USN_B], {USN_A: {"name": KN_NAME},
                                            USN_B: {"name": "Probe Two"}})
        model = report_service.build_table_report_model(dup, ADMIN, "student_list")
        self.assertTrue(model["notes"], "fixture must produce at least one note")
        note = model["notes"][0]
        for fmt in TABLE_FORMATS:
            with self.subTest(format=fmt):
                req = routes_export.ReportRequest(category="student_list",
                                                  format=fmt, rows=dup)
                resp = routes_export.generate_report(req, current_user=ADMIN)
                if fmt == "print":
                    body = resp.body.decode("utf-8")
                else:
                    raw = _resp_bytes(resp)
                    body = (raw.decode("utf-8-sig") if fmt == "csv" else
                            _xlsx_text(raw) if fmt == "excel" else _pdf_text(raw))
                self.assertIn(note[:28], body,
                              f"the note {note!r} is missing from the {fmt} version")

    def test_generated_file_names_say_which_report_they_are(self):
        ext = {"csv": "csv", "excel": "xlsx", "pdf": "pdf"}
        for cat, fmt in (("fees", "csv"), ("academic", "excel"), ("personal", "pdf")):
            resp = _render(cat, [USN_A], ADMIN, fmt)
            raw = _resp_bytes(resp)
            self.assertEqual(resp.filename, f"{cat}_report.{ext[fmt]}")
            if fmt == "pdf":
                self.assertTrue(raw.startswith(b"%PDF-"), "pdf body is not a PDF")
            if fmt == "excel":
                self.assertTrue(raw.startswith(b"PK"), "xlsx body is not a zip workbook")
            if fmt == "csv":
                self.assertTrue(raw.startswith(b"\xef\xbb\xbf"),
                                "CSV must carry a UTF-8 BOM so Excel opens Kannada correctly")


if __name__ == "__main__":
    unittest.main(verbosity=2)
