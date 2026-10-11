"""
routes_export.py — Consistent, current-DB export: PDF / Excel / CSV / JSON.

All formats are built from ONE shared model, so CSV, Excel, PDF and print
always show identical fields. Values are re-read from the current authorized
MySQL records at generation time, never from a stale frontend snapshot.

Two families:
  * /export/report*  — category-scoped reports for the dashboard "Generate
    Report" window (student list / academic / personal / fees / discontinued /
    individual). A list report contains ONLY the displayed records and the
    category's columns — never unrelated sections.
  * /export/pdf|excel|csv|json|print (legacy) — full detail model (Personal,
    Academic, Fees, Backlogs, Lifecycle) kept for existing integrations.

Role-based sensitive-data masking applies to every format.
"""

import os, tempfile, re
from datetime import datetime
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable,
    Image as RLImage, KeepTogether,
)
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfgen import canvas as rl_canvas
from auth import get_current_user
import report_service

router = APIRouter(prefix="/api/export", tags=["Export"])

UNIVERSITY = report_service.INSTITUTION["university"]
COLLEGE = report_service.INSTITUTION["college"]
DEPARTMENT = report_service.INSTITUTION["department"]
LOGO_PATH = os.path.join(
    os.path.dirname(__file__), "..", "frontend", "public", "college-logo.png"
)

_DARK = "#1e3a5f"
_LIGHT = "#f0f4f8"

# ── Spreadsheet formula-injection hardening (OWASP CSV injection) ────────────
# A cell whose text begins with = + - @ or a tab/CR is executed as a formula by
# Excel/Sheets on open. Student-supplied fields (name, address, discontinuation
# reason, uploaded dynamic headings) are free text, so an export could carry a
# payload like "=HYPERLINK(...)". These helpers neutralise it in every format.
_UNSAFE_CELL = re.compile(r"^[=+\-@\t\r]")


def _csv_cell(value):
    """CSV: prefix a leading apostrophe so the value imports as literal text.
    Excel also trims a leading tab/CR before testing for a formula, so those
    are removed first."""
    if isinstance(value, str) and value and value[0] in "\t\r":
        value = value.lstrip("\t\r")
    if isinstance(value, str) and _UNSAFE_CELL.match(value):
        return "'" + value
    return value


def _safe_writer(writer):
    """Wrap a csv.writer so every writerow() value is formula-neutralised."""
    class _Safe:
        def writerow(self, row):
            writer.writerow([_csv_cell(v) for v in row])

        def writerows(self, rows):
            for r in rows:
                self.writerow(r)

        def __getattr__(self, name):
            return getattr(writer, name)
    return _Safe()


def _harden_workbook(wb):
    """Excel: our exports never contain real formulas, so any cell openpyxl
    classified as a formula is re-typed to a plain string. Display is unchanged
    (no visible apostrophe) but the value can no longer execute."""
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.data_type == "f":
                    cell.data_type = "s"

# Friendly labels for the displayed result table columns.
_COLUMN_LABELS = {
    "usn": "USN", "name": "Name", "current_sem": "Semester", "semester": "Semester",
    "sgpa": "SGPA", "cgpa": "CGPA", "area_type": "Rural/Urban", "district": "District",
    "village": "Village", "taluk": "Taluk", "blood_group": "Blood Group",
    "phone": "Phone", "email": "Email", "aadhar_no": "Aadhaar No", "dob": "Date of Birth",
    "gender": "Gender", "branch": "Branch", "status": "Status",
    "father_name": "Father's Name", "mother_name": "Mother's Name",
    "missing_fields": "Missing Fields", "missing_count": "Missing Count",
    "student_type": "Student Type", "admission_year": "Admission Year",
    "distance_from_college": "Distance from College", "hk_status": "HK/Non-HK",
}


def _label(key: str) -> str:
    return _COLUMN_LABELS.get(key, key.replace("_", " ").title())


def _fee_display(fee: dict) -> str:
    """Show the normalized label plus the original source value for auditability."""
    label = fee["status_label"]
    raw = fee.get("status_raw", "")
    if raw and raw.strip().lower() != label.lower():
        return f"{label} (source: {raw})"
    return label


def _has_val(v) -> bool:
    return v not in (None, "", "null")


def _fee_block(st: dict) -> tuple[list[str], list[list[str]]]:
    """Fee table shared by every format: structured rows are authoritative and
    the workbook (dynamic) fields are only used when there are no structured
    records — so fees never appear twice. Columns with no values are dropped."""
    fees = st.get("fees") or []
    if fees:
        has_paid = any(_has_val(f.get("amount_paid")) for f in fees)
        has_remaining = any(_has_val(f.get("remaining_amount")) for f in fees)
        head = ["Fee Type", "Year", "Status"]
        idx = [0, 1, 2]
        if has_paid:
            head.append("Amount Paid"); idx.append(3)
        if has_remaining:
            head.append("Remaining"); idx.append(4)
        rows = []
        for f in fees:
            cells = [
                _as_str_export(f.get("fee_type")),
                "" if f.get("year") is None else str(f.get("year")),
                _fee_display(f),
                "" if not _has_val(f.get("amount_paid")) else str(f.get("amount_paid")),
                "" if not _has_val(f.get("remaining_amount")) else str(f.get("remaining_amount")),
            ]
            rows.append([cells[i] for i in idx])
        return head, rows
    dyn = [d for d in (st.get("dynamic_fee_fields") or []) if _has_val(d.get("value"))]
    if dyn:
        return ["Fee Field", "Value"], [[d["label"], str(d["value"])] for d in dyn]
    return [], []


def _as_str_export(value) -> str:
    return "" if value is None else str(value)


def _log_export(fmt: str, record_count: int, username: str):
    from database import db_conn, write_audit_log
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO export_logs (format, record_count, exported_by) VALUES (%s, %s, %s)",
                (fmt, record_count, username),
            )
            conn.commit()
            cur.close()
        write_audit_log(
            action=f"EXPORT_{fmt.upper()}", username=username,
            summary=f"Exported {record_count} record(s) as {fmt.upper()}", success=True,
        )
    except Exception as e:
        print(f"[ERR] Failed to log export: {e}")


# ── Shared section builders (used identically by every format) ────────────────

def _fee_summary(student: dict) -> str:
    counts = {"paid": 0, "unpaid": 0, "partial": 0, "na": 0, "unknown": 0}
    for fee in student["fees"]:
        counts[fee["status"]] = counts.get(fee["status"], 0) + 1
    parts = []
    if counts["unpaid"]:
        parts.append(f"{counts['unpaid']} unpaid")
    if counts["partial"]:
        parts.append(f"{counts['partial']} partial")
    if counts["paid"]:
        parts.append(f"{counts['paid']} paid")
    return ", ".join(parts) if parts else "No fee records"


