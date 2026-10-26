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


def test_agent_calculator_rejects_complex_results():
    with pytest.raises(ValueError):
        _calculate("(-1) ** 0.5")


def test_agent_calculator_limits_exponent():
    with pytest.raises(ValueError):
        _calculate("2 ** 100")



def test_agent_extracts_contacts_from_supplied_text():
    result = _execute_step({"action": "extract_contacts", "input": "Email test@example.com or call +234 801 234 5678"})
    assert result["status"] == "succeeded"
    assert "test@example.com" in result["emails"]
    assert result["phone_numbers"]


def test_agent_extracts_dates_from_supplied_text():
    result = _execute_step({"action": "extract_dates", "input": "Deadline is 2026-11-03 and review is Dec 4, 2026."})
    assert result["status"] == "succeeded"
    assert "2026-11-03" in result["dates"]
    assert "Dec 4, 2026" in result["dates"]


def test_agent_summary_labels_its_deterministic_method():
    result = _execute_step({"action": "summarize_text", "input": "First sentence. Second sentence. Third sentence."})
    assert result["status"] == "succeeded"
    assert result["method"] == "extractive sentence selection"
    assert "First sentence." in result["summary"]

def test_agent_draft_never_sends_message():
    result = _execute_step({"action": "draft_message", "input": "Hello"})
    assert result["status"] == "succeeded"
    assert result["sent"] is False
    assert result["draft"] == "Hello"


def test_agent_routes_are_registered_and_protected(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    schema = client.get("/openapi.json").json()
    assert "/v1/agent/tasks" in schema["paths"]
    assert "/v1/agent/tasks/{task_id}/run" in schema["paths"]
    response = client.post("/v1/agent/tasks", json={"goal": "Count words", "context": {"text": "one two"}})
    assert response.status_code == 401


def test_agent_workspace_is_served():
    response = client.get("/app/agent.html")
    assert response.status_code == 200
    assert "Norah Agent Desk" in response.text
    assert 'id="extractPdf"' in response.text
    assert 'id="ocrPdf"' in response.text
    assert "scheduleReminder" in response.text
    assert "Local Android reminder notification scheduled" in response.text



def test_agent_plans_multiple_supported_actions_in_order():
    plan = _plan("Count words and extract contacts", {
        "text": "Contact test@example.com. One two three."
    })
    assert [step["action"] for step in plan] == ["count_words", "extract_contacts"]
    assert [step["id"] for step in plan] == ["step-1", "step-2"]
    assert all(step["input"] == "Contact test@example.com. One two three." for step in plan)


def test_agent_does_not_partially_plan_mixed_unsupported_goals():
    plan = _plan("Count words and send money to my supplier", {"text": "one two"})
    assert len(plan) == 1
    assert plan[0]["action"] == "unsupported_goal"
