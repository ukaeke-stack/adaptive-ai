from fastapi import APIRouter, HTTPException
from app.memory.store import create_conversation, list_conversations, get_messages, conversation_exists, delete_conversation

router = APIRouter(prefix="/v1/conversations")


@router.post("")
def new_conversation():
    return create_conversation()


@router.get("")
def conversations():
    return {"conversations": list_conversations()}


@router.get("/{conversation_id}/messages")
def conversation_messages(conversation_id: str):
    if not conversation_exists(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"conversation_id": conversation_id, "messages": get_messages(conversation_id, limit=100)}


@router.delete("/{conversation_id}")
def remove_conversation(conversation_id: str):
    if not delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": True, "conversation_id": conversation_id}