def _lifecycle_fields(st: dict) -> list[tuple[str, str]]:
    """Ordered (label, value) pairs describing a student's current lifecycle
    status, for the profile/detail section of every export format. Unavailable
    fields are omitted entirely (never rendered as a blank or a '—' placeholder),
    so a section only shows the data the student actually has."""
    lc = st.get("lifecycle") or {}
    pairs = [
        ("Lifecycle Status", lc.get("current_status") or "Active"),
        ("Status Effective Date", lc.get("effective_date") or ""),
        ("Last Enrolled Semester", "" if lc.get("last_enrolled_semester") in (None, "")
         else str(lc.get("last_enrolled_semester"))),
        ("Last Enrolled Academic Year", lc.get("last_enrolled_academic_year") or ""),
        ("Applicable Scheme", lc.get("scheme") or ""),
        ("Reason", lc.get("reason") or ""),
        ("Reason Category", lc.get("reason_category") or ""),
        ("Document Reference", lc.get("document_ref") or ""),
        ("Last Updated By", lc.get("updated_by") or ""),
    ]
    return [(lbl, val) for lbl, val in pairs if val not in ("", None, "—")]


def _lifecycle_history_rows(st: dict) -> list[dict]:
    return (st.get("lifecycle") or {}).get("history") or []


def _pdf_styles():
    return {
        "hdr": ParagraphStyle("H", fontName="Helvetica-Bold", fontSize=11, alignment=TA_CENTER, leading=16),
        "sub": ParagraphStyle("S", fontName="Helvetica-Bold", fontSize=9, alignment=TA_CENTER, leading=13, textColor=colors.HexColor(_DARK)),
        "dept": ParagraphStyle("D", fontName="Helvetica-Bold", fontSize=8, alignment=TA_CENTER, leading=12, textColor=colors.HexColor(_DARK)),
        "norm": ParagraphStyle("N", fontName="Helvetica", fontSize=8, alignment=TA_LEFT, leading=11),
        "sign": ParagraphStyle("SG", fontName="Helvetica", fontSize=8, alignment=TA_LEFT, leading=12),
        "tiny": ParagraphStyle("T", fontName="Helvetica", fontSize=7, alignment=TA_CENTER, leading=10, textColor=colors.grey),
        "lbl": ParagraphStyle("LB", fontName="Helvetica-Bold", fontSize=8, alignment=TA_LEFT, leading=12),
        "val": ParagraphStyle("VL", fontName="Helvetica", fontSize=8, alignment=TA_LEFT, leading=12),
        "sec": ParagraphStyle("SC", fontName="Helvetica-Bold", fontSize=9, alignment=TA_LEFT, leading=13, textColor=colors.HexColor(_DARK)),
        "title": ParagraphStyle("TT", fontName="Helvetica-Bold", fontSize=10, alignment=TA_CENTER, leading=14, textColor=colors.HexColor(_DARK)),
    }


def _pdf_table(header, rows, widths=None, pad=6):
    data = [header] + rows
    t = Table(data, repeatRows=1, colWidths=widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_DARK)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(_LIGHT)]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), pad),
        ("RIGHTPADDING", (0, 0), (-1, -1), pad),
    ]))
    return t


