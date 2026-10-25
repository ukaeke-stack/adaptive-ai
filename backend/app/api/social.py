"""Social-account integration readiness; no tokens are accepted or stored here."""
import os
from fastapi import APIRouter, HTTPException, Request
from app.security.sessions import require_user

router = APIRouter(prefix="/v1/social", tags=["social"])
_PROVIDERS = {
    "instagram": ("INSTAGRAM_CLIENT_ID", "INSTAGRAM_CLIENT_SECRET", "INSTAGRAM_REDIRECT_URI"),
    "facebook": ("FACEBOOK_CLIENT_ID", "FACEBOOK_CLIENT_SECRET", "FACEBOOK_REDIRECT_URI"),
    "x": ("X_CLIENT_ID", "X_CLIENT_SECRET", "X_REDIRECT_URI"),
    "youtube": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "YOUTUBE_REDIRECT_URI"),
    "tiktok": ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REDIRECT_URI"),
}

@router.get("/providers")
def providers(request: Request):
    require_user(request)
    return {"providers": [{"provider": name,
        "configured": all(os.getenv(key, "").strip() for key in keys),
        "connected": False,
        "status": "ready_for_oauth" if all(os.getenv(key, "").strip() for key in keys) else "needs_provider_credentials"}
        for name, keys in _PROVIDERS.items()]}

@router.post("/{provider}/connect")
def connect(provider: str, request: Request):
    require_user(request)
    if provider not in _PROVIDERS:
        raise HTTPException(status_code=404, detail="Unsupported social provider")
    if not all(os.getenv(key, "").strip() for key in _PROVIDERS[provider]):
        raise HTTPException(status_code=503, detail=f"{provider} OAuth needs provider client ID, secret, and redirect URI configured by the service administrator.")
    raise HTTPException(status_code=501, detail="Provider credentials exist, but OAuth state/PKCE, callback validation, encrypted token storage, and revocation are not deployed. No account was connected.")
