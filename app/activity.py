"""Helper para registrar entradas en el log de actividad."""
import json
import logging
from datetime import datetime

from models import ActivityLog

log = logging.getLogger("activity")


def registrar(
    db,
    tipo: str,
    accion: str,
    resumen: str = "",
    origen: str = "usuario",
    ok: bool = True,
    detalle: dict | None = None,
) -> None:
    """Inserta una entrada en activity_log y hace commit."""
    try:
        entry = ActivityLog(
            tipo=tipo,
            accion=accion,
            origen=origen,
            ok=ok,
            resumen=resumen,
            detalle=json.dumps(detalle, default=str) if detalle else None,
        )
        db.add(entry)
        db.commit()
    except Exception as e:
        log.error(f"Error al registrar actividad: {e}")