def _build_branded_pdf(path: str, model: dict):
    s = _pdf_styles()
    gen = model["generated_by"]
    students = model["students"]
    single = model["is_single_student"]
    story = []

    logo_cell = Paragraph("", s["norm"])
    if os.path.exists(LOGO_PATH):
        try:
            logo_cell = RLImage(LOGO_PATH, width=2.2 * cm, height=2.2 * cm)
        except Exception:
            pass
    hdr_tbl = Table([[logo_cell, [
        Paragraph(model["institution"]["university"], s["hdr"]), Spacer(1, 2),
        Paragraph(model["institution"]["college"], s["sub"]), Spacer(1, 2),
        Paragraph(model["institution"]["department"], s["dept"]),
    ]]], colWidths=[2.8 * cm, None])
    hdr_tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.append(hdr_tbl)
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor(_DARK), spaceAfter=6))
    story.append(Paragraph("Student Report", s["title"]))
    story.append(Spacer(1, 8))

    for st in students:
        if not single:
            story.append(Paragraph(f"{st['name']} ({st['usn']})", s["sec"]))
            story.append(Spacer(1, 3))

        # Personal information block (2-column)
        info_rows = []
        for key, label in report_service.PERSONAL_FIELDS:
            v = st["personal"].get(key)
            if v not in (None, "", "null"):
                info_rows.append([Paragraph(f"<b>{label}:</b>", s["lbl"]), Paragraph(str(v), s["val"])])
        if info_rows:
            half = (len(info_rows) + 1) // 2
            left, right = info_rows[:half], info_rows[half:]
            while len(right) < len(left):
                right.append([Paragraph("", s["lbl"]), Paragraph("", s["val"])])
            merged = [l + r for l, r in zip(left, right)]
            tbl = Table(merged, colWidths=[3.2 * cm, 5.5 * cm, 3.2 * cm, 5.5 * cm])
            tbl.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2), ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8faff")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d8ef")),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 6))

        # ── Sections render only when the student actually has that data. An
        # unavailable section (and any unavailable column within a section) is
        # omitted entirely rather than shown as a blank row or a "—" placeholder,
        # and each header+table is kept together so a section never spills onto —
        # or leaves behind — a near-empty page.

        # Fees Details — shared builder dedupes structured vs workbook fields and
        # drops columns that carry no values.
        fee_head, fee_rows = _fee_block(st)
        if fee_head:
            fee_widths = ([4 * cm, 2 * cm, 5 * cm, 3 * cm, 3 * cm] if len(fee_head) >= 3
                          else None)
            if fee_head[:2] == ["Fee Field", "Value"]:
                fee_widths = [9 * cm, 8 * cm]
            widths = fee_widths[:len(fee_head)] if fee_widths else None
            header_para = Paragraph("FEES DETAILS", s["sec"])
            table = _pdf_table(fee_head, fee_rows, widths=widths)
            # Short tables stay together; a many-row fee table is allowed to
            # flow across pages (its column header repeats) instead of being
            # pushed whole onto a fresh page and orphaning the next section.
            if len(fee_rows) <= 6:
                story.append(KeepTogether([header_para, table]))
            else:
                story.append(header_para)
                story.append(table)
            story.append(Spacer(1, 6))

        # Backlogs / Arrears — only active (uncleared) rows remain in the model.
        if st["backlogs"]:
            bl_rows = [[
                b["subject"],
                "" if b["semester"] is None else str(b["semester"]),
                "" if b.get("year") in (None, "") else str(b["year"]),
            ] for b in st["backlogs"]]
            story.append(KeepTogether([
                Paragraph("BACKLOGS / ARREARS", s["sec"]),
                _pdf_table(["Subject", "Semester", "Year"], bl_rows,
                           widths=[9 * cm, 4 * cm, 4 * cm]),
            ]))
            story.append(Spacer(1, 6))

        # Academic performance — drop SGPA/CGPA columns that hold no values.
        if st["academic"]:
            has_sgpa = any(a["sgpa"] is not None for a in st["academic"])
            has_cgpa = any(a["cgpa"] is not None for a in st["academic"])
            acad_head, acad_rows = ["Semester"], []
            if has_sgpa:
                acad_head.append("SGPA")
            if has_cgpa:
                acad_head.append("Cumulative CGPA")
            for a in st["academic"]:
                row = [f"Semester {a['semester']}"]
                if has_sgpa:
                    row.append("" if a["sgpa"] is None else str(round(a["sgpa"], 2)))
                if has_cgpa:
                    row.append("" if a["cgpa"] is None else str(round(a["cgpa"], 2)))
                acad_rows.append(row)
            story.append(KeepTogether([
                Paragraph("ACADEMIC PERFORMANCE", s["sec"]),
                _pdf_table(acad_head, acad_rows,
                           widths=[5 * cm, 4 * cm, 5 * cm][:len(acad_head)]),
            ]))
            story.append(Spacer(1, 6))

        # Lifecycle status + audited history
        lc_pairs = _lifecycle_fields(st)
        lc_rows = [[Paragraph(f"<b>{lbl}:</b>", s["lbl"]), Paragraph(str(val), s["val"])]
                   for lbl, val in lc_pairs]
        hist = _lifecycle_history_rows(st)
        if lc_rows or hist:
            block = [Paragraph("LIFECYCLE STATUS", s["sec"])]
            if lc_rows:
                half = (len(lc_rows) + 1) // 2
                left, right = lc_rows[:half], lc_rows[half:]
                while len(right) < len(left):
                    right.append([Paragraph("", s["lbl"]), Paragraph("", s["val"])])
                merged = [l + r for l, r in zip(left, right)]
                lct = Table(merged, colWidths=[3.6 * cm, 4.4 * cm, 3.6 * cm, 4.4 * cm])
                lct.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 2), ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8faff")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d8ef")),
                ]))
                block.append(lct)
            if hist:
                block.append(Spacer(1, 3))
                block.append(Paragraph("Status change history:", s["norm"]))
                h_rows = [[
                    str(h.get("created_at") or ""), h.get("event_type", "") or "",
                    h.get("from_status", "") or "", h.get("to_status", "") or "",
                    h.get("actor_username", "") or "",
                ] for h in hist]
                block.append(_pdf_table(["When", "Event", "From", "To", "By"], h_rows,
                                        widths=[3.2 * cm, 3.2 * cm, 3.2 * cm, 3.2 * cm, 2.4 * cm]))
            story.append(KeepTogether(block))
        story.append(Spacer(1, 10))
        if not single:
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc"), spaceAfter=8))

    # Displayed result table (kept for list exports)
    if not single and model["table_rows"]:
        story.append(Paragraph("QUERY RESULTS", s["sec"]))
        headers = model["table_headers"]
        rows = [[_cell_text(r.get(h)) for h in headers] for r in model["table_rows"]]
        story.append(_pdf_table([_label(h) for h in headers], rows))
        story.append(Spacer(1, 10))

    sig = Table([[
        Paragraph(f"<b>Prepared By:</b><br/><br/>Signature: {gen['username']}<br/><br/><b>({gen['role']})</b>", s["sign"]),
        Paragraph(f"<b>Generated on:</b><br/>{gen['timestamp']}", s["sign"]),
        Paragraph("", s["sign"]),
    ]], colWidths=[7 * cm, 7 * cm, 4 * cm])
    sig.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceBefore=6, spaceAfter=8))
    story.append(sig)
    story.append(Paragraph(f"Report generated by AI Student Management System · {COLLEGE}", s["tiny"]))

    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    doc.build(story)


def _cell_text(value) -> str:
    if value is None or value == "":
        return ""
    return str(value)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/pdf")
def export_pdf(data: list[dict], current_user: dict = Depends(get_current_user)):
    if not data:
        raise HTTPException(400, "No data to export.")
    model = report_service.build_report_model(data, current_user)
    _log_export("pdf", len(data), current_user["username"])
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    _build_branded_pdf(path, model)
    return FileResponse(path, filename="student_report.pdf", media_type="application/pdf")


