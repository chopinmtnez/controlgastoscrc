from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from auth import AuthMiddleware
from database import create_tables, SessionLocal
from scheduler import iniciar_scheduler
from curso import ensure_curso_default

from routers import auth_router, dashboard, facturas, cobros, beca, mes, documentos, gmail, banco
from routers import actividad, config as config_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    # Crear curso 2025/26 por defecto si no existe ninguno
    db = SessionLocal()
    try:
        ensure_curso_default(db)
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
