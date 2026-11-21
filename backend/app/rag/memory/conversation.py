"""Conversation memory helpers."""
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.chat import ChatMessage, Conversation


def load_conversation_context(
    db: Session,
    conversation_id: uuid.UUID | str | None,
    organization_id: uuid.UUID | str,
    user_id: uuid.UUID | str | None,
    *,
    max_turns: int = 4,
) -> list[str]:
    """Return recent turns as ``role: content`` strings for query rewriting.

    Ownership is enforced: a conversation belonging to another user or
    organization yields no context.
    """
    if not conversation_id:
        return []
    try:
        conversation_uuid = uuid.UUID(str(conversation_id))
    except ValueError:
        return []
    conversation = db.get(Conversation, conversation_uuid)
    if conversation is None:
        return []
    if str(conversation.organization_id) != str(organization_id):
        return []
    if user_id is not None and str(conversation.user_id) != str(user_id):
        return []
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation_uuid)
        .order_by(ChatMessage.created_at.desc())
        .limit(max(1, max_turns) * 2)
        .all()
    )
    messages.reverse()
    return [f"{message.role}: {message.content[:1500]}" for message in messages]


def conversation_citations(db: Session, conversation_id: uuid.UUID | str) -> list[dict[str, Any]]:
    try:
        conversation_uuid = uuid.UUID(str(conversation_id))
    except ValueError:
        return []
    message = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation_uuid, ChatMessage.role == "assistant")
        .order_by(ChatMessage.created_at.desc())
        .first()
    )
    if message is None or not message.citations:
        return []
    try:
        value = json.loads(message.citations)
        return value if isinstance(value, list) else []
    except Exception:  # noqa: BLE001
        return []
