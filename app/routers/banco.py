"""
Router /banco — Conexión Open Banking con ING via Enable Banking.

Flujo:
1. GET  /banco              → página de estado
2. GET  /banco/aspsps       → lista de bancos (JSON, para el selector)
3. GET  /banco/conectar     → inicia OAuth con el banco seleccionado
4. GET  /banco/callback     → Enable Banking redirige aquí tras autorizar
5. POST /banco/sincronizar  → descarga transacciones y crea Cobros nuevos
6. POST /banco/desconectar  → revoca sesión y limpia BD
"""
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import enable_banking as eb
from database import get_db
from models import Cobro, CuentaBanco

router = APIRouter(prefix="/banco")
templates = Jinja2Templates(directory="templates")

# URL pública de callback (debe coincidir con lo registrado en Enable Banking)
_APP_URL = "https://controlgastoscrc.albertomartinezmartin.com"
_CALLBACK_URL = f"{_APP_URL}/banco/callback"


def _get_or_create_cuenta(db: Session) -> CuentaBanco:
    """Devuelve (o crea) el único registro CuentaBanco de la app."""
    cuenta = db.query(CuentaBanco).first()
    if not cuenta:
        cuenta = CuentaBanco()
        db.add(cuenta)
        db.commit()
        db.refresh(cuenta)
    return cuenta


# ── Páginas ────────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def banco_page(
    request: Request,
    db: Session = Depends(get_db),
    ok: int = None,
    importados: int = None,
    omitidos: int = None,
    error: str = None,
):
    cuenta = _get_or_create_cuenta(db)
    return templates.TemplateResponse(
        "banco.html",
        {
            "request": request,
            "page": "banco",
            "cuenta": cuenta,
            "configurado": eb.configured(),
            "sandbox": eb.EB_SANDBOX,
            "ok": ok,
            "importados": importados,
            "omitidos": omitidos,
            "error": error,
        },
    )


@router.get("/aspsps")
async def get_aspsps():
    """Devuelve la lista de bancos disponibles en España (JSON)."""
    try:
        aspsps = eb.get_aspsps("ES")
        return JSONResponse({"aspsps": aspsps})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── OAuth flow ─────────────────────────────────────────────────────────────────

@router.get("/conectar")
async def banco_conectar(
    request: Request,
    aspsp: str = "ING",
    country: str = "ES",
    db: Session = Depends(get_db),
):
    """Inicia el flujo OAuth con el banco seleccionado."""
    if not eb.configured():
        return RedirectResponse(url="/banco?error=Enable+Banking+no+configurado", status_code=302)

    estado = str(uuid.uuid4())

    try:
        result = eb.start_auth(
            aspsp_name=aspsp,
            aspsp_country=country,
            redirect_url=_CALLBACK_URL,
            state=estado,
        )
    except Exception as e:
        err = str(e).replace(" ", "+")[:200]
        return RedirectResponse(url=f"/banco?error={err}", status_code=302)

    auth_url = result.get("url", "")
    if not auth_url:
        return RedirectResponse(url="/banco?error=Enable+Banking+no+devolvio+URL", status_code=302)

    # Guardar state para verificarlo en el callback
    cuenta = _get_or_create_cuenta(db)
    cuenta.aspsp_name = aspsp
    cuenta.aspsp_country = country
    cuenta.oauth_state = estado
    cuenta.estado = "pendiente"
    cuenta.error = None
    db.commit()

    # Redirigir al banco
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/callback")
async def banco_callback(
    request: Request,
    db: Session = Depends(get_db),
    code: str = None,
    state: str = None,
    error: str = None,
    error_description: str = None,
):
    """Enable Banking redirige aquí tras la autorización del usuario en el banco."""
    cuenta = _get_or_create_cuenta(db)

    if error:
        cuenta.estado = "error"
        cuenta.error = f"{error}: {error_description or ''}"
        db.commit()
        err = (error_description or error).replace(" ", "+")[:200]
        return RedirectResponse(url=f"/banco?error={err}", status_code=302)

    if not code:
        cuenta.estado = "error"
        cuenta.error = "Callback sin código de autorización"
        db.commit()
        return RedirectResponse(url="/banco?error=Sin+codigo+de+autorizacion", status_code=302)

    # Verificar state anti-CSRF
    if state and cuenta.oauth_state and state != cuenta.oauth_state:
        cuenta.estado = "error"
        cuenta.error = "State OAuth no coincide"
        db.commit()
        return RedirectResponse(url="/banco?error=Estado+OAuth+invalido", status_code=302)

    try:
        session_data = eb.create_session(code)
    except Exception as e:
        cuenta.estado = "error"
        cuenta.error = str(e)
        db.commit()
        err = str(e).replace(" ", "+")[:200]
        return RedirectResponse(url=f"/banco?error={err}", status_code=302)

    session_id = session_data.get("session_id", "")
    accounts = session_data.get("accounts", [])

    if not session_id or not accounts:
        cuenta.estado = "error"
        cuenta.error = "Enable Banking no devolvió session_id o cuentas"
        db.commit()
        return RedirectResponse(url="/banco?error=Sin+sesion+o+cuentas", status_code=302)

    # Guardar la primera cuenta (la principal de ING)
    account_id = accounts[0]
    iban_display = None
    try:
        details = eb.get_account_details(account_id)
        iban = details.get("iban", "")
        iban_display = f"···· {iban[-4:]}" if len(iban) >= 4 else iban
    except Exception:
        pass

    cuenta.session_id = session_id
    cuenta.account_id = account_id
    cuenta.iban_display = iban_display
    cuenta.oauth_state = None
    cuenta.estado = "conectado"
    cuenta.error = None
    db.commit()

    return RedirectResponse(url="/banco?ok=1", status_code=302)


