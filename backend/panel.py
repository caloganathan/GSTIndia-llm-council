"""Adversarial compliance panel orchestration.

Four counsel argue, cross-examine, and a chairman determines. Structurally
identical across domains — only the injected domain pack changes, which is
what makes adding the Income Tax pack a matter of days rather than weeks.

Stages
    0  current-law briefing: one shared web search, so counsel do not argue
       from a training snapshot on provisions that have since moved
    1  opening analyses, in parallel
    2  cross-examination: each counsel attacks the other three
    3  chairman determination, returned as structured JSON
    4  citation verification against live sources
"""

import asyncio
import json
import re
from typing import Any, AsyncGenerator, Dict, List, Optional

from . import config, grounding, sanitizer
from .domains import get_pack
from .openrouter import query_model
from .roles import (
    CHAIRMAN_KEY,
    CHAIRMAN_TITLE,
    PANEL_ROLES,
    build_chairman_prompt,
    build_cross_exam_prompt,
    build_role_prompt,
)
from .verification import verify_authorities


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Pull the chairman's JSON object out of whatever wrapping it used."""
    if not text:
        return None

    # Straight parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fenced block
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass

    # First balanced object in the text
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _fallback_determination(raw_text: str, error: str = "") -> Dict[str, Any]:
    """Chairman returned unusable output — degrade honestly, never silently."""
    return {
        "recommended_position": (
            "The panel could not produce a structured determination. "
            "The counsel analyses above remain valid and should be read directly. "
            f"{error}".strip()
        ),
        "confidence": "insufficient_information",
        "lead_argument": "",
        "issues": [],
        "panel_disagreements": [],
        "draft_reply": raw_text or "",
        "authorities": [],
        "risk_flags": [
            "Chairman synthesis failed — this output has NOT been through "
            "partner-level determination and must not be filed."
        ],
        "documents_to_collect": [],
        "board_summary": "",
        "working_note": "",
        "open_questions": ["Re-run the panel; chairman output was unparseable."],
        "_degraded": True,
    }


