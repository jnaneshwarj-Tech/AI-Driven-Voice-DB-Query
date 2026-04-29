from fastapi import APIRouter, Depends
from fastapi.responses import Response
from auth import get_current_user
from export_service import to_csv, to_excel, to_pdf

router = APIRouter(prefix="/api/export", tags=["Export"])

@router.post("/csv")
def export_csv(data: list[dict], current_user: dict = Depends(get_current_user)):
    return Response(content=to_csv(data), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=results.csv"})

@router.post("/excel")
def export_excel(data: list[dict], current_user: dict = Depends(get_current_user)):
    return Response(content=to_excel(data),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=results.xlsx"})

@router.post("/pdf")
def export_pdf(data: list[dict], current_user: dict = Depends(get_current_user)):
    return Response(content=to_pdf(data), media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=results.pdf"})
