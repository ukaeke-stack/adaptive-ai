import base64
import json
import hashlib

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from app.main import app
from app.api import document_ocr, updates
from app.api.safe_plugins import ALLOWED, Manifest

client = TestClient(app)


def test_ocr_rejects_non_pdf_before_processing(monkeypatch):
    monkeypatch.setattr(document_ocr, "require_user", lambda request: {"id": "test-user", "role": "owner"})
    response = client.post(
        "/v1/assistant/documents/ocr-pdf",
        files={"file": ("not-a-pdf.txt", b"plain text", "text/plain")},
    )
    assert response.status_code == 415


def test_ocr_rejects_fake_pdf_header(monkeypatch):
    monkeypatch.setattr(document_ocr, "require_user", lambda request: {"id": "test-user", "role": "owner"})
    response = client.post(
        "/v1/assistant/documents/ocr-pdf",
        files={"file": ("fake.pdf", b"not actually a pdf", "application/pdf")},
    )
    assert response.status_code == 415


def test_plugin_manifest_rejects_extra_fields():
    with pytest.raises(Exception):
        Manifest(name="example plugin", capabilities=["count_words"], run_shell=True)


def test_plugin_capability_allowlist_excludes_arbitrary_code():
    manifest = Manifest(name="example plugin", capabilities=["count_words"])
    assert manifest.capabilities == ["count_words"]
    assert ALLOWED == {"count_words", "extract_bullets", "draft_message"}
    assert "execute_shell" not in ALLOWED


def _signed_release():
    private_key = Ed25519PrivateKey.generate()
    manifest = {
        "version": "v1.2.3",
        "source_revision": "a" * 40,
        "artifact_sha256": "b" * 64,
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    signature = base64.b64encode(private_key.sign(canonical)).decode()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    body = updates.SignedRelease(**manifest, signature=signature)
    return body, public_key


def test_signed_update_verifies_ed25519_manifest(monkeypatch):
    body, public_key = _signed_release()
    monkeypatch.setenv("ADAPTIVE_AI_UPDATE_PUBLIC_KEY", public_key)
    digest = updates._verify(body)
    assert digest == hashlib.sha256(
        json.dumps(
            {
                "version": body.version,
                "source_revision": body.source_revision,
                "artifact_sha256": body.artifact_sha256,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def test_signed_update_rejects_tampered_manifest(monkeypatch):
    body, public_key = _signed_release()
    monkeypatch.setenv("ADAPTIVE_AI_UPDATE_PUBLIC_KEY", public_key)
    tampered = body.model_copy(update={"artifact_sha256": "c" * 64})
    with pytest.raises(HTTPException) as exc:
        updates._verify(tampered)
    assert exc.value.status_code == 422


def test_signed_update_requires_configured_public_key(monkeypatch):
    body, _ = _signed_release()
    monkeypatch.delenv("ADAPTIVE_AI_UPDATE_PUBLIC_KEY", raising=False)
    with pytest.raises(HTTPException) as exc:
        updates._verify(body)
    assert exc.value.status_code == 503


def test_update_policy_never_claims_automatic_deployment(monkeypatch):
    monkeypatch.setattr(updates, "require_user", lambda request: {"id": "owner", "role": "owner"})
    response = client.get("/v1/updates/policy")
    assert response.status_code == 200
    assert response.json()["automatic_deployment"] is False
    assert response.json()["mode"] == "signed-release-approval-only"


def test_ocr_processes_scanned_pdf_page_and_returns_text(monkeypatch):
    monkeypatch.setattr(document_ocr, "require_user", lambda request: {"id": "test-user", "role": "owner"})
    monkeypatch.setattr(document_ocr.pytesseract, "image_to_string", lambda image, timeout=20: "Recognized scanned text")
    import fitz
    pdf = fitz.open()
    page = pdf.new_page(width=300, height=300)
    page.insert_text((30, 40), "scan placeholder")
    data = pdf.tobytes()
    pdf.close()

    response = client.post(
        "/v1/assistant/documents/ocr-pdf",
        files={"file": ("scanned.pdf", data, "application/pdf")},
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["filename"] == "scanned.pdf"
    assert result["page_count"] == 1
    assert result["processed_pages"] == 1
    assert "Recognized scanned text" in result["text"]
    assert result["method"] == "local-tesseract-ocr"
