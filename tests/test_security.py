import time

import pyotp

from core import security


def test_session_token_round_trip(monkeypatch):
    monkeypatch.setattr(security.settings, "session_secret", "test-secret-with-enough-length-32-chars")
    monkeypatch.setattr(security.settings, "session_ttl_seconds", 60)
    monkeypatch.setattr(security.settings, "app_username", "admin")

    token = security.create_session_token(username="admin")
    payload = security.read_session_token(token)

    assert payload is not None
    assert payload["sub"] == "admin"


def test_session_token_rejects_tampering(monkeypatch):
    monkeypatch.setattr(security.settings, "session_secret", "test-secret-with-enough-length-32-chars")
    monkeypatch.setattr(security.settings, "session_ttl_seconds", 60)
    monkeypatch.setattr(security.settings, "app_username", "admin")

    token = security.create_session_token(username="admin")
    tampered = token.replace(".", "x.", 1)

    assert security.read_session_token(tampered) is None


def test_session_token_rejects_expired_token(monkeypatch):
    monkeypatch.setattr(security.settings, "session_secret", "test-secret-with-enough-length-32-chars")
    monkeypatch.setattr(security.settings, "session_ttl_seconds", -1)
    monkeypatch.setattr(security.settings, "app_username", "admin")

    token = security.create_session_token(username="admin")
    time.sleep(1)

    assert security.read_session_token(token) is None


def test_password_hash_takes_precedence(monkeypatch):
    monkeypatch.setattr(security.settings, "app_password", "wrong")
    monkeypatch.setattr(
        security.settings,
        "app_password_hash",
        "2bb80d537b1da3e38bd30361aa855686bde0eacd7162fef6a25fe97bf527a25b",
    )

    assert security.verify_password("secret") is True
    assert security.verify_password("wrong") is False


def test_totp_verification(monkeypatch):
    secret = pyotp.random_base32()
    code = pyotp.TOTP(secret).now()
    monkeypatch.setattr(security.settings, "totp_secret", secret)

    assert security.verify_totp(code) is True
    assert security.verify_totp("000000") is False


def test_csrf_token_matches_session_token(monkeypatch):
    monkeypatch.setattr(security.settings, "session_secret", "test-secret-with-enough-length-32-chars")

    session_token = "session-token"
    csrf_token = security.create_csrf_token(session_token)

    assert security.verify_csrf_token(session_token, csrf_token) is True
    assert security.verify_csrf_token(session_token, "wrong") is False


def test_session_secret_must_be_strong(monkeypatch):
    monkeypatch.setattr(security.settings, "session_secret", "short")

    try:
        security.create_csrf_token("session-token")
    except RuntimeError as error:
        assert "BACKUP_HUB_SESSION_SECRET" in str(error)
    else:
        raise AssertionError("weak session secret was accepted")
