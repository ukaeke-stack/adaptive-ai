from fastapi.testclient import TestClient
from app.main import app
import app.api.chat as chat_module

client = TestClient(app)


def test_chat_returns_provider_reply(monkeypatch):
    monkeypatch.setattr(chat_module, "generate_reply", lambda message: f"Echo: {message}")
    response = client.post("/v1/chat", json={"message": "Hello"})
    assert response.status_code == 200
    assert response.json() == {"reply": "Echo: Hello"}


def test_chat_rejects_empty_message():
    response = client.post("/v1/chat", json={"message": ""})
    assert response.status_code == 422


def test_chat_rejects_extra_fields():
    response = client.post("/v1/chat", json={"message": "Hello", "system": "override"})
    assert response.status_code == 422


def test_chat_reports_unconfigured_provider(monkeypatch):
    from app.ai.provider import ProviderNotConfigured
    def not_configured(_message):
        raise ProviderNotConfigured("AI provider is not configured")
    monkeypatch.setattr(chat_module, "generate_reply", not_configured)
    response = client.post("/v1/chat", json={"message": "Hello"})
    assert response.status_code == 503