# ── Sincronización ────────────────────────────────────────────────────────────

@router.post("/sincronizar")
async def banco_sincronizar(request: Request, db: Session = Depends(get_db)):
    """Descarga transacciones de ING y crea Cobros nuevos en BD."""
    cuenta = _get_or_create_cuenta(db)

    if cuenta.estado != "conectado" or not cuenta.account_id:
        return RedirectResponse(url="/banco?error=Banco+no+conectado", status_code=302)

    try:
        transactions = eb.get_transactions(cuenta.account_id)
        candidatos = eb.filter_cobros(transactions)
    except Exception as e:
        cuenta.error = str(e)
        db.commit()
        err = str(e).replace(" ", "+")[:200]
        return RedirectResponse(url=f"/banco?error={err}", status_code=302)

    importados = 0
    omitidos = 0

    for tx in candidatos:
        # Fecha de contabilización
        fecha_str = tx.get("booking_date") or tx.get("value_date") or tx.get("transaction_date")
        if not fecha_str:
            continue
        try:
            fecha = date.fromisoformat(fecha_str)
        except ValueError:
            continue

        amount = tx["_amount"]
        description = tx.get("_description", "")[:255]
        mes_referencia = date(fecha.year, fecha.month, 1)

        # Deduplicación: misma fecha + importe + mes
        existe = db.query(Cobro).filter(
            Cobro.fecha == fecha,
            Cobro.importe == amount,
            Cobro.mes_referencia == mes_referencia,
        ).first()

        if existe:
            omitidos += 1
            continue

        cobro = Cobro(
            fecha=fecha,
            importe=amount,
            mes_referencia=mes_referencia,
            descripcion=f"ING · {description}" if description else "ING · carga automática",
        )
        db.add(cobro)
        importados += 1

    cuenta.ultimo_sync = datetime.utcnow()
    cuenta.error = None
    db.commit()

    return RedirectResponse(
        url=f"/banco?ok=2&importados={importados}&omitidos={omitidos}",
        status_code=302,
    )


# ── Desconectar ───────────────────────────────────────────────────────────────

@router.post("/desconectar")
async def banco_desconectar(db: Session = Depends(get_db)):
    """Revoca la sesión Enable Banking y resetea la conexión."""
    cuenta = _get_or_create_cuenta(db)

    if cuenta.session_id:
        eb.delete_session(cuenta.session_id)

    cuenta.session_id = None
    cuenta.account_id = None
    cuenta.iban_display = None
    cuenta.oauth_state = None
    cuenta.estado = "no_conectado"
    cuenta.error = None
    cuenta.ultimo_sync = None
    db.commit()

    return RedirectResponse(url="/banco", status_code=302)
