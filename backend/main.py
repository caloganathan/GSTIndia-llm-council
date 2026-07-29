"""FastAPI backend for LLM Council."""

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import (APIRouter, Depends, FastAPI, File, Header, HTTPException,
                     Response, UploadFile)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import (calculators, config, deadlines, export, intake, ocr, pricing,
               reconciliation, storage, users)
from .auth import redact_for_role, require_auth, require_permission, resolve_user
from .council import (
    generate_conversation_title,
    run_council_stream,
    run_full_council,
)
from .domains import available_domains, get_pack
from .panel import run_panel_stream
from .roles import PANEL_ROLES

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    Startup work, none of which may prevent the service from coming up.

    A deployment that refuses to start because the model catalogue was briefly
    unreachable is worse than one that starts and reports the problem on its
    health endpoint.
    """
    for step in (ensure_state_dirs, bootstrap_users, validate_models):
        try:
            await step()
        except Exception as e:  # noqa: BLE001 - startup must never be fatal
            print(f"Startup step {step.__name__} failed (continuing): {e}")
    yield


app = FastAPI(title="LLM Council API", lifespan=lifespan)

# CORS for local development (in production the frontend is served same-origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_origin_regex=(r"https://.*\.vercel\.app"
                        if config.CORS_ALLOW_VERCEL_PREVIEWS else None),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# All /api routes require the access token (no-op when APP_ACCESS_TOKEN unset)
router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])

# Best-effort startup validation of configured model IDs, surfaced via /api/health
MODEL_VALIDATION: Dict[str, Any] = {"checked": False}


class CouncilQuestion(BaseModel):
    """A question put to the general council."""
    content: str
    # "full" runs all three stages; "quick" skips peer review, which is
    # roughly half the cost and most of the speed.
    mode: str = "full"
    # Ground the opening responses with OpenRouter's web search plugin.
    web_search: bool = False


class ConversationEntry(BaseModel):
    """One row of the conversation index — enough to render the sidebar."""
    id: str
    created_at: str
    title: str
    message_count: int


class ConversationRecord(BaseModel):
    """A conversation with its full message history."""
    id: str
    created_at: str
    title: str
    messages: List[Dict[str, Any]]


class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class CreateUserRequest(BaseModel):
    email: str
    password: str
    name: str = ""
    role: str = "staff"


class UpdateUserRequest(BaseModel):
    role: Optional[str] = None
    active: Optional[bool] = None
    name: Optional[str] = None
    password: Optional[str] = None


class PanelRunRequest(BaseModel):
    """Run the compliance panel on a matter."""
    intake: Dict[str, Any]
    domain: str = "gst"
    tier: str = config.DEFAULT_TIER
    skip_verification: bool = False


@app.get("/healthz")
async def healthz():
    """Unauthenticated liveness probe (used by the hosting platform)."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    """
    Unauthenticated readiness probe.

    Reports the things that make a deployment useless even though the process
    is alive: no API key, or state that cannot be persisted.
    """
    checks = {
        "api_key_configured": bool(config.OPENROUTER_API_KEY),
        "state_writable": STATE_WRITABLE.get("ok"),
        "frontend_bundled": FRONTEND_DIST.is_dir(),
        "auth_enabled": bool(config.APP_ACCESS_TOKEN) or users.user_count() > 0,
    }
    ready = bool(checks["api_key_configured"]) and checks["state_writable"] is not False
    return {"status": "ready" if ready else "degraded", "checks": checks,
            "state_dir": config.STATE_DIR, "data_dir": config.DATA_DIR}


@router.get("/features")
async def features():
    """
    What this deployment offers, for the UI to render against.

    Read on the auth check rather than fetched separately so navigation never
    flickers a tab into existence after the page has settled.
    """
    ocr_ready, ocr_reason = ocr.available()
    return {
        "general_council": config.ENABLE_GENERAL_COUNCIL,
        "ocr": {"available": ocr_ready, "reason": ocr_reason},
    }


@router.get("/auth/check")
async def auth_check(user: Dict[str, Any] = Depends(require_auth)):
    """Returns 200 when the presented credential is valid (or auth is disabled)."""
    ocr_ready, ocr_reason = ocr.available()
    return {
        "status": "ok",
        "auth_enabled": bool(config.APP_ACCESS_TOKEN) or users.user_count() > 0,
        "user": user,
        # Carried on the session check so navigation renders once, correctly,
        # rather than growing a tab after the page has settled.
        "features": {
            "general_council": config.ENABLE_GENERAL_COUNCIL,
            "ocr": {"available": ocr_ready, "reason": ocr_reason},
        },
    }


@app.post("/api/auth/login")
async def login(request: LoginRequest):
    """Exchange email + password for a session token."""
    session = users.authenticate(request.email, request.password)
    if session is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return session


@router.post("/auth/logout")
async def logout(authorization: str = Header(default="")):
    """Revoke the current session token."""
    token = authorization.split(" ", 1)[-1].strip() if authorization else ""
    users.revoke_session(token)
    return {"status": "ok"}


@router.post("/auth/password")
async def change_password(
    request: ChangePasswordRequest,
    user: Dict[str, Any] = Depends(require_auth),
):
    """Change the signed-in user's own password."""
    if user["id"] in ("legacy-token", "anonymous"):
        raise HTTPException(
            status_code=400,
            detail="The shared access token has no password. Sign in as a named user.",
        )
    record = users.find_by_email(user["email"])
    if record is None or not users.verify_password(
        request.current_password, record["password"]
    ):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    try:
        users.update_user(user["id"], password=request.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok"}


@router.get("/health")
async def health():
    """Config summary + model ID validation results."""
    ocr_ready, ocr_reason = ocr.available()
    return {
        "status": "ok",
        "council_models": config.COUNCIL_MODELS,
        "chairman_model": config.CHAIRMAN_MODEL,
        "reasoning_effort": config.REASONING_EFFORT,
        "auth_enabled": bool(config.APP_ACCESS_TOKEN) or users.user_count() > 0,
        "model_validation": MODEL_VALIDATION,
        # Surfaced so the UI can warn before a user discovers it by uploading a
        # scan. A silent capability gap is the failure mode the retired free
        # tier is remembered for.
        "ocr": {"available": ocr_ready, "reason": ocr_reason},
        "usd_inr_rate": pricing.USD_INR,
        "general_council_enabled": config.ENABLE_GENERAL_COUNCIL,
        "panel_tiers": {
            key: {
                "label": tier["label"],
                "description": tier["description"],
                "anonymise": tier["anonymise"],
                "allow_export": tier["allow_export"],
                "models": tier["models"],
            }
            for key, tier in config.TIERS.items()
        },
        "default_tier": config.DEFAULT_TIER,
        "zdr_enforced": config.ENFORCE_ZDR,
    }


# ---------------------------------------------------------------------------
# Compliance Panel
# ---------------------------------------------------------------------------


@router.get("/panel/config")
async def panel_config():
    """Everything the intake form needs to render."""
    return {
        "domains": available_domains(),
        "roles": [r.as_dict() for r in PANEL_ROLES],
        "tiers": [
            {
                "key": key,
                "label": tier["label"],
                "description": tier["description"],
                "anonymise": tier["anonymise"],
                "allow_export": tier["allow_export"],
                "watermark": tier["watermark"],
            }
            for key, tier in config.TIERS.items()
        ],
        "default_tier": config.DEFAULT_TIER,
        "schemas": {
            domain["key"]: get_pack(domain["key"]).intake_schema()
            for domain in available_domains()
        },
    }


@router.get("/matters")
async def list_matters(user: Dict[str, Any] = Depends(require_auth)):
    """
    Dashboard listing of all matters, worst deadline first.

    The ordering is the feature. A list sorted by creation date buries the
    matter that is overdue behind the three created after it.
    """
    matters = storage.list_matters()
    for matter in matters:
        deadlines.annotate(matter)
    matters.sort(key=deadlines.sort_key)
    if not users.can(user, "view_costs"):
        for matter in matters:
            matter.pop("usage", None)
    return matters


# Registered BEFORE /matters/{matter_id}. FastAPI resolves routes in
# declaration order, so the parameterised route would otherwise swallow this
# one and look for a matter whose id is "calendar.ics".
@router.get("/matters/calendar.ics")
async def matters_calendar(user: Dict[str, Any] = Depends(require_auth)):
    """
    Every reply deadline on file, as a calendar the firm can open.

    Served as a download rather than a subscribable feed: a live feed URL has
    to carry its own credential, and minting a long-lived token that exposes
    the client list is not a trade worth making for a self-hosted deployment.
    Re-download after adding matters.
    """
    matters = storage.list_matters()
    return Response(
        content=deadlines.build_ics(matters),
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition":
                'attachment; filename="compliance-panel-deadlines.ics"'
        },
    )


