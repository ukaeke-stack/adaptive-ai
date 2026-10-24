"""Simple shared-token guard for single-user deployments.

Production is the safe default: an omitted APP_ENV must never silently expose /v1.
This is a starter guard, not a replacement for per-user identity or rate limiting.
"""
import hmac
import os

from fastapi import Request
from fastapi.responses import JSONResponse


async def protect_api_routes(request: Request, call_next):
    app_env = os.getenv("APP_ENV", "production").strip().lower()
    if not request.url.path.startswith("/v1/") or app_env != "production":
        return await call_next(request)
    expected = os.getenv("ADAPTIVE_AI_API_TOKEN", "").strip()
    if not expected:
        return JSONResponse(status_code=503, content={"detail": "API access token is not configured"})
    authorization = request.headers.get("authorization", "")
    scheme, _, supplied = authorization.partition(" ")
    if scheme.lower() != "bearer" or not supplied or not hmac.compare_digest(supplied, expected):
        return JSONResponse(
            status_code=401,
            content={"detail": "Valid bearer token required"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await call_next(request)
