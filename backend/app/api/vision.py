"""Image understanding endpoint for Adaptive AI camera input."""
import base64
import os
import re
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

router = APIRouter(prefix="/v1/vision", tags=["vision"])
_DATA_URL = re.compile(r"^data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=]+)$")
_SYSTEM = (
    "You are Adaptive AI's visual assistant. Analyze the supplied image as ONE image, in one pass. "
    "Do not split it into top/bottom photos, panels, crops, or multiple images unless clear physical "
    "borders or unmistakable separate frames are actually visible. A repeated-looking subject, pose, "
    "or clothing pattern alone is not proof of multiple photographs. Never invent a composite or duplicate "
    "parts of the scene. Give one concise, direct answer (normally 2-6 sentences). Do not repeat the same "
    "observations in separate sections, summaries, key points, or a transcription recap. If the user asks "
    "for OCR, list readable text once; if no text is legible, say so briefly. Describe only relevant visible "
    "details and be honest about uncertainty. You may describe non-sensitive visible attributes of people, "
    "but must not identify a person, match a face to a real identity, or search social-media profiles from "
    "a face. Do not infer sensitive traits or claim to have searched the internet."
)


class VisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image_data_url: str = Field(min_length=100, max_length=8_500_000)
    prompt: str = Field(default="Describe what you see and transcribe any readable text.", min_length=1, max_length=2000)

    @field_validator("image_data_url")
    @classmethod
    def validate_image(cls, value: str) -> str:
        match = _DATA_URL.fullmatch(value.strip())
        if not match:
            raise ValueError("Image must be a base64 data URL for JPEG, PNG, or WebP.")
        try:
            raw = base64.b64decode(match.group(2), validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise ValueError("Image data is not valid base64.") from exc
        if not raw or len(raw) > 6_000_000:
            raise ValueError("Image must be smaller than 6 MB.")
        return value.strip()


@router.post("/analyze")
def analyze_image(request: VisionRequest):
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    base_url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").strip().rstrip("/")
    model = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b").strip()
    parsed = urlparse(base_url)
    if not api_key:
        raise HTTPException(status_code=503, detail="Groq API key is not configured.")
    if parsed.scheme != "https" or parsed.hostname != "api.groq.com" or parsed.username or parsed.password:
        raise HTTPException(status_code=503, detail="Groq base URL must use the official HTTPS API host.")
    match = _DATA_URL.fullmatch(request.image_data_url)
    if not match:
        raise HTTPException(status_code=422, detail="Unsupported image data.")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": request.prompt.strip() + " Return one concise description. Do not repeat it in multiple sections."},
                {"type": "image_url", "image_url": {"url": request.image_data_url}},
            ]},
        ],
        "temperature": 0.1,
        "reasoning_effort": "none",
        "max_completion_tokens": 550,
    }
    try:
        models_to_try = [model]
        fallback_model = "qwen/qwen3.8-27b"
        if model != fallback_model:
            models_to_try.append(fallback_model)
        data = None
        used_model = model
        with httpx.Client(timeout=httpx.Timeout(45.0, connect=8.0)) as client:
            for candidate in models_to_try:
                payload["model"] = candidate
                response = client.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
                if response.status_code in (400, 404, 422) and candidate != models_to_try[-1]:
                    continue
                response.raise_for_status()
                data = response.json()
                used_model = candidate
                break
        if data is None:
            raise ValueError("vision provider returned no result")
        answer = data["choices"][0]["message"]["content"]
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("empty response")
        return {"analysis": answer.strip(), "model": used_model}
    except httpx.HTTPStatusError as exc:
        # Avoid forwarding provider response bodies, which may contain operational details.
        if exc.response.status_code in (400, 404, 422):
            raise HTTPException(status_code=502, detail="The configured Groq vision model is unavailable or rejected the image. Check GROQ_VISION_MODEL.") from exc
        if exc.response.status_code == 429:
            raise HTTPException(status_code=503, detail="The vision provider is rate-limited. Try again shortly.") from exc
        raise HTTPException(status_code=502, detail="The vision provider request failed.") from exc
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="Could not analyze this image. Try a clearer or smaller image.") from exc
