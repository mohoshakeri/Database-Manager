from fastapi import FastAPI, Request, Response

from core.config import settings
from endpoints import auth, databases


def create_app() -> FastAPI:
    app: FastAPI = FastAPI(title="Database Manager", debug=settings.debug)

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next) -> Response:
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
        )
        return response

    app.include_router(auth.router)
    app.include_router(databases.router)
    return app
