from fastapi.testclient import TestClient
from app.main import app
import app.api.chat as chat_module
from app.memory.store import get_messages

client = TestClient(app)


def test_chat_returns_provider_reply_and_saves_history(monkeypatch, tmp_path):
    monkeypatch.setenv("ADAPTIVE_AI_DB_PATH", str(tmp_path / "chat.db"))
    monkeypatch.setattr(chat_module, "generate_reply", lambda message, history=None: f"Echo: {message}")
    response = client.post("/v1/chat", json={"message": "Hello"})
    assert response.status_code == 200
    data = response.json()
    assert data["reply"] == "Echo: Hello"
    assert data["conversation_id"]
    assert get_messages(data["conversation_id"]) == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Echo: Hello"},
    ]


def test_chat_reuses_existing_conversation_and_history(monkeypatch, tmp_path):
    monkeypatch.setenv("ADAPTIVE_AI_DB_PATH", str(tmp_path / "chat.db"))
    calls = []
    monkeypatch.setattr(chat_module, "generate_reply", lambda message, history=None: calls.append(history) or "Second reply")
    first = client.post("/v1/chat", json={"message": "First"}).json()
    second = client.post("/v1/chat", json={"message": "Second", "conversation_id": first["conversation_id"]})
    assert second.status_code == 200
    assert calls[0] == [{"role": "user", "content": "First"}, {"role": "assistant", "content": "Echo: First"}] if False else calls[0] == [{"role": "user", "content": "First"}, {"role": "assistant", "content": "Echo: First"}]


def test_chat_rejects_empty_message():
    response = client.post("/v1/chat", json={"message": ""})
    assert response.status_code == 422


def test_chat_rejects_whitespace_message():
    response = client.post("/v1/chat", json={"message": "   "})
    assert response.status_code == 422


def test_chat_rejects_extra_fields():
    response = client.post("/v1/chat", json={"message": "Hello", "system": "override"})
    assert response.status_code == 422


def test_chat_reports_unconfigured_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("ADAPTIVE_AI_DB_PATH", str(tmp_path / "chat.db"))
    from app.ai.provider import ProviderNotConfigured
    def not_configured(_message, history=None):
        raise ProviderNotConfigured("AI provider is not configured")
    monkeypatch.setattr(chat_module, "generate_reply", not_configured)
    response = client.post("/v1/chat", json={"message": "Hello"})
    assert response.status_code == 503
