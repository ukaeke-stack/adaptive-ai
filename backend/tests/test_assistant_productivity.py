from fastapi.testclient import TestClient
from app.main import app
from app.api.assistant_productivity import _validate_steps

client = TestClient(app)


def test_workflow_validator_allows_only_safe_step_types():
    assert _validate_steps([{"type": "draft_message", "input": "Hello"}])[0]["type"] == "draft_message"


def test_workflow_validator_rejects_arbitrary_actions():
    from fastapi import HTTPException
    import pytest
    with pytest.raises(HTTPException):
        _validate_steps([{"type": "execute_shell", "input": "rm -rf /"}])


def test_workflow_validator_rejects_unrecognized_fields():
    from fastapi import HTTPException
    import pytest
    with pytest.raises(HTTPException):
        _validate_steps([{"type": "draft_message", "input": "Hi", "send_now": True}])


def test_document_tools_require_authentication_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    response = client.post("/v1/assistant/documents/analyze", json={"text": "A short text.", "task": "count_words"})
    assert response.status_code == 401


def test_productivity_routes_are_registered():
    schema = client.get("/openapi.json").json()
    assert "/v1/assistant/reminders" in schema["paths"]
    assert "/v1/assistant/documents/analyze" in schema["paths"]
    assert "/v1/assistant/documents/extract-pdf" in schema["paths"]
    assert "/v1/assistant/workflows/{workflow_id}/preview" in schema["paths"]
