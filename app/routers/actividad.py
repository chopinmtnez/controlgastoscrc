from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import ActivityLog
from curso import get_curso_nombre

router = APIRouter(prefix="/actividad")
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
async def actividad_list(
    request: Request,
    tipo: str = None,
    db: Session = Depends(get_db),
):
    query = db.query(ActivityLog).order_by(ActivityLog.timestamp.desc())
    if tipo and tipo in ("scheduler", "manual", "config", "sistema"):
        query = query.filter(ActivityLog.tipo == tipo)
    logs = query.limit(200).all()

    return templates.TemplateResponse(
        "actividad.html",
        {
            "request": request,
            "logs": logs,
            "tipo_filtro": tipo,
            "page": "actividad",
            "curso_nombre": get_curso_nombre(db),
        },
    )
