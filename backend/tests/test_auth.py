from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_production_api_fails_closed_without_configured_token(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("ADAPTIVE_AI_API_TOKEN", raising=False)
    response = client.get("/v1/capabilities")
    assert response.status_code == 503


def test_production_api_rejects_missing_token(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADAPTIVE_AI_API_TOKEN", "test-secret-token")
    response = client.get("/v1/capabilities")
    assert response.status_code == 401


def test_production_api_accepts_correct_bearer_token(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADAPTIVE_AI_API_TOKEN", "test-secret-token")
    response = client.get("/v1/capabilities", headers={"Authorization": "Bearer test-secret-token"})
    assert response.status_code == 200


def test_health_remains_available_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("ADAPTIVE_AI_API_TOKEN", raising=False)
    response = client.get("/health")
    assert response.status_code == 200
