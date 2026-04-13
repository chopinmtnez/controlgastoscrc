"""Helper para obtener el curso escolar activo desde la BD."""
from datetime import date
from sqlalchemy.orm import Session
from models import CursoConfig

_FALLBACK_INICIO = date(2025, 10, 1)
_FALLBACK_FIN    = date(2026, 6, 30)
_FALLBACK_NOMBRE = "Curso 2025/26"


def get_curso_activo(db: Session) -> CursoConfig | None:
    return db.query(CursoConfig).filter(CursoConfig.activo == True).first()


def get_curso_fechas(db: Session) -> tuple[date, date]:
    curso = get_curso_activo(db)
    if curso:
        return curso.fecha_inicio, curso.fecha_fin
    return _FALLBACK_INICIO, _FALLBACK_FIN


def get_curso_nombre(db: Session) -> str:
    curso = get_curso_activo(db)
    return curso.nombre if curso else _FALLBACK_NOMBRE


def ensure_curso_default(db: Session) -> None:
    """Crea el curso 2025/26 si no existe ninguno."""
    if db.query(CursoConfig).count() == 0:
        db.add(CursoConfig(
            nombre=_FALLBACK_NOMBRE,
            fecha_inicio=_FALLBACK_INICIO,
            fecha_fin=_FALLBACK_FIN,
            activo=True,
        ))
        db.commit()
