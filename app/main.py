from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from auth import AuthMiddleware, APP_USERNAME, APP_PASSWORD_HASH, hash_password
from database import create_tables, SessionLocal
from scheduler import iniciar_scheduler
from curso import ensure_curso_default

from routers import auth_router, dashboard, facturas, cobros, beca, mes, documentos, gmail, banco
from routers import actividad, config as config_router


def _ensure_default_user(db):
    """Si no hay usuarios en BD, migra el usuario de variables de entorno."""
    from models import Usuario
    if db.query(Usuario).count() > 0:
        return
    if APP_USERNAME and APP_PASSWORD_HASH:
        user = Usuario(
            username=APP_USERNAME,
            nombre=APP_USERNAME.capitalize(),
            password_hash=APP_PASSWORD_HASH,
            activo=True,
        )
        db.add(user)
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    db = SessionLocal()
    try:
        ensure_curso_default(db)
        _ensure_default_user(db)
    finally:
        db.close()
    scheduler = iniciar_scheduler()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="ControlGastosCRC", docs_url=None, redoc_url=None, lifespan=lifespan)

app.add_middleware(AuthMiddleware)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth_router.router)
app.include_router(dashboard.router)
app.include_router(facturas.router)
app.include_router(cobros.router)
app.include_router(beca.router)
app.include_router(mes.router)
app.include_router(documentos.router)
app.include_router(gmail.router)
app.include_router(banco.router)
app.include_router(actividad.router)
app.include_router(config_router.router)
