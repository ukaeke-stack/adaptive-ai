"""Production API guard with bounded abuse protection.

The shared bearer token is only suitable for a controlled single-user deployment.
The in-process rate limiter is a defence-in-depth measure, not a substitute for
account identity or a distributed rate limiter at the edge.
"""
from collections import deque
import hmac
import os
import threading
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from app.security.sessions import current_user

_RATE_WINDOW_SECONDS = 60.0
_RATE_LIMIT = 60
_MAX_BODY_BYTES = 64 * 1024
_MAX_TRACKED_CLIENTS = 5000
_requests_by_client: dict[str, deque[float]] = {}
_rate_lock = threading.Lock()


def _client_key(request: Request) -> str:
    # Do not trust arbitrary X-Forwarded-For headers. Use the address exposed
    # by the ASGI server until a trusted-proxy configuration is explicitly set.
    return request.client.host if request.client else "unknown"


def _is_rate_limited(client_key: str, now: float) -> bool:
    with _rate_lock:
        recent = _requests_by_client.get(client_key)
        if recent is None:
            if len(_requests_by_client) >= _MAX_TRACKED_CLIENTS:
                _requests_by_client.pop(next(iter(_requests_by_client)))
            recent = deque()
            _requests_by_client[client_key] = recent
        cutoff = now - _RATE_WINDOW_SECONDS
        while recent and recent[0] <= cutoff:
            recent.popleft()
        if len(recent) >= _RATE_LIMIT:
            return True
        recent.append(now)
        return False


def _security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), payment=()")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


async def protect_api_routes(request: Request, call_next):
    is_api = request.url.path.startswith("/v1/")
    app_env = os.getenv("APP_ENV", "production").strip().lower()

    is_auth_endpoint = request.url.path.startswith("/v1/auth/")
    if is_api and app_env == "production" and not is_auth_endpoint:
        # Browser users authenticate with an HTTP-only server-managed session.
        # Keep bearer-token access for existing controlled API clients during migration.
        session_user = current_user(request)
        authorization = request.headers.get("authorization", "")
        scheme, _, supplied = authorization.partition(" ")
        expected = os.getenv("ADAPTIVE_AI_API_TOKEN", "").strip()
        bearer_valid = bool(expected and scheme.lower() == "bearer" and supplied and hmac.compare_digest(supplied, expected))
        if not session_user and not bearer_valid:
            return _security_headers(JSONResponse(
                status_code=401,
                content={"detail": "Please sign in to Adaptive AI."},
                headers={"WWW-Authenticate": "Bearer"},
            ))
        if session_user and request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
                return _security_headers(JSONResponse(status_code=403, content={"detail": "Cross-origin request blocked."}))

        raw_length = request.headers.get("content-length")
        if raw_length:
            try:
                body_length = int(raw_length)
            except ValueError:
                return _security_headers(JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"}))
            if body_length < 0 or body_length > _MAX_BODY_BYTES:
                return _security_headers(JSONResponse(status_code=413, content={"detail": "Request body too large"}))

        if _is_rate_limited(_client_key(request), time.monotonic()):
            return _security_headers(JSONResponse(
                status_code=429,
                content={"detail": "Too many API requests. Please wait and retry."},
                headers={"Retry-After": str(int(_RATE_WINDOW_SECONDS))},
            ))

    response = await call_next(request)
    return _security_headers(response)
