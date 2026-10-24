import os

# Keep the test client isolated from deployment settings; production auth is tested below.
os.environ["APP_ENV"] = "test"

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root_returns_service_info():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Adaptive AI API"
    assert data["status"] == "online"
    assert data["health"] == "/health"
    assert data["docs"] == "/docs"


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "adaptive-ai-backend",
        "milestone": "1",
    }


def test_capabilities_only_lists_calculator():
    response = client.get("/v1/capabilities")
    assert response.status_code == 200
    assert response.json()["capabilities"][0]["name"] == "calculator"


def test_calculator_adds_numbers():
    response = client.post("/v1/tools/execute", json={
        "name": "calculator", "arguments": {"operation": "add", "a": 2, "b": 3}
    })
    assert response.status_code == 200
    assert response.json()["result"] == 5.0


def test_unknown_tool_is_rejected():
    response = client.post("/v1/tools/execute", json={
        "name": "run_python", "arguments": {"code": "print('unsafe')"}
    })
    assert response.status_code == 404


def test_division_by_zero_is_rejected():
    response = client.post("/v1/tools/execute", json={
        "name": "calculator", "arguments": {"operation": "divide", "a": 10, "b": 0}
    })
    assert response.status_code == 422


def test_unsupported_operation_is_rejected():
    response = client.post("/v1/tools/execute", json={
        "name": "calculator", "arguments": {"operation": "power", "a": 2, "b": 8}
    })
    assert response.status_code == 422


def test_wrong_argument_shape_is_rejected():
    response = client.post("/v1/tools/execute", json={
        "name": "calculator", "arguments": {"operation": "add", "a": 1}
    })
    assert response.status_code == 422


def test_production_api_requires_bearer_token(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADAPTIVE_AI_API_TOKEN", "test-secret-token")
    assert client.get("/v1/capabilities").status_code == 401
    assert client.get("/v1/capabilities", headers={"Authorization": "Bearer wrong"}).status_code == 401
    response = client.get(
        "/v1/capabilities",
        headers={"Authorization": "Bearer test-secret-token"},
    )
    assert response.status_code == 200


def test_production_api_fails_closed_when_token_missing(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("ADAPTIVE_AI_API_TOKEN", raising=False)
    response = client.get("/v1/capabilities")
    assert response.status_code == 503


def test_omitted_app_env_defaults_to_production(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("ADAPTIVE_AI_API_TOKEN", "test-secret-token")
    assert client.get("/v1/capabilities").status_code == 401



def test_conversation_memory_round_trip_uses_local_sqlite_in_tests(monkeypatch, tmp_path):
    from app.memory import store

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ADAPTIVE_AI_DB_PATH", str(tmp_path / "test-memory.sqlite3"))
    store._engine.cache_clear()
    try:
        conversation = store.create_conversation()
        assert store.conversation_exists(conversation["id"])
        store.add_message(conversation["id"], "user", "hello")
        store.add_message(conversation["id"], "assistant", "world")
        assert store.get_messages(conversation["id"]) == [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
        assert any(item["id"] == conversation["id"] for item in store.list_conversations())
        assert store.delete_conversation(conversation["id"])
        assert not store.conversation_exists(conversation["id"])
    finally:
        store._engine.cache_clear()
