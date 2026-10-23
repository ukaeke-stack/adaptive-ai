from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_conversation_can_be_created_listed_and_deleted(monkeypatch, tmp_path):
    monkeypatch.setenv("ADAPTIVE_AI_DB_PATH", str(tmp_path / "memory.db"))
    created = client.post("/v1/conversations")
    assert created.status_code == 200
    conversation_id = created.json()["id"]

    listed = client.get("/v1/conversations")
    assert listed.status_code == 200
    assert any(item["id"] == conversation_id for item in listed.json()["conversations"])

    messages = client.get(f"/v1/conversations/{conversation_id}/messages")
    assert messages.status_code == 200
    assert messages.json()["messages"] == []

    deleted = client.delete(f"/v1/conversations/{conversation_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get(f"/v1/conversations/{conversation_id}/messages").status_code == 404


def test_unknown_conversation_returns_404(monkeypatch, tmp_path):
    monkeypatch.setenv("ADAPTIVE_AI_DB_PATH", str(tmp_path / "memory.db"))
    assert client.get("/v1/conversations/not-a-real-id/messages").status_code == 404
    assert client.delete("/v1/conversations/not-a-real-id").status_code == 404
