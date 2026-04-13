import os
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import BecaConfig, CursoConfig, CuentaBanco, ActivityLog
from curso import get_curso_nombre
from activity import registrar
import enable_banking as eb
from gmail_importer import GMAIL_SENDER_FILTER, GMAIL_USER
from notifier import NOTIFICATION_EMAIL

router = APIRouter(prefix="/config")
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
async def config_page(request: Request, ok: str = None, error: str = None,
                      importados: int = None, omitidos: int = None,
                      insertados: int = None, db: Session = Depends(get_db)):
    cursos = db.query(CursoConfig).order_by(CursoConfig.fecha_inicio.desc()).all()
    becas = db.query(BecaConfig).order_by(BecaConfig.fecha_inicio.desc()).all()

    # ING status
    cuenta = db.query(CuentaBanco).first()

    # Gmail status
    gmail_configurado = bool(GMAIL_USER and os.getenv("GMAIL_APP_PASSWORD"))

    # Actividad reciente
    logs = (
        db.query(ActivityLog)
        .order_by(ActivityLog.timestamp.desc())
        .limit(15)
        .all()
    )

    return templates.TemplateResponse(
        "config.html",
        {
            "request": request,
            "cursos": cursos,
            "becas": becas,
            "ok": ok,
            "error": error,
            "importados": importados,
            "omitidos": omitidos,
            "insertados": insertados,
            "page": "config",
            "curso_nombre": get_curso_nombre(db),
            # ING
            "cuenta": cuenta,
            "ing_configurado": eb.configured(),
            "ing_sandbox": eb.EB_SANDBOX,
            "ing_prelinked": eb.get_prelinked_accounts(),
            # Gmail
            "gmail_configurado": gmail_configurado,
            "gmail_user": GMAIL_USER,
            "notification_email": NOTIFICATION_EMAIL,
            "sender_filter": GMAIL_SENDER_FILTER,
            # Actividad
            "logs": logs,
        },
    )


# ── Cursos ────────────────────────────────────────────────────────────────────

@router.post("/curso/nuevo")
async def curso_nuevo(
    nombre: str = Form(...),
    fecha_inicio: str = Form(...),
    fecha_fin: str = Form(...),
    db: Session = Depends(get_db),
):
    # Desactivar el actual
    for c in db.query(CursoConfig).filter(CursoConfig.activo == True).all():
        c.activo = False

    curso = CursoConfig(
        nombre=nombre,
        fecha_inicio=date.fromisoformat(fecha_inicio),
        fecha_fin=date.fromisoformat(fecha_fin),
        activo=True,
    )
    db.add(curso)
    db.commit()

    registrar(db, tipo="config", accion="curso_nuevo", origen="usuario",
              resumen=f"Nuevo curso activo: {nombre}",
              detalle={"nombre": nombre, "inicio": fecha_inicio, "fin": fecha_fin})

    return RedirectResponse(url="/config?ok=curso", status_code=302)


@router.post("/curso/{curso_id}/activar")
async def curso_activar(curso_id: str, db: Session = Depends(get_db)):
    for c in db.query(CursoConfig).all():
        c.activo = (str(c.id) == curso_id)
    db.commit()

    curso = db.query(CursoConfig).filter(CursoConfig.id == curso_id).first()
    registrar(db, tipo="config", accion="curso_activar", origen="usuario",
              resumen=f"Curso activado: {curso.nombre if curso else curso_id}")

    return RedirectResponse(url="/config?ok=curso", status_code=302)


@router.post("/curso/{curso_id}/delete")
async def curso_delete(curso_id: str, db: Session = Depends(get_db)):
    curso = db.query(CursoConfig).filter(CursoConfig.id == curso_id).first()
    if curso and not curso.activo:
        db.delete(curso)
        db.commit()
    return RedirectResponse(url="/config", status_code=302)


# ── Becas ─────────────────────────────────────────────────────────────────────

@router.post("/beca/nueva")
async def beca_nueva(
    descripcion: str = Form(...),
    importe_mensual: str = Form(...),
    fecha_inicio: str = Form(...),
    fecha_fin: str = Form(...),
    db: Session = Depends(get_db),
):
    beca = BecaConfig(
        descripcion=descripcion,
        importe_mensual=importe_mensual,
        fecha_inicio=date.fromisoformat(fecha_inicio),
        fecha_fin=date.fromisoformat(fecha_fin),
        activa=True,
    )
    db.add(beca)
    db.commit()

    registrar(db, tipo="config", accion="beca_nueva", origen="usuario",
              resumen=f"Nueva beca: {descripcion} — {importe_mensual} €/mes",
              detalle={"descripcion": descripcion, "importe": importe_mensual,
                       "inicio": fecha_inicio, "fin": fecha_fin})

    return RedirectResponse(url="/config?ok=beca", status_code=302)


@router.post("/beca/{beca_id}/edit")
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
        registrar(db, tipo="config", accion="beca_edit", origen="usuario",
                  resumen=f"Beca editada: {descripcion}")
    return RedirectResponse(url="/config?ok=beca", status_code=302)


@router.post("/beca/{beca_id}/delete")
async def beca_delete(beca_id: str, db: Session = Depends(get_db)):
    beca = db.query(BecaConfig).filter(BecaConfig.id == beca_id).first()
    if beca:
        db.delete(beca)
        db.commit()
    return RedirectResponse(url="/config", status_code=302)
