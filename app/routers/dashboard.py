from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import Factura
from resumen import calcular_kpis, calcular_resumen_curso
from curso import get_curso_fechas, get_curso_nombre

router = APIRouter()
templates = Jinja2Templates(directory="templates")

PREVISION_MENSUAL = Decimal("455.00")


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, insertados: int = 0, omitidos: int = 0, db: Session = Depends(get_db)):
    hoy = date.today()
    mes_actual = date(hoy.year, hoy.month, 1)
    curso_inicio, curso_fin = get_curso_fechas(db)

    todos = calcular_resumen_curso(db, curso_inicio, curso_fin)
    resumenes = [r for r in todos if r.mes <= mes_actual]
    prevision  = [r for r in todos if r.mes >  mes_actual]

    kpis = calcular_kpis(resumenes)
    facturas_recientes = (
        db.query(Factura).order_by(Factura.creado_en.desc()).limit(5).all()
    )
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "resumenes": resumenes,
            "prevision": prevision,
            "kpis": kpis,
            "facturas_recientes": facturas_recientes,
            "today": hoy,
            "insertados": insertados,
            "omitidos": omitidos,
            "page": "dashboard",
            "prevision_mensual": PREVISION_MENSUAL,
            "curso_nombre": get_curso_nombre(db),
        },
    )
