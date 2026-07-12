from __future__ import annotations

import json
import logging
from typing import AsyncIterator

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..ai.errors import CLIPermanentError, CLITransientError
from ..ai.guide_registry import get_guide_adapter
from . import sessions
from .rate_limit import rate_limit_ok
from .settings import guide_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/guide", tags=["guide"])


class CreateSessionBody(BaseModel):
    locale: str = "en"


class SessionResponse(BaseModel):
    session_id: str
    created_at: str
    locale: str | None = None


class MessageBody(BaseModel):
    message: str = Field(..., min_length=1)
    locale: str | None = None


class MessageResponse(BaseModel):
    session_id: str
    message_id: str
    role: str
    content: str
    created_at: str


class SessionDetailResponse(BaseModel):
    session_id: str
    locale: str
    created_at: str
    updated_at: str
    messages: list[MessageResponse]


def _check_token(authorization: str | None, x_guide_token: str | None) -> None:
    settings = guide_settings()
    expected = settings["service_token"]
    require = settings["require_token"] or bool(expected)
    if not require:
        return
    if not expected:
        # Misconfiguration: require without token configured → deny
        raise HTTPException(status_code=503, detail="Guide service token not configured")
    provided = None
    if x_guide_token:
        provided = x_guide_token.strip()
    elif authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    if provided != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


def _validate_message(message: str) -> str:
    text = (message or "").strip()
    max_chars = guide_settings()["max_message_chars"]
    if not text:
        raise HTTPException(status_code=400, detail="Message is empty")
    if len(text) > max_chars:
        raise HTTPException(
            status_code=400,
            detail=f"Message exceeds maximum length of {max_chars} characters",
        )
    return text


async def _prepare_turn(
    request: Request,
    session_id: str,
    body: MessageBody,
    authorization: str | None,
    x_guide_token: str | None,
) -> tuple[str, str, list[dict], str]:
    """Validate and persist user message. Returns session_id, user_text, history, locale."""
    _check_token(authorization, x_guide_token)
    session = await sessions.ensure_session_active(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    if not rate_limit_ok(_client_key(request)):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    max_msgs = guide_settings()["max_messages_per_session"]
    count = await sessions.count_messages(session_id)
    if count >= max_msgs:
        raise HTTPException(status_code=429, detail="Session message limit reached")

    user_text = _validate_message(body.message)
    locale = (body.locale or session.get("locale") or "en").strip() or "en"

    history = await sessions.history_for_prompt(session_id)
    await sessions.add_message(session_id, "user", user_text)
    return session_id, user_text, history, locale


@router.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_guide_session(
    request: Request,
    body: CreateSessionBody | None = None,
    authorization: str | None = Header(default=None),
    x_guide_token: str | None = Header(default=None, alias="X-Guide-Token"),
) -> SessionResponse:
    _check_token(authorization, x_guide_token)
    locale = (body.locale if body else "en") or "en"
    created = await sessions.create_session(locale=locale)
    return SessionResponse(
        session_id=created["session_id"],
        created_at=created["created_at"],
        locale=created.get("locale"),
    )


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_guide_session(
    session_id: str,
    authorization: str | None = Header(default=None),
    x_guide_token: str | None = Header(default=None, alias="X-Guide-Token"),
) -> SessionDetailResponse:
    _check_token(authorization, x_guide_token)
    session = await sessions.ensure_session_active(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    messages = await sessions.list_messages(session_id, limit=200)
    return SessionDetailResponse(
        session_id=session["session_id"],
        locale=session["locale"],
        created_at=session["created_at"],
        updated_at=session["updated_at"],
        messages=[
            MessageResponse(
                session_id=m["session_id"],
                message_id=m["message_id"],
                role=m["role"],
                content=m["content"],
                created_at=m["created_at"],
            )
            for m in messages
        ],
    )


@router.post("/sessions/{session_id}/messages", response_model=MessageResponse)
async def post_guide_message(
    session_id: str,
    body: MessageBody,
    request: Request,
    authorization: str | None = Header(default=None),
    x_guide_token: str | None = Header(default=None, alias="X-Guide-Token"),
) -> MessageResponse:
    sid, user_text, history, locale = await _prepare_turn(
        request, session_id, body, authorization, x_guide_token
    )
    adapter = get_guide_adapter()
    try:
        content = await adapter.chat(
            user_message=user_text,
            history=history,
            locale=locale,
            session_id=sid,
        )
    except CLITransientError as exc:
        logger.warning("Guide CLI transient error: %s", exc)
        raise HTTPException(status_code=503, detail="Guide temporarily unavailable") from exc
    except CLIPermanentError as exc:
        logger.error("Guide CLI permanent error: %s", exc)
        raise HTTPException(status_code=502, detail="Guide failed to produce a reply") from exc

    stored = await sessions.add_message(sid, "assistant", content)
    return MessageResponse(
        session_id=sid,
        message_id=stored["message_id"],
        role="assistant",
        content=content,
        created_at=stored["created_at"],
    )


@router.post("/sessions/{session_id}/messages/stream")
async def post_guide_message_stream(
    session_id: str,
    body: MessageBody,
    request: Request,
    authorization: str | None = Header(default=None),
    x_guide_token: str | None = Header(default=None, alias="X-Guide-Token"),
) -> StreamingResponse:
    sid, user_text, history, locale = await _prepare_turn(
        request, session_id, body, authorization, x_guide_token
    )
    adapter = get_guide_adapter()

    async def event_gen() -> AsyncIterator[bytes]:
        pieces: list[str] = []
        try:
            async for chunk in adapter.chat_stream(
                user_message=user_text,
                history=history,
                locale=locale,
                session_id=sid,
            ):
                pieces.append(chunk)
                payload = json.dumps({"type": "token", "content": chunk}, ensure_ascii=False)
                yield f"data: {payload}\n\n".encode("utf-8")
            full = "".join(pieces)
            stored = await sessions.add_message(sid, "assistant", full)
            done = {
                "type": "done",
                "session_id": sid,
                "message_id": stored["message_id"],
                "content": full,
                "created_at": stored["created_at"],
            }
            yield f"data: {json.dumps(done, ensure_ascii=False)}\n\n".encode("utf-8")
        except CLITransientError as exc:
            logger.warning("Guide stream transient error: %s", exc)
            err = {"type": "error", "detail": "Guide temporarily unavailable"}
            yield f"data: {json.dumps(err)}\n\n".encode("utf-8")
        except CLIPermanentError as exc:
            logger.error("Guide stream permanent error: %s", exc)
            err = {"type": "error", "detail": "Guide failed to produce a reply"}
            yield f"data: {json.dumps(err)}\n\n".encode("utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Guide stream unexpected error: %s", exc)
            err = {"type": "error", "detail": "Unexpected guide error"}
            yield f"data: {json.dumps(err)}\n\n".encode("utf-8")

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
