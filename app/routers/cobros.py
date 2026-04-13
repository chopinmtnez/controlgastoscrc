from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import Cobro
from resumen import calcular_resumen_curso
from curso import get_curso_fechas, get_curso_nombre

router = APIRouter(prefix="/cobros")
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
async def cobros_list(request: Request, db: Session = Depends(get_db)):
    cobros = db.query(Cobro).order_by(Cobro.fecha.desc()).all()
    curso_inicio, curso_fin = get_curso_fechas(db)
    resumenes = calcular_resumen_curso(db, curso_inicio, curso_fin)
    return templates.TemplateResponse(
        "cobros.html", {"request": request, "cobros": cobros, "resumenes": resumenes, "page": "cobros", "curso_nombre": get_curso_nombre(db)}
    )


@router.post("")
async def cobros_create(
    fecha: str = Form(...),
    importe: str = Form(...),
    mes_referencia: str = Form(...),
    descripcion: str = Form(""),
    db: Session = Depends(get_db),
):
    mes_ref = date.fromisoformat(mes_referencia)
    cobro = Cobro(
        fecha=date.fromisoformat(fecha),
        importe=importe,
        mes_referencia=date(mes_ref.year, mes_ref.month, 1),
        descripcion=descripcion or None,
    )
    db.add(cobro)
    db.commit()
    return RedirectResponse(url="/cobros", status_code=302)


@router.post("/{cobro_id}/delete")
async def cobros_delete(cobro_id: str, db: Session = Depends(get_db)):
    cobro = db.query(Cobro).filter(Cobro.id == cobro_id).first()
    if cobro:
        db.delete(cobro)
        db.commit()
    return RedirectResponse(url="/cobros", status_code=302)


@router.get("/{cobro_id}/edit", response_class=HTMLResponse)
async def cobros_edit_get(request: Request, cobro_id: str, db: Session = Depends(get_db)):
    cobro = db.query(Cobro).filter(Cobro.id == cobro_id).first()
    if not cobro:
        return RedirectResponse(url="/cobros", status_code=302)
    return templates.TemplateResponse("cobro_edit.html", {"request": request, "cobro": cobro, "page": "cobros"})


@router.post("/{cobro_id}/edit")
async def cobros_edit_post(
    cobro_id: str,
    fecha: str = Form(...),
    importe: str = Form(...),
    mes_referencia: str = Form(...),
    descripcion: str = Form(""),
    db: Session = Depends(get_db),
):
    cobro = db.query(Cobro).filter(Cobro.id == cobro_id).first()
    if cobro:
        mes_ref = date.fromisoformat(mes_referencia)
        cobro.fecha = date.fromisoformat(fecha)
        cobro.importe = importe
        cobro.mes_referencia = date(mes_ref.year, mes_ref.month, 1)
        cobro.descripcion = descripcion or None
        db.commit()
    return RedirectResponse(url="/cobros", status_code=302)