def _usage_of(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return result.get("usage") if result.get("ok") else None


def _sum_usage(*groups: List[Optional[Dict[str, Any]]]) -> Dict[str, Any]:
    tokens = 0
    cost = 0.0
    for group in groups:
        for usage in group:
            if not usage:
                continue
            tokens += usage.get("total_tokens") or 0
            cost += usage.get("cost") or 0.0
    return {"total_tokens": tokens, "total_cost": round(cost, 6)}


async def run_panel_stream(
    matter: Dict[str, Any],
    domain: str = "gst",
    tier_name: str = None,
    skip_verification: bool = False,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Run the panel, yielding an event per stage.

    Events: panel_start, stage1_start, counsel_complete, stage1_complete,
    stage2_start, stage2_complete, stage3_start, stage3_complete,
    verification_start, verification_complete, summary, error.
    """
    pack = get_pack(domain)
    tier = config.get_tier(tier_name)
    models = tier["models"]
    zdr = config.ENFORCE_ZDR and not tier["anonymise"]

    # ---- Privacy gate -----------------------------------------------------
    # On the free tier this is not optional and not skippable.
    replacements: Dict[str, str] = {}
    working_matter = matter
    if tier["anonymise"]:
        working_matter, replacements = sanitizer.sanitize_matter(matter)
        leak_probe = " ".join(
            str(working_matter.get(f) or "")
            for f in ("issues", "facts", "documents_available")
        )
        leaks = sanitizer.audit_leaks(leak_probe)
        if leaks:
            yield {
                "type": "error",
                "message": (
                    "Anonymisation failed — identifiers still present "
                    f"({', '.join(leaks)}). Aborting before any request left "
                    "this machine. Use the Pro tier for full-fact analysis."
                ),
            }
            return

    yield {
        "type": "panel_start",
        "tier": tier["key"],
        "tier_label": tier["label"],
        "anonymised": tier["anonymise"],
        "domain": domain,
        "roles": [r.as_dict() for r in PANEL_ROLES],
    }

    # ---- Stage 0: current-law briefing -----------------------------------
    # One web-grounded search, shared by every counsel. Cheaper than grounding
    # each seat separately, and it keeps the whole panel arguing from the same
    # facts. Never fatal: if it fails, counsel are told they are working blind.
    briefing: Optional[Dict[str, Any]] = None
    briefing_usage: List[Optional[Dict[str, Any]]] = []

    if config.PANEL_WEB_GROUNDING:
        yield {"type": "grounding_start"}
        briefing, usage = await grounding.build_briefing(working_matter, pack, tier)
        briefing_usage.append(usage)
        yield {"type": "grounding_complete", "data": briefing}

    briefing_text = grounding.briefing_block(briefing)

    # ---- Stage 1: opening analyses ---------------------------------------
    yield {"type": "stage1_start"}

    async def run_counsel(role):
        prompt = build_role_prompt(role, working_matter, pack, briefing_text)
        result = await query_model(
            models.get(role.key, models["chairman"]),
            [{"role": "user", "content": prompt}],
            zdr=zdr,
            effort=config.role_effort(role.key),
            max_tokens=config.role_max_tokens("opening"),
        )
        return role, result

    stage1_raw = await asyncio.gather(*[run_counsel(r) for r in PANEL_ROLES])

    analyses: List[Dict[str, str]] = []
    stage1_failures: List[Dict[str, str]] = []
    stage1_usage: List[Optional[Dict[str, Any]]] = []

    for role, result in stage1_raw:
        stage1_usage.append(_usage_of(result))
        if result.get("ok"):
            analyses.append({
                "key": role.key,
                "title": role.title,
                "short_title": role.short_title,
                "model": result.get("model"),
                "analysis": result["content"],
            })
        else:
            stage1_failures.append({
                "role": role.title,
                "model": models.get(role.key),
                "error": result.get("error", "unknown"),
            })

    yield {
        "type": "stage1_complete",
        "data": analyses,
        "failures": stage1_failures,
    }

    if not analyses:
        yield {
            "type": "error",
            "message": "Every counsel failed. Check model IDs at /api/health "
                       "and your OpenRouter credits.",
        }
        return

    # ---- Stage 2: cross-examination --------------------------------------
    cross_exams: List[Dict[str, str]] = []
    stage2_failures: List[Dict[str, str]] = []
    stage2_usage: List[Optional[Dict[str, Any]]] = []

    if len(analyses) >= 2:
        yield {"type": "stage2_start"}

        async def run_cross(entry):
            role = next(r for r in PANEL_ROLES if r.key == entry["key"])
            peers = [a for a in analyses if a["key"] != entry["key"]]
            prompt = build_cross_exam_prompt(role, working_matter, pack, peers)
            result = await query_model(
                models.get(role.key, models["chairman"]),
                [{"role": "user", "content": prompt}],
                zdr=zdr,
                effort=config.role_effort("cross_exam"),
                max_tokens=config.role_max_tokens("cross_exam"),
            )
            return role, result

        stage2_raw = await asyncio.gather(*[run_cross(a) for a in analyses])

        for role, result in stage2_raw:
            stage2_usage.append(_usage_of(result))
            if result.get("ok"):
                cross_exams.append({
                    "key": role.key,
                    "title": role.title,
                    "short_title": role.short_title,
                    "model": result.get("model"),
                    "analysis": result["content"],
                })
            else:
                stage2_failures.append({
                    "role": role.title,
                    "model": models.get(role.key),
                    "error": result.get("error", "unknown"),
                })

        yield {
            "type": "stage2_complete",
            "data": cross_exams,
            "failures": stage2_failures,
        }

    # ---- Stage 3: chairman determination ---------------------------------
    yield {"type": "stage3_start"}

    chairman_prompt = build_chairman_prompt(
        working_matter, pack, analyses, cross_exams, briefing_text
    )
    chairman_result = await query_model(
        models["chairman"],
        [{"role": "user", "content": chairman_prompt}],
        zdr=zdr,
        effort=config.role_effort("chairman"),
        max_tokens=config.role_max_tokens("chairman"),
    )
    chairman_usage = [_usage_of(chairman_result)]

    if chairman_result.get("ok"):
        determination = _extract_json(chairman_result["content"])
        if determination is None:
            determination = _fallback_determination(
                chairman_result["content"],
                "The chairman did not return parseable JSON.",
            )
    else:
        determination = _fallback_determination(
            "", f"Chairman call failed: {chairman_result.get('error')}"
        )

    determination["_chairman_model"] = models["chairman"]
    yield {"type": "stage3_complete", "data": determination}

    # ---- Stage 4: citation verification ----------------------------------
    verification: Dict[str, Any] = {"checked": False, "authorities": []}
    verify_usage: List[Optional[Dict[str, Any]]] = []

    if not skip_verification:
        yield {"type": "verification_start"}
        verification, verify_usage = await verify_authorities(
            determination, pack, tier["verifier"]
        )
        yield {"type": "verification_complete", "data": verification}

    # ---- Restore identifiers locally (free tier only) --------------------
    if replacements:
        analyses = sanitizer.restore_structure(analyses, replacements)
        cross_exams = sanitizer.restore_structure(cross_exams, replacements)
        determination = sanitizer.restore_structure(determination, replacements)

    usage = _sum_usage(briefing_usage, stage1_usage, stage2_usage,
                       chairman_usage, verify_usage)

    yield {
        "type": "summary",
        "data": {
            "analyses": analyses,
            "cross_exams": cross_exams,
            "determination": determination,
            "verification": verification,
            "briefing": briefing,
        },
        "metadata": {
            "domain": domain,
            "tier": tier["key"],
            "tier_label": tier["label"],
            "anonymised": tier["anonymise"],
            "allow_export": tier["allow_export"],
            "watermark": tier["watermark"],
            "models": models,
            "grounded": bool(briefing and briefing.get("available")),
            "failures": {"stage1": stage1_failures, "stage2": stage2_failures},
            "usage": usage,
        },
    }


async def run_panel(
    matter: Dict[str, Any],
    domain: str = "gst",
    tier_name: str = None,
    skip_verification: bool = False,
) -> Dict[str, Any]:
    """Non-streaming wrapper: returns the summary payload."""
    final: Dict[str, Any] = {}
    async for event in run_panel_stream(matter, domain, tier_name, skip_verification):
        if event["type"] == "summary":
            final = {"data": event["data"], "metadata": event["metadata"]}
        elif event["type"] == "error":
            final = {"error": event["message"]}
    return final
