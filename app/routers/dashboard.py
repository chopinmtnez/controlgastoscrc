from datetime import date, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import Factura
from resumen import calcular_kpis, calcular_resumen_curso

router = APIRouter()
templates = Jinja2Templates(directory="templates")

CURSO_INICIO = date(2025, 10, 1)
CURSO_FIN = date(2026, 6, 30)


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, insertados: int = 0, omitidos: int = 0, db: Session = Depends(get_db)):
    resumenes = calcular_resumen_curso(db, CURSO_INICIO, CURSO_FIN)
    kpis = calcular_kpis(resumenes)
    facturas_recientes = (
        db.query(Factura).order_by(Factura.creado_en.desc()).limit(5).all()
    )
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "resumenes": resumenes,
            "kpis": kpis,
            "facturas_recientes": facturas_recientes,
            "today": date.today(),
            "insertados": insertados,
            "omitidos": omitidos,
            "page": "dashboard",
        },
    )
