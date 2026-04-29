"""
export_service.py — Export query results to CSV, Excel, PDF.
"""
import io
import pandas as pd
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

def to_csv(data: list[dict]) -> bytes:
    df = pd.DataFrame(data)
    return df.to_csv(index=False).encode('utf-8')

def to_excel(data: list[dict]) -> bytes:
    df = pd.DataFrame(data)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Results')
    return buf.getvalue()

def to_pdf(data: list[dict]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter), rightMargin=20, leftMargin=20, topMargin=30, bottomMargin=20)
    styles = getSampleStyleSheet()
    elements = [Paragraph("Query Results", styles['Title'])]

    if not data:
        elements.append(Paragraph("No data.", styles['Normal']))
    else:
        headers = list(data[0].keys())
        table_data = [headers] + [[str(row.get(h, '')) for h in headers] for row in data]
        t = Table(table_data, repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
            ('TEXTCOLOR',  (0, 0), (-1, 0), colors.white),
            ('FONTNAME',   (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',   (0, 0), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f1f5f9')]),
            ('GRID',       (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('ALIGN',      (0, 0), (-1, -1), 'LEFT'),
            ('PADDING',    (0, 0), (-1, -1), 4),
        ]))
        elements.append(t)

    doc.build(elements)
    return buf.getvalue()