@router.post("/excel")
def export_excel(data: list[dict], current_user: dict = Depends(get_current_user)):
    if not data:
        raise HTTPException(400, "No data to export.")
    model = report_service.build_report_model(data, current_user)
    _log_export("excel", len(data), current_user["username"])
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)

    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Report"

    def header(row_text):
        ws.append([row_text])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True, color="FFFFFF")
        ws.cell(row=ws.max_row, column=1).fill = PatternFill("solid", fgColor="1e3a5f")

    for line in (model["institution"]["university"], model["institution"]["college"],
                 model["institution"]["department"]):
        ws.append([line])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True, size=11)
    ws.append([])

    for st in model["students"]:
        header(f"STUDENT: {st['name']} ({st['usn']})" if not model["is_single_student"] else "PERSONAL DETAILS")
        for key, label in report_service.PERSONAL_FIELDS:
            v = st["personal"].get(key)
            if v not in (None, ""):
                ws.append([label, str(v)])
        ws.append([])

        fee_head, fee_rows = _fee_block(st)
        if fee_head:
            header("FEES DETAILS")
            ws.append(fee_head)
            for row in fee_rows:
                ws.append(row)
            ws.append([])

        if st["backlogs"]:
            header("BACKLOGS / ARREARS")
            ws.append(["Subject", "Semester", "Year"])
            for b in st["backlogs"]:
                ws.append([b["subject"], "" if b["semester"] is None else str(b["semester"]),
                           "" if b.get("year") in (None, "") else str(b["year"])])
            ws.append([])

        if st["academic"]:
            has_sgpa = any(a["sgpa"] is not None for a in st["academic"])
            has_cgpa = any(a["cgpa"] is not None for a in st["academic"])
            a_head = ["Semester"] + (["SGPA"] if has_sgpa else []) + (["Cumulative CGPA"] if has_cgpa else [])
            header("ACADEMIC PERFORMANCE")
            ws.append(a_head)
            for a in st["academic"]:
                row = [f"Semester {a['semester']}"]
                if has_sgpa:
                    row.append("" if a["sgpa"] is None else round(a["sgpa"], 2))
                if has_cgpa:
                    row.append("" if a["cgpa"] is None else round(a["cgpa"], 2))
                ws.append(row)
            ws.append([])

        lc_rows = _lifecycle_fields(st)
        hist = _lifecycle_history_rows(st)
        if lc_rows or hist:
            header("LIFECYCLE STATUS")
            for lbl, val in lc_rows:
                ws.append([lbl, val])
            if hist:
                ws.append(["Status change history:"])
                ws.append(["When", "Event", "From", "To", "By", "Remarks"])
                for h in hist:
                    ws.append([str(h.get("created_at") or ""), h.get("event_type", ""),
                               h.get("from_status", "") or "", h.get("to_status", ""),
                               h.get("actor_username", ""), h.get("remarks", "")])
        ws.append([])

    if not model["is_single_student"] and model["table_rows"]:
        header("QUERY RESULTS")
        headers = model["table_headers"]
        ws.append([_label(h) for h in headers])
        for row in model["table_rows"]:
            ws.append([row.get(h, "") for h in headers])
        ws.append([])

    ws.append(["Prepared By:", model["generated_by"]["username"], f"({model['generated_by']['role']})"])
    ws.append(["Generated on:", model["generated_by"]["timestamp"]])

    for col in ws.columns:
        letter = col[0].column_letter
        width = max((len(str(c.value)) for c in col if c.value is not None), default=10)
        ws.column_dimensions[letter].width = min(width + 2, 60)

    _harden_workbook(wb)
    wb.save(path)
    return FileResponse(path, filename="student_report.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.post("/csv")
def export_csv(data: list[dict], current_user: dict = Depends(get_current_user)):
    if not data:
        raise HTTPException(400, "No data to export.")
    model = report_service.build_report_model(data, current_user)
    _log_export("csv", len(data), current_user["username"])
    fd, path = tempfile.mkstemp(suffix=".csv")
    import csv
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
        w = _safe_writer(csv.writer(fh))

        w.writerow(["INSTITUTION"])
        for k, v in model["institution"].items():
            w.writerow([k.title(), v])
        w.writerow([])

        for st in model["students"]:
            w.writerow(["STUDENT", st["usn"], st["name"]])
            w.writerow(["PERSONAL DETAILS"])
            for key, label in report_service.PERSONAL_FIELDS:
                val = st["personal"].get(key)
                if val not in (None, ""):
                    w.writerow([label, val])
            w.writerow([])
            fee_head, fee_rows = _fee_block(st)
            if fee_head:
                w.writerow(["FEES DETAILS"])
                w.writerow(fee_head)
                for row in fee_rows:
                    w.writerow(row)
                w.writerow([])
            if st["backlogs"]:
                w.writerow(["BACKLOGS / ARREARS"])
                w.writerow(["Subject", "Semester", "Year"])
                for b in st["backlogs"]:
                    w.writerow([b["subject"], "" if b["semester"] is None else b["semester"],
                                "" if b.get("year") in (None, "") else b["year"]])
                w.writerow([])
            if st["academic"]:
                has_sgpa = any(a["sgpa"] is not None for a in st["academic"])
                has_cgpa = any(a["cgpa"] is not None for a in st["academic"])
                a_head = ["Semester"] + (["SGPA"] if has_sgpa else []) + (["Cumulative CGPA"] if has_cgpa else [])
                w.writerow(["ACADEMIC PERFORMANCE"])
                w.writerow(a_head)
                for a in st["academic"]:
                    row = [f"Semester {a['semester']}"]
                    if has_sgpa:
                        row.append("" if a["sgpa"] is None else round(a["sgpa"], 2))
                    if has_cgpa:
                        row.append("" if a["cgpa"] is None else round(a["cgpa"], 2))
                    w.writerow(row)
                w.writerow([])
            lc_fields = _lifecycle_fields(st)
            hist = _lifecycle_history_rows(st)
            if lc_fields or hist:
                w.writerow(["LIFECYCLE STATUS"])
                for lbl, val in lc_fields:
                    w.writerow([lbl, val])
                if hist:
                    w.writerow(["Status change history:"])
                    w.writerow(["When", "Event", "From", "To", "By", "Remarks"])
                    for h in hist:
                        w.writerow([str(h.get("created_at") or ""), h.get("event_type", ""),
                                    h.get("from_status", "") or "", h.get("to_status", ""),
                                    h.get("actor_username", ""), h.get("remarks", "")])
            w.writerow([])

        if not model["is_single_student"] and model["table_rows"]:
            w.writerow(["QUERY RESULTS"])
            headers = model["table_headers"]
            w.writerow([_label(h) for h in headers])
            for row in model["table_rows"]:
                w.writerow([row.get(h, "") for h in headers])
            w.writerow([])

        w.writerow(["SIGNATURE"])
        w.writerow(["Prepared By", model["generated_by"]["username"]])
        w.writerow(["Role", model["generated_by"]["role"]])
        w.writerow(["Generated on", model["generated_by"]["timestamp"]])

    return FileResponse(path, filename="student_report.csv", media_type="text/csv")


@router.post("/json")
def export_json(data: list[dict], current_user: dict = Depends(get_current_user)):
    """Return the shared report model (personal + academic + fees + backlogs)."""
    if not data:
        raise HTTPException(400, "No data to export.")
    _log_export("json", len(data), current_user["username"])
    model = report_service.build_report_model(data, current_user)
    fd, path = tempfile.mkstemp(suffix=".json")
    import json
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False, default=str, indent=2)
    return FileResponse(path, filename="student_report.json", media_type="application/json")


def _esc(value) -> str:
    import html
    return html.escape("" if value is None else str(value))


