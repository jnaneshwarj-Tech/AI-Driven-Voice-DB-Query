import os, tempfile, json
import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from reportlab.lib.pagesizes import landscape, letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors

router = APIRouter(prefix="/api/export", tags=["Export"])

def _flatten(data: list[dict]) -> list[dict]:
    """Flatten nested dicts for tabular export."""
    flat = []
    for doc in data:
        row = {}
        for k, v in doc.items():
            if isinstance(v, dict):
                for sk, sv in v.items():
                    row[f"{k}.{sk}"] = sv
            elif isinstance(v, list):
                row[k] = str(v)
            else:
                row[k] = v
        flat.append(row)
    return flat

@router.post("/csv")
def export_csv(data: list[dict]):
    if not data:
        raise HTTPException(status_code=400, detail="No data to export.")
    df = pd.DataFrame(_flatten(data))
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        df.to_csv(f, index=False)
    return FileResponse(path, filename="results.csv", media_type="text/csv")

@router.post("/excel")
def export_excel(data: list[dict]):
    if not data:
        raise HTTPException(status_code=400, detail="No data to export.")
    df = pd.DataFrame(_flatten(data))
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    df.to_excel(path, index=False)
    return FileResponse(path, filename="results.xlsx", media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@router.post("/pdf")
def export_pdf(data: list[dict]):
    if not data:
        raise HTTPException(status_code=400, detail="No data to export.")
    flat = _flatten(data)
    df = pd.DataFrame(flat)
    headers = list(df.columns)
    rows = df.astype(str).values.tolist()

    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    doc = SimpleDocTemplate(path, pagesize=landscape(letter))
    table_data = [headers] + rows
    t = Table(table_data, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
    ]))
    doc.build([t])
    return FileResponse(path, filename="results.pdf", media_type="application/pdf")

@router.post("/json")
def export_json(data: list[dict]):
    if not data:
        raise HTTPException(status_code=400, detail="No data to export.")
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, default=str)
    return FileResponse(path, filename="results.json", media_type="application/json")
