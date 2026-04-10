"""
Cliente Enable Banking para ControlGastosCRC.

Reutiliza la cuenta Enable Banking del proyecto MisCuentas
(mismo APP_ID y clave privada RSA).

Requiere en .app.env:
  EB_APP_ID=0315767f-1410-4d77-b420-510533c5b18b
  EB_PRIVATE_KEY_B64=<base64 del archivo .pem>
  EB_SANDBOX=false
  ING_FILTRO=COLEGIO,INSPIRED,CRC,RAMON   (opcional — sin filtro importa todo)
"""
import os
import time
from datetime import date, datetime, timedelta, timezone

import jwt  # PyJWT
import requests
from cryptography.hazmat.primitives.serialization import load_pem_private_key

EB_APP_ID = os.getenv("EB_APP_ID", "0315767f-1410-4d77-b420-510533c5b18b")
EB_KEY_PATH = os.getenv("EB_KEY_PATH", f"/app/keys/{EB_APP_ID}.pem")
EB_SANDBOX = os.getenv("EB_SANDBOX", "false").lower() == "true"
ING_FILTRO = os.getenv("ING_FILTRO", "")  # Keywords separados por coma

_API = (
    "https://api.sandbox.enablebanking.com"
    if EB_SANDBOX
    else "https://api.enablebanking.com"
)


def configured() -> bool:
    return bool(EB_APP_ID and os.path.exists(EB_KEY_PATH))


def _load_private_key():
    """Carga la clave privada RSA desde el archivo PEM."""
    if not os.path.exists(EB_KEY_PATH):
        raise ValueError(f"Clave privada no encontrada: {EB_KEY_PATH}")
    with open(EB_KEY_PATH, "rb") as f:
        return load_pem_private_key(f.read(), password=None)


def _make_jwt() -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": "enablebanking.com",
            "aud": "api.enablebanking.com",
            "iat": now,
            "exp": now + 3600,
        },
        _load_private_key(),
        algorithm="RS256",
        headers={"kid": EB_APP_ID},
    )


def _h() -> dict:
    return {"Authorization": f"Bearer {_make_jwt()}", "Content-Type": "application/json"}


# ── Bancos ────────────────────────────────────────────────────────────────────

def get_aspsps(country: str = "ES") -> list[dict]:
    """Lista de bancos disponibles (ASPSP) para un país."""
    r = requests.get(f"{_API}/aspsps", params={"country": country}, headers=_h(), timeout=30)
    r.raise_for_status()
    return r.json().get("aspsps", [])


# ── OAuth ─────────────────────────────────────────────────────────────────────

def start_auth(aspsp_name: str, aspsp_country: str, redirect_url: str, state: str) -> dict:
    """
    Inicia el flujo OAuth con el banco.
    Devuelve {url: str, authorization_id: str}.
    """
    valid_until = (datetime.now(timezone.utc) + timedelta(days=179)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    body = {
        "access": {"valid_until": valid_until},
        "aspsp": {"name": aspsp_name, "country": aspsp_country},
        "state": state,
        "redirect_url": redirect_url,
        "psu_type": "personal",
    }
    r = requests.post(f"{_API}/auth", json=body, headers=_h(), timeout=30)
    r.raise_for_status()
    return r.json()


def create_session(code: str) -> dict:
    """
    Intercambia el código de autorización por una sesión.
    Devuelve {session_id: str, accounts: list[str]}.
    """
    r = requests.post(f"{_API}/sessions", json={"code": code}, headers=_h(), timeout=30)
    r.raise_for_status()
    return r.json()


def delete_session(session_id: str) -> None:
    """Revoca una sesión (desconectar banco)."""
    try:
        requests.delete(f"{_API}/sessions/{session_id}", headers=_h(), timeout=30)
    except Exception:
        pass


# ── Cuentas ───────────────────────────────────────────────────────────────────

def get_account_details(account_id: str) -> dict:
    r = requests.get(f"{_API}/accounts/{account_id}/details", headers=_h(), timeout=30)
    r.raise_for_status()
    return r.json()


# ── Transacciones ─────────────────────────────────────────────────────────────

def get_transactions(account_id: str, date_from: date | None = None) -> list[dict]:
    """
    Descarga todas las transacciones con paginación automática.
    Por defecto busca los últimos 90 días (límite PSD2).
    """
    if date_from is None:
        date_from = date.today() - timedelta(days=90)

    params: dict = {"date_from": date_from.isoformat()}
    all_txs: list[dict] = []

    while True:
        r = requests.get(
            f"{_API}/accounts/{account_id}/transactions",
            params=params,
            headers=_h(),
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        all_txs.extend(data.get("transactions", []))
        cont = data.get("continuation_key")
        if not cont:
            break
        params["continuation_key"] = cont

    return all_txs


def _build_description(tx: dict) -> str:
    parts = []
    for field in [
        "remittance_information",
        "remittance_information_unstructured",
        "additional_information",
    ]:
        val = tx.get(field)
        if val:
            parts.extend(val if isinstance(val, list) else [str(val)])
    return " | ".join(parts)


def _matches_filter(description: str) -> bool:
    if not ING_FILTRO:
        return True  # Sin filtro → incluir todas las salidas
    keywords = [k.strip().upper() for k in ING_FILTRO.split(",") if k.strip()]
    return any(kw in description.upper() for kw in keywords)


def filter_cobros(transactions: list[dict]) -> list[dict]:
    """
    Filtra las transacciones para quedarse solo con los cargos
    que coincidan con el filtro de palabras clave (ING_FILTRO).
    Añade _description y _amount a cada transacción filtrada.
    """
    result = []
    for tx in transactions:
        # Solo cargos salientes (DBIT)
        cdi = tx.get("credit_debit_indicator", "")
        if cdi not in ("DBIT", ""):
            continue

        desc = _build_description(tx)
        if not _matches_filter(desc):
            continue

        from decimal import Decimal
        amount_raw = tx.get("transaction_amount", {}).get("amount", "0")
        amount = abs(Decimal(str(amount_raw)))

        tx["_description"] = desc
        tx["_amount"] = amount
        result.append(tx)

    return result