@router.get("/matters/{matter_id}")
async def get_matter(matter_id: str, user: Dict[str, Any] = Depends(require_auth)):
    """Full matter record, redacted by role."""
    matter = storage.get_matter(matter_id)
    if matter is None:
        raise HTTPException(status_code=404, detail="Matter not found")
    return redact_for_role(matter, user)


@router.delete("/matters/{matter_id}")
async def delete_matter(
    matter_id: str,
    user: Dict[str, Any] = Depends(require_permission("delete_matters")),
):
    if not storage.delete_matter(matter_id):
        raise HTTPException(status_code=404, detail="Matter not found")
    return {"status": "deleted"}


@router.post("/matters/{matter_id}/export")
@router.get("/matters/{matter_id}/export")
async def export_matter(
    matter_id: str,
    document: str = "reply",
    user: Dict[str, Any] = Depends(require_permission("export")),
):
    """
    Download one of the two documents a completed matter produces.

    `document=reply` is the filing document — signed and sent to the
    department. `document=file_note` is the internal working paper and must
    never be filed. They are separate downloads because they are separate
    documents with separate audiences, and combining them was the defect this
    endpoint was rewritten to remove.
    """
    matter = storage.get_matter(matter_id)
    if matter is None:
        raise HTTPException(status_code=404, detail="Matter not found")
    if matter.get("status") != "complete":
        raise HTTPException(status_code=400, detail="Panel has not completed for this matter")

    tier = config.get_tier(matter.get("tier"))
    if not tier["allow_export"]:
        raise HTTPException(
            status_code=403,
            detail=f"{tier['label']} output cannot be exported. Re-run this "
                   "matter on the Pro tier to export.",
        )

    if document not in ("reply", "file_note"):
        raise HTTPException(
            status_code=400,
            detail="document must be 'reply' or 'file_note'.",
        )

    # The tier's watermark reaches the filing document through the matter
    # metadata, so a draft-tier reply is stamped on every page.
    if tier.get("watermark"):
        matter.setdefault("metadata", {}).setdefault(
            "watermark", tier["watermark"])

    if document == "file_note":
        payload = export.build_file_note(matter)
        filename = export.file_note_filename(matter)
    else:
        payload = export.build_filing_reply(matter)
        filename = export.suggested_filename(matter)

    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/panel/extract")
