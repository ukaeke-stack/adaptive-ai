from fastapi.testclient import TestClient
from app.main import app
import app.security.auth as auth_module

client = TestClient(app)


def _production(monkeypatch, token="test-secret-token"):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADAPTIVE_AI_API_TOKEN", token)
    with auth_module._rate_lock:
        auth_module._requests_by_client.clear()


def test_production_api_fails_closed_without_configured_token(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("ADAPTIVE_AI_API_TOKEN", raising=False)
    response = client.get("/v1/capabilities")
    assert response.status_code == 401
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_production_api_rejects_missing_token(monkeypatch):
    _production(monkeypatch)
    response = client.get("/v1/capabilities")
    assert response.status_code == 401


def test_production_api_accepts_correct_bearer_token(monkeypatch):
    _production(monkeypatch)
    response = client.get("/v1/capabilities", headers={"Authorization": "Bearer test-secret-token"})
    assert response.status_code == 200
    assert response.headers["X-Frame-Options"] == "DENY"


def test_health_remains_available_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("ADAPTIVE_AI_API_TOKEN", raising=False)
    response = client.get("/health")
    assert response.status_code == 200


def test_production_api_rate_limits_after_configured_threshold(monkeypatch):
    _production(monkeypatch)
    monkeypatch.setattr(auth_module, "_RATE_LIMIT", 2)
    headers = {"Authorization": "Bearer test-secret-token"}
    assert client.get("/v1/capabilities", headers=headers).status_code == 200
    assert client.get("/v1/capabilities", headers=headers).status_code == 200
    limited = client.get("/v1/capabilities", headers=headers)
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "60"


def test_production_api_rejects_oversized_declared_body(monkeypatch):
    _production(monkeypatch)
    response = client.post(
        "/v1/chat",
        headers={"Authorization": "Bearer test-secret-token", "Content-Length": str(65 * 1024)},
        content=b"x" * (65 * 1024),
    )
    assert response.status_code == 413


def test_security_headers_are_added_to_public_health(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
