import os

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from gmail_importer import GMAIL_SENDER_FILTER, GMAIL_USER, import_from_gmail
from notifier import NOTIFICATION_EMAIL, notify_import_result, send_email

router = APIRouter(prefix="/gmail")
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
async def gmail_page(
    request: Request,
    ok: int = None,
    insertados: int = None,
    omitidos: int = None,
    error: str = None,
    test: int = None,
):
    configurado = bool(GMAIL_USER and os.getenv("GMAIL_APP_PASSWORD"))
    return templates.TemplateResponse(
        "gmail.html",
        {
            "request": request,
            "page": "gmail",
            "configurado": configurado,
            "gmail_user": GMAIL_USER,
            "notification_email": NOTIFICATION_EMAIL,
            "sender_filter": GMAIL_SENDER_FILTER,
            "ok": ok,
            "insertados": insertados,
            "omitidos": omitidos,
            "error": error,
            "test": test,
        },
    )


@router.post("/importar")
async def gmail_importar(request: Request, db: Session = Depends(get_db)):
    resultado = import_from_gmail(db)

    if not resultado["ok"]:
        # URL-encode el error básico
        err = resultado["error"].replace(" ", "+").replace("&", "%26")
        return RedirectResponse(url=f"/gmail?error={err}", status_code=302)

    insertados = resultado["insertados"]
    omitidos = resultado["omitidos"]
    errores = resultado.get("errores", [])

    if insertados > 0:
        notify_import_result(insertados, omitidos, errores)

    return RedirectResponse(
        url=f"/gmail?ok=1&insertados={insertados}&omitidos={omitidos}",
        status_code=302,
    )


@router.post("/test-email")
async def gmail_test_email(request: Request):
    ok = send_email(
        "ControlGastosCRC · Notificaciones activas ✓",
        """<html><body style="font-family:sans-serif;background:#0f172a;color:#e2e8f0;padding:24px">
        <h2 style="color:#22c55e">✅ Notificaciones configuradas correctamente</h2>
        <p>ControlGastosCRC enviará alertas a esta dirección cuando:</p>
        <ul>
          <li>Se importen nuevas facturas desde Gmail</li>
          <li>Exista una diferencia entre lo facturado y lo cobrado</li>
        </ul>
        <p style="font-size:12px;color:#64748b">ControlGastosCRC · Lucía · Curso 25/26</p>
        </body></html>""",
    )
    return RedirectResponse(url=f"/gmail?test={'1' if ok else '0'}", status_code=302)