async def extract_notice(
    files: List[UploadFile] = File(default=None),
    file: UploadFile = File(default=None),
    domain: str = "gst",
    tier: str = config.DEFAULT_TIER,
    user: Dict[str, Any] = Depends(require_auth),
):
    """
    Read one or more uploaded documents and propose a matter.

    A scrutiny notice arrives as at least two files: the one-page portal form
    carrying the reference, the provision and the reply date, and a separate
    attachment carrying the defects and their annexures. Both are accepted in
    one request, and the singular `file` field is still honoured so older
    clients keep working.

    Nothing returned here is authoritative — every field, and every defect, is
    a proposal the user confirms before the panel runs. Uploaded files are
    parsed in memory and never written to disk.
    """
    try:
        pack = get_pack(domain)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    uploads = [u for u in (files or []) if u is not None]
    if file is not None:
        uploads.append(file)
    if not uploads:
        raise HTTPException(status_code=400, detail="No file was uploaded.")

    documents = []
    for upload in uploads:
        content = await upload.read()
        if not content:
            raise HTTPException(
                status_code=400,
                detail=f"{upload.filename or 'The uploaded file'} is empty.",
            )
        documents.append((upload.filename or "", content))

    try:
        return await intake.read_notice_set(
            documents, pack, config.get_tier(tier)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Notice extraction failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="The notice could not be read. Enter the details manually.",
        )


@router.post("/panel/reconciliation")
async def upload_reconciliation(
    file: UploadFile = File(...),
    domain: str = "gst",
    tier: str = config.DEFAULT_TIER,
    user: Dict[str, Any] = Depends(require_auth),
):
    """
    Parse and bucket an uploaded reconciliation.

    Parsing, classification and aggregation all happen here, in process. The
    row data is never sent to a model and is never written to disk — only the
    aggregate summary is returned, and only that reaches the panel.
    """
    try:
        pack = get_pack(domain)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    tier_config = config.get_tier(tier)
    try:
        return reconciliation.read_reconciliation(
            file.filename or "", content, pack,
            # Supplier GSTINs are third-party data. On the anonymising tier
            # they are withheld even from the user-facing summary.
            mask_suppliers=tier_config.get("anonymise", False),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Reconciliation parsing failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="The reconciliation could not be read.",
        )


