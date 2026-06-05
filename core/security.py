import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

import pyotp

from core.config import settings


def verify_password(password: str) -> bool:
    if settings.app_password_hash:
        digest: str = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return secrets.compare_digest(digest, settings.app_password_hash)
    return secrets.compare_digest(password, settings.app_password)


def verify_totp(code: str) -> bool:
    if not settings.totp_secret:
        return True
    totp: pyotp.TOTP = pyotp.TOTP(settings.totp_secret)
    return bool(totp.verify(code.strip(), valid_window=1))


def create_session_token(username: str) -> str:
    now: int = int(time.time())
    payload: dict[str, Any] = {
        "sub": username,
        "iat": now,
        "exp": now + settings.session_ttl_seconds,
        "nonce": secrets.token_urlsafe(16),
    }
    body: bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    encoded: str = base64.urlsafe_b64encode(body).decode("ascii").rstrip("=")
    signature: str = _sign(encoded)
    return f"{encoded}.{signature}"


def create_csrf_token(session_token: str) -> str:
    return _sign(f"csrf:{session_token}")


def verify_csrf_token(session_token: str | None, csrf_token: str | None) -> bool:
    if not session_token or not csrf_token:
        return False
    expected: str = create_csrf_token(session_token)
    return secrets.compare_digest(expected, csrf_token)


def read_session_token(token: str | None) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    encoded, signature = token.rsplit(".", 1)
    if not secrets.compare_digest(_sign(encoded), signature):
        return None
    try:
        padded: str = encoded + ("=" * (-len(encoded) % 4))
        payload: dict[str, Any] = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    if payload.get("sub") != settings.app_username:
        return None
    return payload


def _sign(value: str) -> str:
    if len(settings.session_secret) < 32:
        raise RuntimeError("BACKUP_HUB_SESSION_SECRET must be at least 32 characters")
    secret: bytes = settings.session_secret.encode("utf-8")
    digest: bytes = hmac.new(secret, value.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
