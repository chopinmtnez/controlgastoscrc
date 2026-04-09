import io
import os
import zipfile

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import Factura

router = APIRouter(prefix="/documentos")
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
async def documentos_list(request: Request, db: Session = Depends(get_db)):
    facturas = db.query(Factura).order_by(Factura.fecha_emision.desc()).all()
    return templates.TemplateResponse(
        "documentos.html", {"request": request, "facturas": facturas, "page": "documentos"}
    )


@router.get("/zip")
async def documentos_zip(db: Session = Depends(get_db)):
    facturas = db.query(Factura).order_by(Factura.fecha_emision.desc()).all()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in facturas:
            if os.path.exists(f.pdf_path):
                arcname = f"{f.mes_referencia.strftime('%Y-%m')}_{f.numero_documento}_{f.tipo.value}.pdf"
                zf.write(f.pdf_path, arcname)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=facturas_CRC.zip"},
    )


@router.get("/{factura_id}/pdf")
async def documentos_pdf(factura_id: str, db: Session = Depends(get_db)):
    factura = db.query(Factura).filter(Factura.id == factura_id).first()
    if not factura or not os.path.exists(factura.pdf_path):
        return HTMLResponse("PDF no encontrado", status_code=404)
    filename = f"{factura.numero_documento}.pdf"
    return FileResponse(factura.pdf_path, media_type="application/pdf", filename=filename)
