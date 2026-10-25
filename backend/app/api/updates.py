"""Owner-gated update proposal policy; never mutates code or deploys directly."""
import os
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from app.security.sessions import require_user

router = APIRouter(prefix="/v1/updates", tags=["updates"])

class UpdateProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(pattern=r"^v?[0-9]+\.[0-9]+\.[0-9]+$", max_length=32)
    summary: str = Field(min_length=10, max_length=2000)
    source_revision: str = Field(pattern=r"^[0-9a-f]{7,40}$", max_length=40)

@router.get("/policy")
def update_policy(request: Request):
    user = require_user(request)
    return {"enabled": os.getenv("ADAPTIVE_AI_UPDATES_ENABLED", "false").lower() == "true",
            "requires_role": "owner", "authenticated_role": user.get("role"),
            "requires_ci_pass": True, "requires_approval": True,
            "requires_rollback_snapshot": True, "mode": "proposal_only"}

@router.post("/proposals")
def propose_update(body: UpdateProposal, request: Request):
    user = require_user(request)
    if user.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can propose an application update.")
    if os.getenv("ADAPTIVE_AI_UPDATES_ENABLED", "false").lower() != "true":
        raise HTTPException(status_code=503, detail="Update proposals are disabled by the service administrator.")
    return {"accepted": False, "status": "manual_review_required", "version": body.version,
            "source_revision": body.source_revision,
            "message": "No deployment was triggered. Code review, CI, signing, staged rollout, and rollback remain mandatory."}