def _build_html_report(model: dict) -> str:
    gen = model["generated_by"]
    parts = ["""<!doctype html><html><head><meta charset="utf-8"><title>Student Report</title>
<style>
body{font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#111;margin:1.5cm}
h1,h2{font-size:14px;color:#1e3a5f;text-align:center;margin:2px 0}
h3{font-size:12px;color:#1e3a5f;border-bottom:1px solid #ccc;margin:14px 0 6px}
table{border-collapse:collapse;width:100%;margin-bottom:8px}
th,td{border:1px solid #bbb;padding:3px 6px;text-align:left}
th{background:#1e3a5f;color:#fff}
tr:nth-child(even) td{background:#f4f7fb}
.info{display:grid;grid-template-columns:1fr 1fr;gap:2px 24px}
.sig{margin-top:24px;display:flex;justify-content:space-between}
@media print{.print-section{page-break-inside:avoid}button{display:none}}
</style></head><body>"""]
    inst = model["institution"]
    parts.append(f"<h1>{_esc(inst['university'])}</h1>")
    parts.append(f"<h2>{_esc(inst['college'])}</h2>")
    parts.append(f"<h2>{_esc(inst['department'])}</h2><hr>")
    parts.append("<h3>Student Report</h3>")

    for st in model["students"]:
        parts.append("<div class='print-section'>")
        parts.append(f"<h2>{_esc(st['name'])} ({_esc(st['usn'])})</h2>")
        personal = "".join(
            f"<div><b>{_esc(label)}:</b> {_esc(st['personal'].get(key))}</div>"
            for key, label in report_service.PERSONAL_FIELDS
            if st["personal"].get(key) not in (None, "", "null")
        )
        parts.append(f"<h3>Personal Information</h3><div class='info'>{personal}</div>")

        fee_head, fee_rows = _fee_block(st)
        if fee_head:
            fhead = "".join(f"<th>{_esc(h)}</th>" for h in fee_head)
            fbody = "".join("<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>"
                            for row in fee_rows)
            parts.append(f"<h3>Fees Details</h3><table><tr>{fhead}</tr>{fbody}</table>")

        if st["backlogs"]:
            brows = "".join(
                f"<tr><td>{_esc(b['subject'])}</td><td>{_esc(b['semester'])}</td>"
                f"<td>{_esc(b['year'])}</td></tr>"
                for b in st["backlogs"])
            parts.append(f"<h3>Backlogs / Arrears</h3><table><tr><th>Subject</th><th>Semester</th><th>Year</th></tr>{brows}</table>")

        if st["academic"]:
            has_sgpa = any(a["sgpa"] is not None for a in st["academic"])
            has_cgpa = any(a["cgpa"] is not None for a in st["academic"])
            arows = ""
            for a in st["academic"]:
                arows += f"<tr><td>Semester {_esc(a['semester'])}</td>"
                if has_sgpa:
                    arows += f"<td>{_esc('' if a['sgpa'] is None else round(a['sgpa'],2))}</td>"
                if has_cgpa:
                    arows += f"<td>{_esc('' if a['cgpa'] is None else round(a['cgpa'],2))}</td>"
                arows += "</tr>"
            a_cols = (["SGPA"] if has_sgpa else []) + (["Cumulative CGPA"] if has_cgpa else [])
            ahead = "".join(f"<th>{_esc(c)}</th>" for c in (["Semester"] + a_cols))
            parts.append(f"<h3>Academic Performance</h3><table>{ahead}{arows}</table>")

        lc_fields = _lifecycle_fields(st)
        hist = _lifecycle_history_rows(st)
        if lc_fields or hist:
            lc_html = "".join(f"<div><b>{_esc(lbl)}:</b> {_esc(val)}</div>" for lbl, val in lc_fields)
            parts.append(f"<h3>Lifecycle Status</h3><div class='info'>{lc_html}</div>")
        if hist:
            hrows = "".join(
                f"<tr><td>{_esc(h.get('created_at'))}</td><td>{_esc(h.get('event_type'))}</td>"
                f"<td>{_esc(h.get('from_status'))}</td><td>{_esc(h.get('to_status'))}</td>"
                f"<td>{_esc(h.get('actor_username'))}</td><td>{_esc(h.get('remarks'))}</td></tr>"
                for h in hist)
            parts.append("<p><i>Status change history:</i></p>"
                         "<table><tr><th>When</th><th>Event</th><th>From</th><th>To</th><th>By</th><th>Remarks</th></tr>"
                         f"{hrows}</table>")
        parts.append("</div>")

    if not model["is_single_student"] and model["table_rows"]:
        headers = model["table_headers"]
        head_html = "".join(f"<th>{_esc(_label(h))}</th>" for h in headers)
        body = "".join(
            "<tr>" + "".join(f"<td>{_esc(r.get(h))}</td>" for h in headers) + "</tr>"
            for r in model["table_rows"])
        parts.append(f"<h3>Query Results</h3><table><tr>{head_html}</tr>{body}</table>")

    parts.append(f"<div class='sig'><div><b>Prepared By:</b><br>{_esc(gen['username'])}<br>({gen['role']})</div>"
                 f"<div><b>Generated on:</b><br>{_esc(gen['timestamp'])}</div></div>")
    parts.append("</body></html>")
    return "".join(parts)


@router.post("/print")
def export_print(data: list[dict], current_user: dict = Depends(get_current_user)):
    """Print-ready HTML built from the SAME shared model as CSV/Excel/PDF."""
    if not data:
        raise HTTPException(400, "No data to export.")
    _log_export("print", len(data), current_user["username"])
    model = report_service.build_report_model(data, current_user)
    return HTMLResponse(_build_html_report(model))


# ── Category-scoped reports (Generate Report window) ─────────────────────────
#
# These endpoints receive EXACTLY the dashboard rows in the user's current
# filter/sort/page/selection scope and render only the selected category.
# Formats stay consistent because all four are built from one table model.

class ReportRequest(BaseModel):
    category: str
    format: str = "pdf"
    rows: list[dict]
    subtitle: str = ""


def _assemble_report(req: ReportRequest, user: dict):
    if not req.rows:
        raise HTTPException(400, "There are no displayed records to report on.")
    if req.category not in report_service.REPORT_CATEGORIES:
        raise HTTPException(400, f"Unknown report category: {req.category}")
    if req.category == "individual":
        model = report_service.build_report_model(req.rows, user)
        if len(model["students"]) != 1:
            raise HTTPException(400,
                                "Individual Student Report needs exactly one selected student.")
        return {"kind": "detail", "model": model}
    model = report_service.build_table_report_model(req.rows, user, req.category)
    if req.subtitle:
        model["subtitle"] = req.subtitle[:120]
    return {"kind": "table", "model": model}


@router.post("/report/preview")
def report_preview(req: ReportRequest, current_user: dict = Depends(get_current_user)):
    """JSON preview of the exact table the download/print will contain."""
    assembled = _assemble_report(req, current_user)
    if assembled["kind"] == "detail":
        st = assembled["model"]["students"][0]
        pairs = [(report_service.field_label(k), st["personal"].get(k))
                 for k, _ in report_service.PERSONAL_FIELDS
                 if st["personal"].get(k) not in (None, "", "null")]
        sections = [f"{len(st['academic'])} academic semester row(s)",
                    f"{len(st['fees'])} fee record(s)",
                    f"{len(st['backlogs'])} backlog record(s)",
                    "Lifecycle status and history"]
        return {
            "kind": "detail",
            "title": "Individual Student Report",
            "subtitle": f"{st['name']} ({st['usn']})",
            "columns": [{"key": "field", "label": "Field"}, {"key": "value", "label": "Value"}],
            "records": [{"field": f, "value": v} for f, v in pairs[:15]],
            "sections": sections,
            "record_count": 1,
            "notes": [],
        }
    model = assembled["model"]
    return {
        "kind": "table",
        "title": model["title"],
        "subtitle": model.get("subtitle", ""),
        "columns": model["columns"],
        "records": model["records"][:15],
        "record_count": model["record_count"],
        "truncated_preview": model["record_count"] > 15,
        "notes": model["notes"],
        "generated_by": model["generated_by"],
    }


