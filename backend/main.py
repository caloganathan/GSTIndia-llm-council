"""FastAPI backend for LLM Council."""

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, storage
from .auth import require_auth
from .council import (
    generate_conversation_title,
    run_council_stream,
    run_full_council,
)

app = FastAPI(title="LLM Council API")

# CORS for local development (in production the frontend is served same-origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# All /api routes require the access token (no-op when APP_ACCESS_TOKEN unset)
router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])

# Best-effort startup validation of configured model IDs, surfaced via /api/health
MODEL_VALIDATION: Dict[str, Any] = {"checked": False}


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    pass


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""
    content: str
    mode: str = "full"          # "full" = 3-stage deliberation, "quick" = skip peer review
    web_search: bool = False    # ground Stage 1 with OpenRouter's web search plugin


class ConversationMetadata(BaseModel):
    """Conversation metadata for list view."""
    id: str
    created_at: str
    title: str
    message_count: int


class Conversation(BaseModel):
    """Full conversation with all messages."""
    id: str
    created_at: str
    title: str
    messages: List[Dict[str, Any]]


@app.get("/healthz")
async def healthz():
    """Unauthenticated liveness probe (used by the hosting platform)."""
    return {"status": "ok"}


@router.get("/auth/check")
async def auth_check():
    """Returns 200 when the presented token is valid (or auth is disabled)."""
    return {"status": "ok", "auth_enabled": bool(config.APP_ACCESS_TOKEN)}


@router.get("/health")
async def health():
    """Config summary + model ID validation results."""
    return {
        "status": "ok",
        "council_models": config.COUNCIL_MODELS,
        "chairman_model": config.CHAIRMAN_MODEL,
        "reasoning_effort": config.REASONING_EFFORT,
        "auth_enabled": bool(config.APP_ACCESS_TOKEN),
        "model_validation": MODEL_VALIDATION,
    }


@router.get("/conversations", response_model=List[ConversationMetadata])
async def list_conversations():
    """List all conversations (metadata only)."""
    return storage.list_conversations()


@router.post("/conversations", response_model=Conversation)
async def create_conversation(request: CreateConversationRequest):
    """Create a new conversation."""
    conversation_id = str(uuid.uuid4())
    conversation = storage.create_conversation(conversation_id)
    return conversation


@router.get("/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    """Get a specific conversation with all its messages."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation."""
    if not storage.delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "deleted"}


@router.post("/conversations/{conversation_id}/message")
async def send_message(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and run the council process (non-streaming).
    Returns the complete response with all stages.
    """
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    is_first_message = len(conversation["messages"]) == 0
    prior_messages = conversation["messages"]

    storage.add_user_message(conversation_id, request.content)

    if is_first_message:
        title = await generate_conversation_title(request.content)
        storage.update_conversation_title(conversation_id, title)

    stage1_results, stage2_results, stage3_result, metadata = await run_full_council(
        request.content,
        prior_messages=prior_messages,
        mode=request.mode,
        web_search=request.web_search,
    )

    storage.add_assistant_message(
        conversation_id, stage1_results, stage2_results, stage3_result, metadata
    )

    return {
        "stage1": stage1_results,
        "stage2": stage2_results,
        "stage3": stage3_result,
        "metadata": metadata,
    }


@router.post("/conversations/{conversation_id}/message/stream")
async def send_message_stream(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and stream the council process.
    Returns Server-Sent Events as each stage completes.
    """
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    is_first_message = len(conversation["messages"]) == 0
    prior_messages = conversation["messages"]

    async def event_generator():
        try:
            storage.add_user_message(conversation_id, request.content)

            title_task = None
            if is_first_message:
                title_task = asyncio.create_task(
                    generate_conversation_title(request.content)
                )

            final: Optional[Dict[str, Any]] = None
            async for event in run_council_stream(
                request.content,
                prior_messages=prior_messages,
                mode=request.mode,
                web_search=request.web_search,
            ):
                if event["type"] == "summary":
                    final = event
                yield f"data: {json.dumps(event)}\n\n"

            if final is not None:
                storage.add_assistant_message(
                    conversation_id,
                    final["data"]["stage1"],
                    final["data"]["stage2"],
                    final["data"]["stage3"],
                    final.get("metadata", {}),
                )

            if title_task:
                title = await title_task
                storage.update_conversation_title(conversation_id, title)
                yield f"data: {json.dumps({'type': 'title_complete', 'data': {'title': title}})}\n\n"

            yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        except Exception as e:
            print(f"Stream error in conversation {conversation_id}: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


app.include_router(router)


@app.on_event("startup")
async def validate_models():
    """Check configured model IDs against OpenRouter's catalog (best-effort)."""
    configured = set(config.COUNCIL_MODELS) | {config.CHAIRMAN_MODEL, config.TITLE_MODEL}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(config.OPENROUTER_MODELS_URL)
            response.raise_for_status()
            available = {m["id"] for m in response.json().get("data", [])}
    except Exception as e:
        MODEL_VALIDATION.update({"checked": False, "error": str(e)})
        print(f"Warning: could not validate model IDs against OpenRouter: {e}")
        return

    unknown = sorted(configured - available)
    MODEL_VALIDATION.update({"checked": True, "unknown_models": unknown})
    if unknown:
        print(f"WARNING: these configured model IDs were not found on OpenRouter: "
              f"{', '.join(unknown)} — check backend/config.py or your env vars.")
    else:
        print("All configured model IDs validated against OpenRouter.")


# Serve the built frontend (single-service deployment). Registered after all
# API routes so /api and /healthz take precedence.
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT)
