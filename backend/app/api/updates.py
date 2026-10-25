"""Signed update release verification and owner approval ledger. This service never deploys its own code."""
from __future__ import annotations
import base64, hashlib, json, os, re
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature
from app.memory.store import _ready_engine
from app.security.sessions import require_user

router=APIRouter(prefix="/v1/updates",tags=["signed updates"])

class SignedRelease(BaseModel):
    model_config=ConfigDict(extra="forbid")
    version: str=Field(pattern=r"^v?[0-9]+\.[0-9]+\.[0-9]+$",max_length=32)
    source_revision: str=Field(pattern=r"^[0-9a-f]{40}$")
    artifact_sha256: str=Field(pattern=r"^[0-9a-f]{64}$")
    signature: str=Field(min_length=80,max_length=512)

def _tables():
    with _ready_engine().begin() as conn:
        conn.execute(text("""CREATE TABLE IF NOT EXISTS adaptive_signed_releases(
        id TEXT PRIMARY KEY, version TEXT NOT NULL, source_revision TEXT NOT NULL,
        artifact_sha256 TEXT NOT NULL, manifest_sha256 TEXT NOT NULL, status TEXT NOT NULL,
        proposed_by TEXT NOT NULL, approved_by TEXT, created_at TEXT NOT NULL, approved_at TEXT)"""))

def _owner(request):
    user=require_user(request)
    if user.get("role")!="owner": raise HTTPException(status_code=403,detail="Only the platform owner can manage releases.")
    return user

def _verify(body):
    pem=os.getenv("ADAPTIVE_AI_UPDATE_PUBLIC_KEY","").strip()
    if not pem: raise HTTPException(status_code=503,detail="Update signing public key is not configured.")
    try:
        key=serialization.load_pem_public_key(pem.encode())
        if key.__class__.__name__!="Ed25519PublicKey": raise ValueError("Expected Ed25519 public key")
        manifest={"version":body.version,"source_revision":body.source_revision,"artifact_sha256":body.artifact_sha256}
        canonical=json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()
        signature=base64.b64decode(body.signature,validate=True)
        key.verify(signature,canonical)
        return hashlib.sha256(canonical).hexdigest()
    except InvalidSignature as exc:
        raise HTTPException(status_code=422,detail="Release signature verification failed.") from exc
    except HTTPException: raise
    except Exception as exc:
        raise HTTPException(status_code=422,detail="Invalid update signing key, manifest or signature.") from exc

@router.get("/policy")
def update_policy(request: Request):
    user=require_user(request)
    return {"enabled":os.getenv("ADAPTIVE_AI_UPDATES_ENABLED","false").lower()=="true",
      "authenticated_role":user.get("role"),"signature_algorithm":"Ed25519",
      "requires_ci_pass":True,"requires_owner_approval":True,"requires_rollback_snapshot":True,
      "mode":"signed-release-approval-only","automatic_deployment":False}

@router.post("/proposals")
def propose_release(body: SignedRelease, request: Request):
    user=_owner(request)
    if os.getenv("ADAPTIVE_AI_UPDATES_ENABLED","false").lower()!="true":
        raise HTTPException(status_code=503,detail="Signed update proposals are disabled by the service administrator.")
    digest=_verify(body); _tables(); rid=str(uuid4()); now=datetime.now(timezone.utc).isoformat()
    with _ready_engine().begin() as conn:
        conn.execute(text("""INSERT INTO adaptive_signed_releases
        (id,version,source_revision,artifact_sha256,manifest_sha256,status,proposed_by,created_at)
        VALUES(:id,:version,:revision,:artifact,:digest,'pending_approval',:uid,:at)"""),
        {"id":rid,"version":body.version,"revision":body.source_revision,"artifact":body.artifact_sha256,
         "digest":digest,"uid":user["id"],"at":now})
    return {"release_id":rid,"status":"pending_approval","manifest_sha256":digest,"signature_verified":True,
      "message":"Signature verified. No files were installed and no deployment was triggered."}

@router.get("/releases")
def list_releases(request: Request):
    user=_owner(request); _tables()
    with _ready_engine().connect() as conn:
        rows=conn.execute(text("""SELECT id,version,source_revision,artifact_sha256,manifest_sha256,status,
        proposed_by,approved_by,created_at,approved_at FROM adaptive_signed_releases ORDER BY created_at DESC LIMIT 100""")).mappings().all()
    return {"releases":[dict(r) for r in rows]}

@router.post("/releases/{release_id}/approve")
def approve_release(release_id: str, request: Request):
    user=_owner(request); _tables(); now=datetime.now(timezone.utc).isoformat()
    with _ready_engine().begin() as conn:
        result=conn.execute(text("""UPDATE adaptive_signed_releases SET status='approved',approved_by=:uid,approved_at=:at
        WHERE id=:id AND status='pending_approval'"""),{"uid":user["id"],"at":now,"id":release_id})
    if not result.rowcount: raise HTTPException(status_code=404,detail="Pending signed release not found.")
    return {"approved":True,"release_id":release_id,"status":"approved","deployment_triggered":False}

@router.post("/releases/{release_id}/mark-deployed")
def mark_deployed(release_id: str, request: Request):
    _owner(request); _tables()
    with _ready_engine().begin() as conn:
        result=conn.execute(text("UPDATE adaptive_signed_releases SET status='deployed' WHERE id=:id AND status='approved'"),{"id":release_id})
    if not result.rowcount: raise HTTPException(status_code=409,detail="Only an approved release can be marked deployed.")
    return {"release_id":release_id,"status":"deployed","note":"This records a deployment performed by the external CI/hosting pipeline; it does not deploy code."}

@router.post("/rollback-plan")
def rollback_plan(request: Request):
    _owner(request); _tables()
    with _ready_engine().connect() as conn:
        rows=conn.execute(text("""SELECT id,version,source_revision,artifact_sha256,status FROM adaptive_signed_releases
        WHERE status='deployed' ORDER BY approved_at DESC LIMIT 2""")).mappings().all()
    if len(rows)<2: raise HTTPException(status_code=409,detail="A rollback target requires at least two recorded deployed signed releases.")
    return {"current_release":dict(rows[0]),"rollback_target":dict(rows[1]),"requires_external_deploy":True,
      "message":"Use the hosting/CI rollback mechanism to deploy the target revision, then verify health before marking it current."}