# ── Table renderers (one model, four formats) ─────────────────────────────────

def _col_weights(columns, records, cap=30):
    weights = []
    for col in columns:
        longest = max([len(str(col["label"]))] +
                      [len(str(r.get(col["key"], ""))) for r in records[:200]])
        weights.append(min(max(longest + 2, 8), cap))
    return weights


_PT_CM = 0.03528  # 1 point in centimetres


def _fit_table_widths(columns, records, usable_cm, start_font, pad_pt):
    """Choose a font size and per-column widths so header words never break
    mid-word.

    Widths are measured exactly with reportlab's stringWidth. Every column gets
    at least the width of its longest header word (plus cell padding); short
    atomic values (a single token like a USN, phone or PIN) also set a floor so
    they stay on one line, while multi-word values and long tokens (emails,
    addresses) wrap inside their cell. Leftover space is shared by content
    weight. The font shrinks in 0.5pt steps until the minimums fit the page; if
    even the smallest legible font cannot fit, minimums are scaled pro-rata so
    columns are never reduced to single stacked characters.
    """
    from reportlab.pdfbase.pdfmetrics import stringWidth
    pad_cm = 2 * pad_pt * _PT_CM
    weights = _col_weights(columns, records)
    total_w = float(sum(weights)) or 1.0
    sample = records[:200]

    def _atomic_tokens(col):
        toks = []
        for r in sample:
            val = str(r.get(col["key"], "")).strip()
            if val and " " not in val and len(val) <= 14:
                toks.append(val)
        return toks

    def _mins_at(font):
        mins = []
        for col in columns:
            label_w = max((stringWidth(w, "Helvetica-Bold", font)
                           for w in str(col["label"]).split()), default=0.0)
            val_w = max((stringWidth(t, "Helvetica", font)
                         for t in _atomic_tokens(col)), default=0.0)
            mins.append(max(label_w, val_w) * _PT_CM + pad_cm)
        return mins

    font = start_font
    while font > 5.0:
        if sum(_mins_at(font)) <= usable_cm:
            break
        font -= 0.5
    else:
        font = 5.0
    mins = _mins_at(font)
    if sum(mins) > usable_cm:
        scale = usable_cm / sum(mins)
        return font, [m * scale for m in mins]
    leftover = usable_cm - sum(mins)
    widths = [mins[i] + leftover * weights[i] / total_w for i in range(len(columns))]
    return font, widths


# Beyond this many columns a horizontal table can no longer be shown legibly on
# a page (headers squeeze into single stacked characters), so the report switches
# to a one-sheet-per-record layout that lists every field as a Label: value pair.
_MAX_COLS_HORIZONTAL = 9


def _record_sheet_flowables(record, columns, s, usable_cm):
    """Render one record as a compact 'all on one sheet' block: a heading with
    the student's name and USN, then every remaining field laid out two
    Label: value pairs per row. Used for very wide reports so all columns stay
    readable on a page instead of being fragmented across many tables."""
    name = _cell_text(record.get("name"))
    usn = _cell_text(record.get("usn"))
    title = " · ".join(x for x in (name, usn) if x) or "Record"
    lbl_st = ParagraphStyle("rlbl", parent=s["norm"], fontName="Helvetica-Bold",
                            fontSize=7.5, leading=10, textColor=colors.HexColor(_DARK))
    val_st = ParagraphStyle("rval", parent=s["norm"], fontSize=7.5, leading=10)
    head_st = ParagraphStyle("rhead", parent=s["norm"], fontName="Helvetica-Bold",
                             fontSize=9.5, leading=12, textColor=colors.HexColor(_DARK),
                             spaceBefore=6, spaceAfter=3)
    fields = [c for c in columns if c["key"] not in ("usn", "name")]
    rows = []
    for i in range(0, len(fields), 2):
        cells = []
        for c in fields[i:i + 2]:
            cells.append(Paragraph(str(c["label"]), lbl_st))
            cells.append(Paragraph(_cell_text(record.get(c["key"])), val_st))
        while len(cells) < 4:
            cells.append(Paragraph("", val_st))
        rows.append(cells)
    if not rows:
        rows = [[Paragraph("", lbl_st), Paragraph("", val_st),
                 Paragraph("", lbl_st), Paragraph("", val_st)]]
    tbl = Table(rows, colWidths=[0.20 * usable_cm * cm, 0.30 * usable_cm * cm,
                                 0.20 * usable_cm * cm, 0.30 * usable_cm * cm])
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#b8c2d0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor(_LIGHT)),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor(_LIGHT)),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return [Paragraph(title, head_st), tbl]


class _NumberedCanvas(rl_canvas.Canvas):
    """Adds 'Page X of Y' plus a discreet footer to every PDF page."""
    footer_left = ""
    footer_right = ""

    def __init__(self, *args, **kwargs):
        self._saved_states = []
        super().__init__(*args, **kwargs)

    def showPage(self):
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_states)
        for state in self._saved_states:
            self.__dict__.update(state)
            width, _ = self._pagesize
            self.setFont("Helvetica", 7.5)
            self.setFillColor(colors.grey)
            if self.footer_left:
                self.drawString(1.5 * cm, 0.95 * cm, self.footer_left)
            self.drawCentredString(width / 2.0, 0.95 * cm,
                                   f"Page {self._pageNumber} of {total}")
            if self.footer_right:
                self.drawRightString(width - 1.5 * cm, 0.95 * cm, self.footer_right)
            rl_canvas.Canvas.showPage(self)
        rl_canvas.Canvas.save(self)


def _table_header_block(s, model):
    logo_cell = Paragraph("", s["norm"])
    if os.path.exists(LOGO_PATH):
        try:
            logo_cell = RLImage(LOGO_PATH, width=2.0 * cm, height=2.0 * cm)
        except Exception:
            pass
    hdr_tbl = Table([[logo_cell, [
        Paragraph(model["institution"]["university"], s["hdr"]), Spacer(1, 2),
        Paragraph(model["institution"]["college"], s["sub"]), Spacer(1, 2),
        Paragraph(model["institution"]["department"], s["dept"]),
    ]]], colWidths=[2.6 * cm, None])
    hdr_tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return hdr_tbl


