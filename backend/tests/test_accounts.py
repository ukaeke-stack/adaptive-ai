import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.memory import store


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ADAPTIVE_AI_DB_PATH", str(tmp_path / "accounts.sqlite3"))
    monkeypatch.setenv("ADAPTIVE_AI_OWNER_EMAIL", "ukaeke@gmail.com")
    monkeypatch.setenv("ADAPTIVE_AI_OWNER_NAME", "Uka Eke Kalu")
    monkeypatch.setenv("ADAPTIVE_AI_OWNER_PHONE", "07036105354")
    monkeypatch.setenv("ADAPTIVE_AI_OWNER_ENROLLMENT_SECRET", "test-enrollment-secret-long-enough-123456")
    store._engine.cache_clear()
    return TestClient(app)


def test_owner_enrollment_session_login_recovery_and_logout(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    recovery = "a" * 64
    enroll = client.post("/v1/auth/enroll-owner", json={
        "email": "ukaeke@gmail.com",
        "full_name": "Uka Eke Kalu",
        "enrollment_secret": "test-enrollment-secret-long-enough-123456",
        "password": "strong-owner-password-123",
        "recovery_code": recovery,
    })
    assert enroll.status_code == 200
    assert enroll.json()["user"]["role"] == "owner"
    assert "adaptive_ai_session" in enroll.cookies

    assert client.get("/v1/auth/me").json()["authenticated"] is True
    duplicate = client.post("/v1/auth/enroll-owner", json={
        "email": "ukaeke@gmail.com",
        "full_name": "Uka Eke Kalu",
        "enrollment_secret": "test-enrollment-secret-long-enough-123456",
        "password": "strong-owner-password-456",
        "recovery_code": "b" * 64,
    })
    assert duplicate.status_code == 409

    logout = client.post("/v1/auth/logout", json={})
    assert logout.status_code == 200
    assert client.get("/v1/auth/me").json()["authenticated"] is False

    login = client.post("/v1/auth/login", json={
        "email": "ukaeke@gmail.com", "password": "strong-owner-password-123"
    })
    assert login.status_code == 200
    assert client.get("/v1/auth/me").json()["authenticated"] is True

    reset = client.post("/v1/auth/recover", json={
        "email": "ukaeke@gmail.com", "recovery_code": recovery,
        "new_password": "another-strong-password-456",
        "new_recovery_code": "c" * 64,
    })
    assert reset.status_code == 200
    assert client.get("/v1/auth/me").json()["authenticated"] is False

    assert client.post("/v1/auth/login", json={
        "email": "ukaeke@gmail.com", "password": "strong-owner-password-123"
    }).status_code == 401
    assert client.post("/v1/auth/login", json={
        "email": "ukaeke@gmail.com", "password": "another-strong-password-456"
    }).status_code == 200
    store._engine.cache_clear()


def test_owner_enrollment_rejects_wrong_secret(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    response = client.post("/v1/auth/enroll-owner", json={
        "email": "ukaeke@gmail.com",
        "full_name": "Uka Eke Kalu",
        "enrollment_secret": "wrong-enrollment-secret-long-enough-123",
        "password": "strong-owner-password-123",
        "recovery_code": "a" * 64,
    })
    assert response.status_code == 403
    store._engine.cache_clear()
