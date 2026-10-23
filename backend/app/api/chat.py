from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.ai.provider import generate_reply, ProviderNotConfigured, ProviderRequestError
from app.memory.store import create_conversation, conversation_exists, add_message, get_messages

router = APIRouter(prefix="/v1")


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message must not be blank")
        return value


@router.post("/chat")
def chat(request: ChatRequest):
    conversation = create_conversation() if request.conversation_id is None else None
    conversation_id = conversation["id"] if conversation else request.conversation_id
    if not conversation and not conversation_exists(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    history = get_messages(conversation_id, limit=20)
    add_message(conversation_id, "user", request.message)
    try:
        reply = generate_reply(request.message, history=history)
    except ProviderNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    add_message(conversation_id, "assistant", reply)
    return {"reply": reply, "conversation_id": conversation_id}
