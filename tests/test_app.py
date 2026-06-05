from fastapi.testclient import TestClient

from main import app
from core import security


def test_login_page_renders():
    client = TestClient(app)
    response = client.get("/login")

    assert response.status_code == 200
    assert "مدیریت دیتابیس" in response.text
    assert "/static/img/logo.png" in response.text
    assert "/static/img/favicon.ico" in response.text

def test_security_headers_are_set():
    client = TestClient(app)
    response = client.get("/login")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "same-origin"
    assert "default-src" in response.headers["content-security-policy"]


def test_logout_requires_valid_csrf_token(monkeypatch):
    monkeypatch.setattr(security.settings, "session_secret", "test-secret-with-enough-length-32-chars")
    monkeypatch.setattr(security.settings, "session_ttl_seconds", 60)
    monkeypatch.setattr(security.settings, "app_username", "admin")

    client = TestClient(app)
    session_token = security.create_session_token(username="admin")
    client.cookies.set(security.settings.session_cookie, session_token)

    missing = client.post("/logout", follow_redirects=False)
    assert missing.status_code == 403

    valid = client.post("/logout", data={"csrf_token": security.create_csrf_token(session_token)}, follow_redirects=False)
    assert valid.status_code == 303