@router.post("/panel/estimate")
async def estimate_panel_cost(
    request: PanelRunRequest,
    user: Dict[str, Any] = Depends(require_auth),
):
    """
    What this run will cost, in rupees, before it is run.

    Estimated on the limbs that will actually convene counsel rather than on
    the total, because triage means most limbs do not — quoting the total
    would overstate a typical eight-limb notice roughly fourfold.
    """
    from . import defects as defects_module

    payload = request.intake or {}
    limbs = payload.get("defects") or []

    if limbs:
        panel_count = defects_module.triage(limbs)["argue_count"]
    else:
        # A matter with no limbs read off the notice still runs, as a single
        # undifferentiated issue. Estimating it at zero would be wrong in the
        # direction that matters.
        panel_count = 1

    estimate = pricing.estimate_run(
        defect_count=len(limbs),
        panel_count=panel_count,
        tier=request.tier,
        history=storage.list_matters(),
    )
    estimate["triage"] = {
        "total": len(limbs),
        "convening_counsel": panel_count,
        "answered_without_panel": max(len(limbs) - panel_count, 0),
    }
    return estimate


@router.get("/matters/{matter_id}/computations")
async def matter_computations(
    matter_id: str,
    user: Dict[str, Any] = Depends(require_auth),
):
    """
    Interest, penalty stages, pre-deposit and amnesty position for a matter.

    Computed in Python from the matter's own figures — never by a model — and
    each figure carries the working behind it so it can be checked line by
    line before it is offered to the department.
    """
    matter = storage.get_matter(matter_id)
    if matter is None:
        raise HTTPException(status_code=404, detail="Matter not found")
    return calculators.matter_computations(matter)


