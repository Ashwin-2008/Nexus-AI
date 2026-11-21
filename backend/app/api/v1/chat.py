"""Chat API: conversations + grounded RAG message streaming.

Streaming contract (POST-based SSE; frontend must use fetch() + ReadableStream
since EventSource cannot send POST bodies):

POST /api/v1/chat/conversations/{id}/messages  body: {"content": "..."}
Response: text/event-stream with events:
  event: message_start  data: {conversation_id, user_message_id}
  event: context        data: {retrieval_latency_ms, context_chunks:[...]}
  event: token          data: {text}                    (LLM mode only)
  event: message_end    data: {answer, answer_mode, model, citations, ...}
  event: error          data: {code, message}

Non-streaming: same endpoint with {"content": "...", "stream": false} returns
the complete assistant message JSON.
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.chat import ChatMessage, Conversation
from app.models.user import User
from app.rag.security import scope_from_user
from app.services.rag_service import RagPipeline, meta_from_json, meta_to_json

router = APIRouter(prefix="/chat", tags=["chat"])

pipeline = RagPipeline()


# -- schemas -----------------------------------------------------------------


class ConversationCreate(BaseModel):
    title: str | None = Field(None, max_length=255)


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    user_id: uuid.UUID
    organization_id: uuid.UUID
    created_at: object
    updated_at: object


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    citations: list[dict] = []
    meta: dict = {}
    created_at: object


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=8000)
    stream: bool = True


# -- helpers -------------------------------------------------------------------


def _get_owned_conversation(db: Session, conversation_id: uuid.UUID, user: User) -> Conversation:
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.organization_id != user.organization_id or conv.user_id != user.id:
        # 404 (not 403) to avoid confirming existence of others' conversations
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Conversation not found"})
    return conv


def _message_to_read(m: ChatMessage) -> MessageRead:
    return MessageRead(
        id=m.id,
        conversation_id=m.conversation_id,
        role=m.role,
        content=m.content,
        citations=json.loads(m.citations) if m.citations else [],
        meta=meta_from_json(m.meta),
        created_at=m.created_at,
    )


# -- endpoints ------------------------------------------------------------------


@router.post("/conversations", response_model=ConversationRead, status_code=201)
def create_conversation(
    body: ConversationCreate | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = Conversation(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        title=(body.title if body and body.title else None),
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("/conversations", response_model=list[ConversationRead])
def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(Conversation)
        .filter(
            Conversation.organization_id == current_user.organization_id,
            Conversation.user_id == current_user.id,
        )
        .order_by(Conversation.updated_at.desc())
        .limit(100)
        .all()
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationRead)
def get_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _get_owned_conversation(db, conversation_id, current_user)


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = _get_owned_conversation(db, conversation_id, current_user)
    db.delete(conv)
    db.commit()
    return None


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageRead])
def list_messages(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = _get_owned_conversation(db, conversation_id, current_user)
    rows = db.query(ChatMessage).filter(ChatMessage.conversation_id == conv.id).order_by(ChatMessage.created_at).all()
    return [_message_to_read(m) for m in rows]


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/conversations/{conversation_id}/messages")
def create_message(
    conversation_id: uuid.UUID,
    body: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = _get_owned_conversation(db, conversation_id, current_user)

    user_msg = ChatMessage(
        conversation_id=conv.id,
        organization_id=conv.organization_id,
        role="user",
        content=body.content,
    )
    db.add(user_msg)
    if conv.title is None:
        conv.title = body.content[:120]
    db.commit()
    db.refresh(user_msg)

    if not body.stream:
        result = pipeline.run(db, scope_from_user(current_user), body.content)
        assistant = ChatMessage(
            conversation_id=conv.id,
            organization_id=conv.organization_id,
            role="assistant",
            content=result.answer,
            citations=json.dumps(result.citations, ensure_ascii=False) if result.citations else None,
            meta=meta_to_json(
                {
                    "answer_mode": result.answer_mode,
                    "model": result.model,
                    "retrieval_latency_ms": result.retrieval_latency_ms,
                    "generation_latency_ms": result.generation_latency_ms,
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                    "insufficient_evidence": result.insufficient_evidence,
                    "verification": result.verification,
                    "trace_id": result.trace_id,
                    "warnings": result.warnings,
                    "retrieval_mode": result.retrieval_mode,
                    "reranker": result.reranker,
                    "context_chunk_count": result.context_chunk_count,
                    "query_analysis": result.query_analysis,
                    "degraded_from": result.degraded_from,
                }
            ),
        )
        db.add(assistant)
        db.commit()
        db.refresh(assistant)
        return _message_to_read(assistant)

    def event_stream():
        yield _sse(
            "message_start",
            {"conversation_id": str(conv.id), "user_message_id": str(user_msg.id)},
        )
        final: dict = {}
        try:
            for event in pipeline.run_streaming(db, scope_from_user(current_user), body.content):
                final = event.get("data", final) if event["event"] == "message_end" else final
                yield _sse(event["event"], event["data"])
        except Exception as e:  # noqa: BLE001 — stream must always terminate with an event
            from app.services.rag_service import logger as rag_logger

            rag_logger.error("chat stream failed: %s", e)
            yield _sse("error", {"code": "generation_failed", "message": str(e)[:300]})
            return
        # Persist assistant message with verified citations
        assistant = ChatMessage(
            conversation_id=conv.id,
            organization_id=conv.organization_id,
            role="assistant",
            content=final.get("answer", ""),
            citations=json.dumps(final.get("citations", []), ensure_ascii=False) or None,
            meta=meta_to_json(final),
        )
        db.add(assistant)
        db.commit()
        # update conversation timestamp
        db.refresh(conv)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
