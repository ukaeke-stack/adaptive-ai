from fastapi import APIRouter, HTTPException, Request
from app.memory.store import create_conversation, list_conversations, get_messages, conversation_exists, delete_conversation
from app.security.sessions import require_user

router = APIRouter(prefix="/v1/conversations")


@router.post("")
def new_conversation(request: Request):
    user = require_user(request)
    return create_conversation(user_id=user["id"])


@router.get("")
def conversations(request: Request):
    user = require_user(request)
    return {"conversations": list_conversations(user_id=user["id"])}


@router.get("/{conversation_id}/messages")
def conversation_messages(conversation_id: str, request: Request):
    user = require_user(request)
    if not conversation_exists(conversation_id, user_id=user["id"]):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"conversation_id": conversation_id, "messages": get_messages(conversation_id, limit=100)}


@router.delete("/{conversation_id}")
def remove_conversation(conversation_id: str, request: Request):
    user = require_user(request)
    if not delete_conversation(conversation_id, user_id=user["id"]):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": True, "conversation_id": conversation_id}
