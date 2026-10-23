from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from app.ai.provider import generate_reply, ProviderNotConfigured, ProviderRequestError

router = APIRouter(prefix="/v1")


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=8000)


@router.post("/chat")
def chat(request: ChatRequest):
    try:
        reply = generate_reply(request.message.strip())
    except ProviderNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"reply": reply}
