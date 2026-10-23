"""Simple shared-token guard for single-user deployments.

For production, set ADAPTIVE_AI_API_TOKEN in the server's secret settings.
This is a starter guard, not a replacement for per-user identity or rate limiting.
"""
import hmac
import os
from fastapi import Request
from fastapi.responses import JSONResponse


async def protect_api_routes(request: Request, call_next):
    if not request.url.path.startswith("/v1/") or os.getenv("APP_ENV", "development").strip().lower() != "production":
        return await call_next(request)
    expected = os.getenv("ADAPTIVE_AI_API_TOKEN", "").strip()
    if not expected:
        return JSONResponse(status_code=503, content={"detail": "API access token is not configured"})
    authorization = request.headers.get("authorization", "")
    scheme, _, supplied = authorization.partition(" ")
    if scheme.lower() != "bearer" or not supplied or not hmac.compare_digest(supplied, expected):
        return JSONResponse(status_code=401, content={"detail": "Valid bearer token required"}, headers={"WWW-Authenticate": "Bearer"})
    return await call_next(request)
