import asyncio

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
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def post(self, url, json):
            assert url == research.TAVILY_ENDPOINT
            assert json["api_key"] == "test-key"
            assert json["include_raw_content"] is False
            return FakeResponse()

    monkeypatch.setattr(research.httpx, "AsyncClient", FakeClient)
    body = research.SearchRequest(query="safe test", max_results=5)
    result = asyncio.run(research.web_search(body, None))
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
