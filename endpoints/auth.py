from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from core.config import settings
from dependencies.auth import require_csrf
from core.security import create_session_token, verify_password, verify_totp

router: APIRouter = APIRouter(tags=["Auth"])
templates: Jinja2Templates = Jinja2Templates(directory="templates")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"settings": settings, "error": ""})


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    totp_code: str = Form(""),
) -> Response:
    if username != settings.app_username or not verify_password(password) or not verify_totp(totp_code):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"settings": settings, "error": "Invalid username, password, or TOTP code."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    response: RedirectResponse = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=settings.session_cookie,
        value=create_session_token(username=username),
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )
    return response


@router.post("/logout")
def logout(_csrf: None = Depends(require_csrf)) -> RedirectResponse:
    response: RedirectResponse = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(settings.session_cookie)
    return response
