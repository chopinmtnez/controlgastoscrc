import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Request
from fastapi.responses import RedirectResponse
import hashlib
import hmac

from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production-32b")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 8
COOKIE_NAME = "cgcrc_token"

APP_USERNAME = os.getenv("APP_USERNAME", "alberto")
APP_PASSWORD_HASH = os.getenv("APP_PASSWORD_HASH", "")

PUBLIC_PATHS = {"/login", "/static"}


def _pbkdf2(password: str, salt: str) -> str:
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260000)
    return key.hex()


def hash_password(password: str) -> str:
    """Genera hash en formato 'salt:hexhash' (sin $ para compatibilidad Docker)."""
    import secrets
    salt = secrets.token_hex(16)
    return f"{salt}:{_pbkdf2(password, salt)}"


def verify_password(plain: str, hashed: str) -> bool:
    try:
        salt, stored_key = hashed.split(":", 1)
        return hmac.compare_digest(_pbkdf2(plain, salt), stored_key)
    except Exception:
        return False


def create_access_token(username: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": username, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path == "/login" or path.startswith("/static"):
            return await call_next(request)
        token = request.cookies.get(COOKIE_NAME)
        if not token or not decode_token(token):
            return RedirectResponse(url="/login", status_code=302)
        return await call_next(request)
