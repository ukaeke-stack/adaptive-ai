"""Authenticated, read-only web research through an explicitly configured search provider."""
from __future__ import annotations

import os
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.security.sessions import require_user

router = APIRouter(prefix="/v1/research", tags=["web research"])
TAVILY_ENDPOINT = "https://api.tavily.com/search"


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=2, max_length=1000)
    max_results: int = Field(default=5, ge=1, le=10)


def _configured_key() -> str:
    key = os.getenv("TAVILY_API_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="Web research is not configured. The service administrator must set TAVILY_API_KEY.")
    return key


@router.get("/status")
def research_status(request: Request):
    require_user(request)
    return {
        "provider": "Tavily",
        "configured": bool(os.getenv("TAVILY_API_KEY", "").strip()),
        "mode": "read_only_search",
        "external_actions": False,
    }


def search_for_agent(query: str, max_results: int = 5) -> dict:
    """Read-only search helper shared by the authenticated API and task executor."""
    key = _configured_key()
    query = query.strip() if isinstance(query, str) else ""
    if len(query) < 2 or len(query) > 1000:
        raise HTTPException(status_code=422, detail="Search query must contain 2 to 1000 characters.")
    if not 1 <= max_results <= 10:
        raise HTTPException(status_code=422, detail="max_results must be between 1 and 10.")
    payload = {
        "api_key": key,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        "include_answer": False,
        "include_raw_content": False,
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0), follow_redirects=False) as client:
            response = client.post(TAVILY_ENDPOINT, json=payload)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="The search provider timed out. Try again.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="The search provider could not be reached.") from exc
    if response.status_code in {401, 403}:
        raise HTTPException(status_code=503, detail="The configured search provider credentials were rejected.")
    if response.status_code == 429:
        raise HTTPException(status_code=429, detail="The search provider rate limit was reached. Try again later.")
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="The search provider returned an error.")
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="The search provider returned an invalid response.") from exc
    raw_results = data.get("results", []) if isinstance(data, dict) else []
    results = []
    for item in raw_results[:max_results]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", ""))[:2000]
        parsed = urlparse(url)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname:
            continue
        results.append({
            "title": str(item.get("title", ""))[:300],
            "url": url,
            "snippet": str(item.get("content", ""))[:2000],
            "score": item.get("score") if isinstance(item.get("score"), (int, float)) else None,
        })
    return {
        "provider": "Tavily",
        "query": query,
        "results": results,
        "result_count": len(results),
        "read_only": True,
        "note": "Search results may be incomplete or outdated. Open sources to verify important claims.",
    }


@router.post("/search")
def web_search(body: SearchRequest, request: Request):
    require_user(request)
    return search_for_agent(body.query, body.max_results)