@router.post("/panel/run")
async def run_panel_endpoint(
    request: PanelRunRequest,
    user: Dict[str, Any] = Depends(require_auth),
):
    """Create a matter and stream the panel deliberation as SSE."""
    matter_id = str(uuid.uuid4())
    intake = request.intake or {}
    storage.create_matter(matter_id, intake, request.domain, request.tier, user)

    async def event_generator():
        try:
            yield f"data: {json.dumps({'type': 'matter_created', 'matter_id': matter_id})}\n\n"

            final = None
            async for event in run_panel_stream(
                intake,
                domain=request.domain,
                tier_name=request.tier,
                skip_verification=request.skip_verification,
            ):
                if event["type"] == "summary":
                    final = event
                yield f"data: {json.dumps(event)}\n\n"

            if final is not None:
                storage.complete_matter(
                    matter_id, final["data"], final.get("metadata", {})
                )

            yield f"data: {json.dumps({'type': 'complete', 'matter_id': matter_id})}\n\n"

        except Exception as e:
            print(f"Panel error on matter {matter_id}: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ---------------------------------------------------------------------------
# Dashboard and admin
# ---------------------------------------------------------------------------


@router.get("/dashboard")
async def dashboard(user: Dict[str, Any] = Depends(require_auth)):
    """Aggregate statistics for the landing dashboard."""
    matters = storage.list_matters()
    show_costs = users.can(user, "view_costs")

    # Deadlines lead the dashboard. A missed reply date costs more than every
    # other number here put together — it turns a reply into an appeal with a
    # pre-deposit attached.
    for matter in matters:
        deadlines.annotate(matter)
    deadline_summary = deadlines.summarise(matters)

    total_cost = 0.0
    total_tokens = 0
    verified = unverified = not_found = 0
    by_state: Dict[str, int] = {}
    by_notice: Dict[str, int] = {}
    by_confidence: Dict[str, int] = {}
    risk_flags = 0

    for matter in matters:
        usage = matter.get("usage") or {}
        total_cost += usage.get("total_cost") or 0.0
        total_tokens += usage.get("total_tokens") or 0

        summary = matter.get("verification_summary") or {}
        verified += summary.get("verified", 0)
        unverified += summary.get("unverified", 0)
        not_found += summary.get("not_found", 0)

        if matter.get("state"):
            by_state[matter["state"]] = by_state.get(matter["state"], 0) + 1
        if matter.get("notice_type"):
            by_notice[matter["notice_type"]] = by_notice.get(matter["notice_type"], 0) + 1
        if matter.get("confidence"):
            by_confidence[matter["confidence"]] = by_confidence.get(matter["confidence"], 0) + 1
        risk_flags += matter.get("risk_flag_count") or 0

    return {
        "matter_count": len(matters),
        "completed": sum(1 for m in matters if m.get("status") == "complete"),
        "risk_flags": risk_flags,
        "deadlines": deadline_summary,
        "verification": {
            "verified": verified,
            "unverified": unverified,
            "not_found": not_found,
        },
        "by_state": by_state,
        "by_notice_type": by_notice,
        "by_confidence": by_confidence,
        "usage": {
            "total_cost": round(total_cost, 4),
            "total_tokens": total_tokens,
            "total_inr": pricing.to_inr(total_cost),
            "label": pricing.format_inr(pricing.to_inr(total_cost)),
        } if show_costs else None,
        "recent": matters[:8],
    }




@router.get("/admin/users")
async def admin_list_users(
    user: Dict[str, Any] = Depends(require_permission("manage_users")),
):
    return users.list_users()


@router.post("/admin/users")
async def admin_create_user(
    request: CreateUserRequest,
    user: Dict[str, Any] = Depends(require_permission("manage_users")),
):
    try:
        return users.create_user(
            request.email, request.password, request.name, request.role
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/admin/users/{user_id}")
async def admin_update_user(
    user_id: str,
    request: UpdateUserRequest,
    user: Dict[str, Any] = Depends(require_permission("manage_users")),
):
    try:
        return users.update_user(
            user_id,
            role=request.role,
            active=request.active,
            name=request.name,
            password=request.password,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/admin/users/{user_id}")
async def admin_delete_user(
    user_id: str,
    user: Dict[str, Any] = Depends(require_permission("manage_users")),
):
    try:
        if not users.delete_user(user_id):
            raise HTTPException(status_code=404, detail="User not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "deleted"}


@router.get("/admin/settings")
async def admin_settings(
    user: Dict[str, Any] = Depends(require_permission("admin")),
):
    """Runtime configuration, for the admin panel."""
    return {
        "tiers": {
            key: {
                "label": tier["label"],
                "models": tier["models"],
                "verifier": tier["verifier"],
                "anonymise": tier["anonymise"],
                "allow_export": tier["allow_export"],
            }
            for key, tier in config.TIERS.items()
        },
        "default_tier": config.DEFAULT_TIER,
        "reasoning_effort": config.REASONING_EFFORT,
        "zdr_enforced": config.ENFORCE_ZDR,
        "request_timeout": config.REQUEST_TIMEOUT,
        "max_retries": config.MAX_RETRIES,
        "history_max_turns": config.HISTORY_MAX_TURNS,
        "data_dir": config.DATA_DIR,
        "model_validation": MODEL_VALIDATION,
        "review_note": config.EXPORT_REVIEW_NOTE,
        "firm_name": config.FIRM_NAME,
        "export_provenance": config.EXPORT_PROVENANCE,
    }


@router.get("/conversations", response_model=List[ConversationEntry])
async def list_conversations():
    """The conversation index, newest first."""
    return storage.list_conversations()


@router.post("/conversations", response_model=ConversationRecord)
async def create_conversation():
    """Open a new, empty conversation and return it."""
    return storage.create_conversation(str(uuid.uuid4()))


@router.get("/conversations/{conversation_id}", response_model=ConversationRecord)
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
async def send_message(conversation_id: str, request: CouncilQuestion):
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
async def send_message_stream(conversation_id: str, request: CouncilQuestion):
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


STATE_WRITABLE: Dict[str, Any] = {"ok": None}


async def ensure_state_dirs():
    """
    Create the persistence directories and prove they are writable.

    On a container with a misconfigured volume mount this is the difference
    between finding out at startup and finding out when a partner loses a
    deliberation they have just paid for.
    """
    paths = [config.DATA_DIR, os.path.join(config.STATE_DIR, "matters")]
    for path in paths:
        Path(path).mkdir(parents=True, exist_ok=True)

    probe = Path(config.STATE_DIR) / ".write-probe"
    try:
        probe.write_text("ok")
        probe.unlink()
        STATE_WRITABLE.update({"ok": True, "state_dir": config.STATE_DIR})
        print(f"State directory ready: {config.STATE_DIR}")
    except OSError as e:
        STATE_WRITABLE.update({"ok": False, "state_dir": config.STATE_DIR,
                               "error": str(e)})
        print(f"WARNING: {config.STATE_DIR} is not writable ({e}). "
              "Matters and user accounts cannot be saved. Check the volume mount.")


async def bootstrap_users():
    """Create the first partner account when the user store is empty."""
    try:
        users.bootstrap_admin()
    except Exception as e:
        print(f"Could not bootstrap the admin account: {e}")


async def validate_models():
    """Check configured model IDs against OpenRouter's catalog (best-effort)."""
    configured = set(config.COUNCIL_MODELS) | {config.CHAIRMAN_MODEL, config.TITLE_MODEL}
    for tier in config.TIERS.values():
        configured |= set(tier["models"].values())
        configured.add(tier["verifier"])
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
