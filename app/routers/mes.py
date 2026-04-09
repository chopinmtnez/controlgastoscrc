from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import Cobro, Factura
from resumen import ResumenMes, calcular_resumen_curso

router = APIRouter(prefix="/mes")
templates = Jinja2Templates(directory="templates")

CURSO_INICIO = date(2025, 10, 1)
CURSO_FIN = date(2026, 6, 30)


@router.get("/{yyyy_mm}", response_class=HTMLResponse)
async def mes_detalle(request: Request, yyyy_mm: str, db: Session = Depends(get_db)):
    try:
        year, month = int(yyyy_mm[:4]), int(yyyy_mm[5:7])
        mes_ref = date(year, month, 1)
    except Exception:
        return RedirectResponse(url="/", status_code=302)

    facturas = db.query(Factura).filter(
        Factura.mes_referencia >= mes_ref,
        Factura.mes_referencia < date(year + (month // 12), (month % 12) + 1, 1),
    ).order_by(Factura.fecha_emision).all()

    cobros = db.query(Cobro).filter(
        Cobro.mes_referencia >= mes_ref,
        Cobro.mes_referencia < date(year + (month // 12), (month % 12) + 1, 1),
    ).order_by(Cobro.fecha).all()

    resumenes = calcular_resumen_curso(db, CURSO_INICIO, CURSO_FIN)
    resumen_mes = next((r for r in resumenes if r.mes == mes_ref), None)

    return templates.TemplateResponse(
        "mes.html",
        {
            "request": request,
            "mes_ref": mes_ref,
            "facturas": facturas,
            "cobros": cobros,
            "resumen": resumen_mes,
            "page": "dashboard",
        },
    )
