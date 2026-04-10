from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from auth import AuthMiddleware
from database import create_tables

from routers import auth_router, dashboard, facturas, cobros, beca, mes, documentos, gmail

app = FastAPI(title="ControlGastosCRC", docs_url=None, redoc_url=None)

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


@app.on_event("startup")
def startup():
    create_tables()
