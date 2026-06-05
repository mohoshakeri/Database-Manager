from fastapi import Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from core.config import settings
from core.security import create_csrf_token, read_session_token, verify_csrf_token


def require_user(request: Request) -> str | RedirectResponse:
    token: str | None = request.cookies.get(settings.session_cookie)
    session: dict[str, object] | None = read_session_token(token)
    if not session or not token:
        return RedirectResponse(url="/login", status_code=303)
    request.state.csrf_token = create_csrf_token(token)
    return str(session["sub"])


def require_csrf(request: Request, csrf_token: str = Form("")) -> None:
    token: str | None = request.cookies.get(settings.session_cookie)
    if not read_session_token(token):
        return
    if not verify_csrf_token(token, csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")
