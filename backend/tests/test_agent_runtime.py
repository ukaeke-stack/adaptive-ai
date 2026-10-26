from fastapi.testclient import TestClient
from fastapi import HTTPException
import pytest

from app.main import app
from app.api.agent_runtime import _calculate, _plan, _execute_step

client = TestClient(app)


def test_agent_plans_supported_word_count_with_context():
    plan = _plan("Count words in this text", {"text": "one two three"})
    assert plan[0]["action"] == "count_words"
    assert plan[0]["input"] == "one two three"


def test_agent_blocks_unsupported_goal_instead_of_simulating():
    plan = _plan("Send money to my supplier", {})
    assert plan[0]["action"] == "unsupported_goal"
    assert plan[0]["status"] == "blocked"


def test_agent_calculator_allows_basic_math():
    assert _calculate("1250 * 4 + 300") == 5300
    assert _calculate("(9 - 3) / 2") == 3


def test_agent_calculator_rejects_code_execution():
    with pytest.raises((ValueError, SyntaxError)):
        _calculate("__import__('os').system('echo unsafe')")


def test_agent_calculator_limits_exponent():
    with pytest.raises(ValueError):
        _calculate("2 ** 100")


def test_agent_draft_never_sends_message():
    result = _execute_step({"action": "draft_message", "input": "Hello"})
    assert result["status"] == "succeeded"
    assert result["sent"] is False
    assert result["draft"] == "Hello"


def test_agent_routes_are_registered_and_protected():
    schema = client.get("/openapi.json").json()
    assert "/v1/agent/tasks" in schema["paths"]
    assert "/v1/agent/tasks/{task_id}/run" in schema["paths"]
    response = client.post("/v1/agent/tasks", json={"goal": "Count words", "context": {"text": "one two"}})
    assert response.status_code == 401


def test_agent_workspace_is_served():
    response = client.get("/app/agent.html")
    assert response.status_code == 200
    assert "Norah Agent Desk" in response.text
