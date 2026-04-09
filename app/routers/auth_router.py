from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from auth import APP_PASSWORD_HASH, APP_USERNAME, COOKIE_NAME, create_access_token, verify_password

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == APP_USERNAME and verify_password(password, APP_PASSWORD_HASH):
        token = create_access_token(username)
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=8 * 3600,
        )
        return response
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": "Usuario o contraseña incorrectos"}, status_code=401
    )


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response