def _build_table_pdf(path: str, model: dict):
    s = _pdf_styles()
    gen = model["generated_by"]
    columns = model["columns"]
    ncols = len(columns)

    # Very wide reports (student_list carries every field, ~50 columns) cannot be
    # shown as one horizontal table without squeezing headers into single stacked
    # characters, so each record is rendered on its own sheet as Label: value
    # pairs. Moderate tables go landscape; narrow ones stay portrait at full size.
    sheet_mode = ncols > _MAX_COLS_HORIZONTAL
    wide = ncols >= 7
    if sheet_mode:
        pagesize = A4
        lr_margin = 1.5 * cm
    else:
        pagesize = landscape(A4) if wide else A4
        lr_margin = 1.2 * cm if wide else 1.5 * cm
    usable_cm = (pagesize[0] / cm) - 2 * (lr_margin / cm)
    if ncols <= 6:
        font_size = 8.0
    elif ncols <= 10:
        font_size = 7.5
    elif ncols <= 16:
        font_size = 7.0
    else:
        font_size = 6.0

    story = [_table_header_block(s, model),
             HRFlowable(width="100%", thickness=1.5, color=colors.HexColor(_DARK), spaceAfter=6),
             Paragraph(model["title"], s["title"])]
    # A single-record report needs no "Records: 1" line; only count lists.
    if model["record_count"] and model["record_count"] != 1:
        story.append(Paragraph(f"Records: {model['record_count']}", s["sub"]))
    story.append(Paragraph(f"Generated on {gen['timestamp']} by {gen['username']} ({gen['role']})",
                           s["tiny"]))
    story.append(Spacer(1, 8))

    for note in model["notes"]:
        story.append(Paragraph(f"Note: {note}", s["norm"]))
    if model["notes"]:
        story.append(Spacer(1, 5))

    if model["records"]:
        if sheet_mode:
            for rec in model["records"]:
                story.extend(_record_sheet_flowables(rec, columns, s, usable_cm))
                story.append(Spacer(1, 10))
        else:
            pad_pt = 4 if wide else 6
            fit_font, widths_cm = _fit_table_widths(
                columns, model["records"], usable_cm, font_size, pad_pt)
            widths = [w * cm for w in widths_cm]
            cell_style = ParagraphStyle("tc", parent=s["norm"], fontSize=fit_font,
                                        leading=fit_font + 3)
            head_style = ParagraphStyle("th", parent=s["norm"], fontName="Helvetica-Bold",
                                        fontSize=fit_font, leading=fit_font + 3,
                                        textColor=colors.white, alignment=TA_CENTER)
            head = [Paragraph(str(c["label"]), head_style) for c in columns]
            body = [[Paragraph(_cell_text(r.get(c["key"])), cell_style) for c in columns]
                    for r in model["records"]]
            story.append(_pdf_table(head, body, widths=widths, pad=pad_pt))
    else:
        story.append(Paragraph("No records match this report for the selected students.", s["norm"]))

    story.append(Spacer(1, 14))
    sig_left = usable_cm * 0.53 * cm
    sig_right = usable_cm * 0.47 * cm
    sig = Table([[
        Paragraph(f"<b>Prepared By:</b><br/><br/>Signature: {gen['username']}<br/><br/><b>({gen['role']})</b>", s["sign"]),
        Paragraph(f"<b>Generated on:</b><br/>{gen['timestamp']}", s["sign"]),
    ]], colWidths=[sig_left, sig_right])
    sig.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceBefore=6, spaceAfter=8))
    story.append(sig)

    doc = SimpleDocTemplate(path, pagesize=pagesize, leftMargin=lr_margin, rightMargin=lr_margin,
                            topMargin=1.4 * cm, bottomMargin=1.6 * cm,
                            title=model["title"], author=COLLEGE)
    canvas_cls = type("Canvas", (_NumberedCanvas,), {
        "footer_left": f"{model['title']}",
        "footer_right": f"Generated {gen['timestamp']}",
    })
    doc.build(story, canvasmaker=canvas_cls)


def _build_table_excel(path: str, model: dict):
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = model["title"][:31] or "Report"
    inst = model["institution"]
    gen = model["generated_by"]

    for line in (inst["university"], inst["college"], inst["department"]):
        ws.append([line])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True, size=11, color="1E3A5F")
    ws.append([f"{model['title']}"
               + (f" — {model['subtitle']}" if model.get("subtitle") else "")])
    ws.cell(row=ws.max_row, column=1).font = Font(bold=True, size=12)
    ws.append([f"Generated on {gen['timestamp']} by {gen['username']} ({gen['role']})"
               f" · Records: {model['record_count']}"])
    ws.append([])

    columns = model["columns"]
    header_row = ws.max_row + 1
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for idx, col in enumerate(columns, start=1):
        cell = ws.cell(row=header_row, column=idx, value=col["label"])
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1E3A5F")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border
    for rec in model["records"]:
        vals = []
        for col in columns:
            v = rec.get(col["key"])
            number = report_service._to_number(v) if isinstance(v, str) else None
            vals.append(v if number is None else number)
        ws.append(vals)
    last_row = ws.max_row
    if last_row > header_row:
        for r in range(header_row + 1, last_row + 1):
            for cidx in range(1, len(columns) + 1):
                ws.cell(row=r, column=cidx).border = border
    ws.auto_filter.ref = f"A{header_row}:{get_column_letter(len(columns))}{max(last_row, header_row)}"
    ws.freeze_panes = f"A{header_row + 1}"

    for idx, col in enumerate(columns, start=1):
        longest = max([len(str(col["label"]))] +
                      [len(str(r.get(col["key"], ""))) for r in model["records"]])
        ws.column_dimensions[get_column_letter(idx)].width = min(longest + 3, 48)

    ws.append([])
    for note in model["notes"]:
        ws.append([f"Note: {note}"])
    ws.append(["Prepared By:", gen["username"], f"({gen['role']})"])
    ws.append(["Generated on:", gen["timestamp"]])
    _harden_workbook(wb)
    wb.save(path)


def _build_table_csv(path: str, model: dict):
    """CSV is intentionally limited to the selected records and category columns."""
    import csv
    columns = model["columns"]
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = _safe_writer(csv.writer(fh))
        w.writerow([c["label"] for c in columns])
        for rec in model["records"]:
            w.writerow([rec.get(c["key"], "") for c in columns])


