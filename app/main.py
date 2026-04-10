from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from auth import AuthMiddleware
from database import create_tables
from scheduler import iniciar_scheduler

from routers import auth_router, dashboard, facturas, cobros, beca, mes, documentos, gmail, banco


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
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
