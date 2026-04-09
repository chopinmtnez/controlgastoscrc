from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import BecaConfig

router = APIRouter(prefix="/beca")
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
async def beca_list(request: Request, db: Session = Depends(get_db)):
    becas = db.query(BecaConfig).order_by(BecaConfig.fecha_inicio.desc()).all()
    return templates.TemplateResponse("beca.html", {"request": request, "becas": becas, "page": "beca"})


@router.post("/{beca_id}/edit")
async def beca_edit(
    beca_id: str,
    descripcion: str = Form(...),
    importe_mensual: str = Form(...),
    fecha_inicio: str = Form(...),
    fecha_fin: str = Form(...),
    activa: str = Form("off"),
    db: Session = Depends(get_db),
):
    beca = db.query(BecaConfig).filter(BecaConfig.id == beca_id).first()
    if beca:
        beca.descripcion = descripcion
        beca.importe_mensual = importe_mensual
        beca.fecha_inicio = date.fromisoformat(fecha_inicio)
        beca.fecha_fin = date.fromisoformat(fecha_fin)
        beca.activa = activa == "on"
        db.commit()
    return RedirectResponse(url="/beca", status_code=302)
