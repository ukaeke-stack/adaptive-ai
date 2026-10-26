import pytest
from fastapi import HTTPException

from app.api import research


def test_research_status_never_exposes_provider_secret(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "server-secret-value")
    monkeypatch.setattr(research, "require_user", lambda request: {"id": "user-1"})
    result = research.research_status(None)
    assert result["configured"] is True
    assert "server-secret-value" not in str(result)
    assert result["external_actions"] is False


def test_search_requires_provider_configuration(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with pytest.raises(HTTPException) as error:
        research._configured_key()
    assert error.value.status_code == 503


def test_search_sanitizes_provider_results(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setattr(research, "require_user", lambda request: {"id": "user-1"})

    class FakeResponse:
        status_code = 200
        def json(self):
            return {"results": [
                {"title": "Good result", "url": "https://example.com/a", "content": "Useful snippet", "score": 0.9},
                {"title": "Bad URL", "url": "javascript:alert(1)", "content": "Ignore"},
            ]}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def post(self, url, json):
            assert url == research.TAVILY_ENDPOINT
            assert json["api_key"] == "test-key"
            assert json["include_raw_content"] is False
            return FakeResponse()

    monkeypatch.setattr(research.httpx, "Client", FakeClient)
    body = research.SearchRequest(query="safe test", max_results=5)
    result = research.web_search(body, None)
    assert result["result_count"] == 1
    assert result["results"][0]["url"] == "https://example.com/a"
    assert result["read_only"] is True


def test_search_rejects_unknown_request_fields():
    with pytest.raises(Exception):
        research.SearchRequest(query="valid query", unexpected="secret")


def test_research_routes_are_registered():
    from app.main import app
    paths = app.openapi()["paths"]
    assert "/v1/research/status" in paths
    assert "/v1/research/search" in paths


def test_agent_can_plan_read_only_web_search():
    from app.api.agent_runtime import _plan
    plan = _plan("Research the latest Android notification guidance", {})
    assert plan[0]["action"] == "web_search"
    assert plan[0]["external_side_effect"] is False


def test_agent_search_action_reports_missing_provider_key(monkeypatch):
    from app.api import agent_runtime
    monkeypatch.setattr(agent_runtime, "search_for_agent",
                        lambda query, max_results: (_ for _ in ()).throw(HTTPException(status_code=503, detail="not configured")))
    result = agent_runtime._execute_step({"action": "web_search", "query": "test", "max_results": 5})
    assert result["status"] == "failed"
    assert result["message"] == "not configured"
