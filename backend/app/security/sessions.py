"""Cookie-session authentication for the Adaptive AI owner account.

The initial deployment is owner-only. Owner privileges are provisioned only with
an out-of-band enrollment secret configured in the hosting environment.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import secrets
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import text

from app.memory.store import _ready_engine

router = APIRouter(prefix="/v1/auth", tags=["account"])
COOKIE_NAME = "adaptive_ai_session"
SESSION_HOURS = 12


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(value: datetime) -> str:
    return value.isoformat()


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$" + salt.hex() + "$" + derived.hex()


def _verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = encoded.split("$", 2)
        if scheme != "scrypt":
            return False
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _cookie(response: Response, token: str) -> None:
    production = os.getenv("APP_ENV", "production").strip().lower() == "production"
    response.set_cookie(
        COOKIE_NAME, token, max_age=SESSION_HOURS * 3600, httponly=True,
        secure=production, samesite="strict", path="/",
    )


def _clear_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True,
                           secure=os.getenv("APP_ENV", "production").strip().lower() == "production",
                           samesite="strict")


def current_user(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE_NAME, "")
    if not token or len(token) < 40:
        return None
    engine = _ready_engine()
    now = _stamp(_now())
    with engine.begin() as connection:
        row = connection.execute(text("""
            SELECT u.id, u.email, u.full_name, u.phone, u.role, u.phone_verified
            FROM adaptive_sessions s JOIN adaptive_users u ON u.id = s.user_id
            WHERE s.token_hash = :token_hash AND s.expires_at > :now
        """), {"token_hash": _hash_secret(token), "now": now}).mappings().first()
        if not row:
            connection.execute(text("DELETE FROM adaptive_sessions WHERE token_hash = :token_hash"),
                               {"token_hash": _hash_secret(token)})
            return None
    return dict(row)


def require_user(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Please sign in to Adaptive AI.")
    return user


def _origin_allowed(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        # Same-origin browser forms normally send Origin for POST. Do not allow
        # cross-site fetches; clients without Origin must use the same-site cookie.
        return request.headers.get("sec-fetch-site", "same-origin") in ("same-origin", "none")
    return origin.rstrip("/") == str(request.base_url).rstrip("/")


def _check_origin(request: Request) -> None:
    if not _origin_allowed(request):
        raise HTTPException(status_code=403, detail="Cross-origin request blocked.")


class OwnerEnrollment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    full_name: str = Field(min_length=3, max_length=120)
    enrollment_secret: str = Field(min_length=24, max_length=512)
    password: str = Field(min_length=12, max_length=256)
    recovery_code: str = Field(min_length=24, max_length=256)

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return " ".join(value.split())


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class RecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    recovery_code: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)
    new_recovery_code: str = Field(min_length=24, max_length=256)


@router.post("/enroll-owner")
def enroll_owner(body: OwnerEnrollment, request: Request, response: Response):
    _check_origin(request)
    expected_secret = os.getenv("ADAPTIVE_AI_OWNER_ENROLLMENT_SECRET", "").strip()
    owner_email = os.getenv("ADAPTIVE_AI_OWNER_EMAIL", "").strip().lower()
    owner_name = " ".join(os.getenv("ADAPTIVE_AI_OWNER_NAME", "").split())
    if not expected_secret or len(expected_secret) < 24:
        raise HTTPException(status_code=503, detail="Owner enrollment is not configured by the service administrator.")
    if not owner_email or not owner_name:
        raise HTTPException(status_code=503, detail="Owner identity is not configured by the service administrator.")
    if not hmac.compare_digest(body.enrollment_secret, expected_secret):
        raise HTTPException(status_code=403, detail="Owner enrollment could not be verified.")
    if body.email.lower() != owner_email or body.full_name.casefold() != owner_name.casefold():
        raise HTTPException(status_code=403, detail="Owner identity does not match the configured owner.")
    engine = _ready_engine()
    now = _stamp(_now())
    user_id = str(uuid4())
    with engine.begin() as connection:
        count = connection.execute(text("SELECT COUNT(*) FROM adaptive_users WHERE role = 'owner'")).scalar_one()
        if count:
            raise HTTPException(status_code=409, detail="Owner account has already been enrolled.")
        connection.execute(text("""
            INSERT INTO adaptive_users(id,email,full_name,password_hash,role,phone_verified,created_at)
            VALUES (:id,:email,:name,:password_hash,'owner',0,:created)
        """), {"id": user_id, "email": owner_email, "name": owner_name,
               "password_hash": _hash_password(body.password), "created": now})
        connection.execute(text("""
            INSERT INTO adaptive_recovery_codes(user_id,code_hash,created_at)
            VALUES (:user_id,:code_hash,:created)
        """), {"user_id": user_id, "code_hash": _hash_secret(body.recovery_code), "created": now})
    token = secrets.token_urlsafe(48)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO adaptive_sessions(token_hash,user_id,expires_at,created_at) VALUES (:hash,:uid,:expires,:created)"),
                           {"hash": _hash_secret(token), "uid": user_id,
                            "expires": _stamp(_now() + timedelta(hours=SESSION_HOURS)), "created": now})
    _cookie(response, token)
    return {"authenticated": True, "user": {"email": owner_email, "full_name": owner_name, "role": "owner"},
            "message": "Owner account enrolled. Save your replacement recovery code securely."}


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response):
    _check_origin(request)
    engine = _ready_engine()
    with engine.connect() as connection:
        user = connection.execute(text("""
            SELECT id,email,full_name,role,password_hash FROM adaptive_users WHERE email=:email
        """), {"email": body.email.lower()}).mappings().first()
    # Perform a password hash even for unknown emails to reduce account enumeration timing.
    valid = _verify_password(body.password, user["password_hash"]) if user else _verify_password(
        body.password, "scrypt$" + ("00" * 16) + "$" + ("00" * 32))
    if not user or not valid:
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    token = secrets.token_urlsafe(48)
    now = _stamp(_now())
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO adaptive_sessions(token_hash,user_id,expires_at,created_at) VALUES (:hash,:uid,:expires,:created)"),
                           {"hash": _hash_secret(token), "uid": user["id"],
                            "expires": _stamp(_now() + timedelta(hours=SESSION_HOURS)), "created": now})
    _cookie(response, token)
    return {"authenticated": True, "user": {"email": user["email"], "full_name": user["full_name"], "role": user["role"]}}


@router.get("/me")
def me(request: Request):
    user = current_user(request)
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "user": user}


@router.post("/logout")
def logout(request: Request, response: Response):
    _check_origin(request)
    token = request.cookies.get(COOKIE_NAME, "")
    if token:
        with _ready_engine().begin() as connection:
            connection.execute(text("DELETE FROM adaptive_sessions WHERE token_hash=:hash"),
                               {"hash": _hash_secret(token)})
    _clear_cookie(response)
    return {"authenticated": False}


@router.post("/recover")
def recover(body: RecoveryRequest, request: Request):
    _check_origin(request)
    engine = _ready_engine()
    with engine.begin() as connection:
        user = connection.execute(text("SELECT id FROM adaptive_users WHERE email=:email AND role='owner'"),
                                  {"email": body.email.lower()}).mappings().first()
        if not user:
            raise HTTPException(status_code=400, detail="Recovery could not be verified.")
        row = connection.execute(text("SELECT code_hash FROM adaptive_recovery_codes WHERE user_id=:id"),
                                 {"id": user["id"]}).mappings().first()
        if not row or not hmac.compare_digest(row["code_hash"], _hash_secret(body.recovery_code)):
            raise HTTPException(status_code=400, detail="Recovery could not be verified.")
        connection.execute(text("UPDATE adaptive_users SET password_hash=:password_hash WHERE id=:id"),
                           {"password_hash": _hash_password(body.new_password), "id": user["id"]})
        connection.execute(text("UPDATE adaptive_recovery_codes SET code_hash=:code_hash, created_at=:created WHERE user_id=:id"),
                           {"code_hash": _hash_secret(body.new_recovery_code), "created": _stamp(_now()), "id": user["id"]})
        connection.execute(text("DELETE FROM adaptive_sessions WHERE user_id=:id"), {"id": user["id"]})
    return {"recovered": True, "message": "Password updated. Sign in with your new password."}