def _build_table_html(model: dict) -> str:
    gen = model["generated_by"]
    inst = model["institution"]
    columns = model["columns"]
    ncols = len(columns)
    # Mirror the PDF: very wide reports render one sheet per record as Label:
    # value pairs; moderate/narrow reports stay a single horizontal table.
    sheet_mode = ncols > _MAX_COLS_HORIZONTAL
    page_size = "A4" if sheet_mode else ("A4 landscape" if ncols >= 7 else "A4")
    notes_html = "".join(f"<p class='note'><b>Note:</b> {_esc(n)}</p>" for n in model["notes"])
    records_line = (f"Records: {model['record_count']} · "
                    if model["record_count"] and model["record_count"] != 1 else "")

    if sheet_mode:
        blocks = []
        fields = [c for c in columns if c["key"] not in ("usn", "name")]
        for r in model["records"]:
            name = _esc(_cell_text(r.get("name")))
            usn = _esc(_cell_text(r.get("usn")))
            title = " · ".join(x for x in (name, usn) if x) or "Record"
            rows_html = []
            for i in range(0, len(fields), 2):
                cells = []
                for c in fields[i:i + 2]:
                    cells.append(f"<th>{_esc(c['label'])}</th>"
                                 f"<td>{_esc(_cell_text(r.get(c['key'])))}</td>")
                while len(cells) < 4:
                    cells.append("<th></th><td></td>")
                rows_html.append("<tr>" + "".join(cells) + "</tr>")
            blocks.append(f"<div class='sheet'><h4>{title}</h4>"
                          f"<table class='kv'>{''.join(rows_html)}</table></div>")
        body_html = "".join(blocks) or \
            "<p class='note'>No records match this report for the selected students.</p>"
    else:
        head_html = "".join(f"<th>{_esc(c['label'])}</th>" for c in columns)
        body_rows = "".join(
            "<tr>" + "".join(f"<td>{_esc(_cell_text(r.get(c['key'])))}</td>" for c in columns) + "</tr>"
            for r in model["records"])
        body_html = (f"<table><thead><tr>{head_html}</tr></thead><tbody>{body_rows}</tbody></table>"
                     if model["records"] else
                     "<p class='note'>No records match this report for the selected students.</p>")

    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{_esc(model['title'])}</title>
<style>
@page {{ size: {page_size}; margin: 14mm 12mm; }}
body {{ font-family: Arial, Helvetica, sans-serif; font-size: 11px; color:#111; margin:0; }}
.inst {{ text-align:center; }}
.inst h1 {{ font-size:14px; margin:2px 0; color:#1e3a5f; }}
.inst h2 {{ font-size:12px; margin:2px 0; color:#1e3a5f; }}
.inst h3 {{ font-size:11px; margin:2px 0; color:#1e3a5f; }}
hr {{ border:1px solid #1e3a5f; margin:6px 0; }}
.title {{ text-align:center; font-size:14px; font-weight:bold; margin:8px 0 2px; }}
.meta {{ text-align:center; font-size:10px; color:#444; margin-bottom:10px; }}
table {{ border-collapse:collapse; width:100%; table-layout:auto; }}
th, td {{ border:1px solid #9aa7b8; padding:4px 6px; text-align:left;
          word-wrap:break-word; overflow-wrap:break-word; max-width:220px; }}
th {{ background:#1e3a5f; color:#fff; font-size:10.5px; position:sticky; top:0; }}
tr:nth-child(even) td {{ background:#f4f7fb; }}
tr {{ page-break-inside:avoid; }}
thead {{ display:table-header-group; }}
.sheet {{ page-break-inside:avoid; margin:14px 0; }}
.sheet h4 {{ font-size:12px; color:#1e3a5f; margin:0 0 4px; }}
.kv th {{ background:#eef2f8; color:#1e3a5f; width:20%; position:static; }}
.kv td {{ width:30%; }}
.note {{ font-size:10px; color:#444; margin:2px 0; }}
.sig {{ margin-top:26px; display:flex; justify-content:space-between; font-size:11px; }}
@media print {{ .noprint {{ display:none; }} body {{ font-size:10px; }} }}
</style></head><body>
<div class="inst"><h1>{_esc(inst['university'])}</h1><h2>{_esc(inst['college'])}</h2>
<h3>{_esc(inst['department'])}</h3></div>
<hr>
<div class="title">{_esc(model['title'])}</div>
<div class="meta">{records_line}Generated on {_esc(gen['timestamp'])}
by {_esc(gen['username'])} ({_esc(gen['role'])})</div>
{notes_html}
{body_html}
<div class="sig"><div><b>Prepared By:</b><br><br>{_esc(gen['username'])}<br>({_esc(gen['role'])})</div>
<div><b>Generated on:</b><br>{_esc(gen['timestamp'])}</div></div>
</body></html>"""


@router.post("/report")
def generate_report(req: ReportRequest, current_user: dict = Depends(get_current_user)):
    assembled = _assemble_report(req, current_user)
    fmt = (req.format or "pdf").lower()

    if assembled["kind"] == "detail":
        # Individual report = full authorized profile of exactly one student,
        # built by the same shared detail model used by the legacy exports.
        model = assembled["model"]
        if fmt == "pdf":
            fd, path = tempfile.mkstemp(suffix=".pdf"); os.close(fd)
            _build_branded_pdf(path, model)
        elif fmt == "excel":
            resp = export_excel(req.rows, current_user)
            return FileResponse(resp.path, filename="individual_student_report.xlsx",
                                media_type=resp.media_type)
        elif fmt == "csv":
            resp = export_csv(req.rows, current_user)
            return FileResponse(resp.path, filename="individual_student_report.csv",
                                media_type=resp.media_type)
        elif fmt == "print":
            _log_export("print", 1, current_user["username"])
            return HTMLResponse(_build_html_report(model))
        else:
            raise HTTPException(400, f"Unsupported format: {fmt}")
        _log_export(f"individual_{fmt}", 1, current_user["username"])
        return FileResponse(path, filename="individual_student_report.pdf",
                            media_type="application/pdf")

    model = assembled["model"]
    base_name = f"{req.category}_report"
    if fmt == "pdf":
        fd, path = tempfile.mkstemp(suffix=".pdf"); os.close(fd)
        _build_table_pdf(path, model)
        _log_export(fmt, model["record_count"], current_user["username"])
        return FileResponse(path, filename=f"{base_name}.pdf", media_type="application/pdf")
    if fmt == "excel":
        fd, path = tempfile.mkstemp(suffix=".xlsx"); os.close(fd)
        _build_table_excel(path, model)
        _log_export(fmt, model["record_count"], current_user["username"])
        return FileResponse(path, filename=f"{base_name}.xlsx",
                            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if fmt == "csv":
        fd, path = tempfile.mkstemp(suffix=".csv"); os.close(fd)
        _build_table_csv(path, model)
        _log_export(fmt, model["record_count"], current_user["username"])
        return FileResponse(path, filename=f"{base_name}.csv", media_type="text/csv")
    if fmt == "print":
        _log_export("print", model["record_count"], current_user["username"])
        return HTMLResponse(_build_table_html(model))
    raise HTTPException(400, f"Unsupported format: {fmt}")
