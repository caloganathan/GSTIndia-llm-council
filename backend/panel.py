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

from . import config, defects, grounding, sanitizer
from .domains import get_pack
from .openrouter import query_model
from .roles import (
    CHAIRMAN_KEY,
    CHAIRMAN_TITLE,
    PANEL_ROLES,
    build_chairman_prompt,
    build_cross_exam_prompt,
    build_role_prompt,
    format_matter,
)
from .verification import VERIFIED, verify_authorities


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
        "preliminary_submissions": "",
        "defects": [],
        "panel_disagreements": [],
        "unstructured_output": raw_text or "",
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


# Keys the chairman may return for a defect that overwrite what intake read.
# Deliberately narrow: the department's own heading, numbering and head-wise
# figures come off the notice and are NOT the chairman's to revise. A model
# that rounds "Rs. 1,16,732" to "Rs. 1.17 lakh" in the reply has introduced an
# error into a document that will be read against the department's annexure.
_CHAIRMAN_DEFECT_KEYS = (
    "posture", "strength", "our_position", "facts", "submission",
    "department_contention", "legal_framework", "authorities",
    "evidence_required", "evidence_gap", "annexures", "payment", "splits",
    "prayer_relief", "amount_note",
)

# The shape each structured key must arrive in. A model asked for an object
# routinely answers with a sentence — "Rs. 2,300 paid vide DRC-03 dated
# 26/06/2026" instead of {"reference": ..., "date": ...} — and the cheap
# models on the draft tier do it more often. Accepting that verbatim put a
# string where the export indexes a mapping, and the filing reply then raised
# mid-response: the download died as "Failed to fetch" with nothing in the UI
# to say why. A value of the wrong shape is dropped here rather than carried
# forward, so the limb keeps what intake read and the reply still builds.
_CHAIRMAN_DEFECT_SHAPES = {
    "payment": dict,
    "legal_framework": list,
    "authorities": list,
    "evidence_required": list,
    "evidence_gap": list,
    "annexures": list,
    "splits": list,
}


def merge_determination(
    intake_defects: List[Dict[str, Any]],
    determination: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Fold the chairman's per-defect determination onto the defects read from
    the notice.

    The notice is authoritative on WHAT was alleged — the heading, the
    department's numbering, and the head-wise figures. The chairman is
    authoritative on WHAT WE SAY ABOUT IT. Keeping that boundary is what stops
    a drafting model from quietly restating the department's own arithmetic
    wrongly in a document filed against that arithmetic.

    A defect the chairman did not answer is left with its triage posture and
    flagged, rather than dropped: a limb missing from the reply is a limb the
    officer confirms unopposed.
    """
    merged = [dict(d) for d in (intake_defects or [])]
    by_index = {d.get("index"): d for d in merged}

    answered = set()
    for entry in determination.get("defects") or []:
        if not isinstance(entry, dict):
            continue
        target = by_index.get(entry.get("index"))
        if target is None:
            # The chairman raised a limb intake did not find. Keep it — an
            # extra defect is a reviewable proposal; a lost one is a hole in
            # the reply.
            target = defects.new_defect(
                index=entry.get("index") or (len(merged) + 1),
                heading=entry.get("heading") or "Additional defect",
                defect_type="other",
                source="panel",
            )
            merged.append(target)
            by_index[target["index"]] = target

        for key in _CHAIRMAN_DEFECT_KEYS:
            if entry.get(key) in (None, "", [], {}):
                continue
            shape = _CHAIRMAN_DEFECT_SHAPES.get(key)
            if shape is not None and not isinstance(entry[key], shape):
                continue
            target[key] = entry[key]

        if target.get("posture") not in defects.POSTURES:
            target["posture"] = defects.UNDECIDED
        answered.add(target["index"])

    for defect in merged:
        if defect["index"] not in answered:
            defect["unanswered"] = True

    merged.sort(key=lambda d: (d.get("index") or 0))
    return merged


def filed_text_blockers(verification: Dict[str, Any]) -> List[str]:
    """
    Blockers for citations found in the filed prose that did not verify.

    The structured `authorities` and `legal_framework` lists are gated at
    export — an entry that fails verification is simply withheld. A citation
    the chairman wrote INTO a submission paragraph cannot be withheld without
    rewriting the paragraph, so it must be surfaced as a blocker the reviewer
    resolves by hand: confirm it against the reported text, or strike it from
    the prose before filing.
    """
    blockers: List[str] = []
    for authority in verification.get("authorities") or []:
        if authority.get("source") != "filed_text":
            continue
        if authority.get("status") == VERIFIED:
            continue
        where = (
            f"defect {authority['defect_index']}"
            f" ({authority.get('defect_heading') or 'unheaded'})"
            if authority.get("defect_index") is not None
            else "the preliminary or general text of the reply"
        )
        blockers.append(
            f"The reply text for {where} cites an authority that did not "
            f"verify: {authority.get('citation')} "
            f"[{authority.get('status', 'UNCHECKED')}]. Confirm it against "
            "the reported text or remove it from the prose before filing — "
            "it cannot be withheld automatically because it sits inside a "
            "filed paragraph."
        )
    return blockers


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
    # On the anonymising tier this is not optional and not skippable.
    replacements: Dict[str, str] = {}
    working_matter = matter
    if tier["anonymise"]:
        working_matter, replacements = sanitizer.sanitize_matter(matter)
        # Audit the text as the models will actually receive it — the full
        # rendered matter block, defects and all — not a hand-picked subset of
        # fields. A probe narrower than the prompt is a probe that passes the
        # exact leak it exists to catch.
        leak_probe = format_matter(working_matter, pack)
        leaks = sanitizer.audit_leaks(leak_probe,
                                      client_name=matter.get("client_name"))
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

    # Reconciliation, if the user attached one. Already bucketed and
    # aggregated locally — this is a few hundred tokens of summary, never the
    # underlying rows.
    recon_text = ""
    reconciliation = working_matter.get("reconciliation")
    if reconciliation:
        recon_text = pack.reconciliation_brief(reconciliation)

    # ---- Stage 1: opening analyses ---------------------------------------
    yield {"type": "stage1_start"}

    async def run_counsel(role):
        prompt = build_role_prompt(role, working_matter, pack,
                                   briefing_text, recon_text)
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
        working_matter, pack, analyses, cross_exams, briefing_text,
        recon_text,
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

    # Fold the determination back onto the defects read from the notice, so
    # everything downstream — export, validation, the eval harness — works from
    # one reconciled list rather than two half-lists that disagree.
    determination["defects"] = merge_determination(
        working_matter.get("defects") or [], determination,
    )
    determination["triage"] = defects.triage(determination["defects"])
    determination["filing_blockers"] = defects.validate_all(
        determination["defects"]
    )
    unanswered = [d for d in determination["defects"] if d.get("unanswered")]
    if unanswered:
        determination.setdefault("risk_flags", []).insert(0, (
            f"{len(unanswered)} defect(s) raised in the notice were not "
            "answered by the panel: "
            + "; ".join(str(d.get("heading")) for d in unanswered)
            + ". A limb left unanswered is a limb the officer confirms "
              "unopposed. Settle these before filing."
        ))

    yield {"type": "stage3_complete", "data": determination}

    # ---- Stage 4: citation verification ----------------------------------
    verification: Dict[str, Any] = {"checked": False, "authorities": []}
    verify_usage: List[Optional[Dict[str, Any]]] = []

    if not skip_verification:
        yield {"type": "verification_start"}
        verification, verify_usage = await verify_authorities(
            determination, pack, tier["verifier"], zdr=zdr,
        )
        yield {"type": "verification_complete", "data": verification}

        # A citation embedded in the filed prose is more dangerous than one in
        # the authorities table: the table is gated at export, the prose is
        # printed verbatim. Any prose citation that did not come back VERIFIED
        # becomes a filing blocker, so it leads section 1 of the file note and
        # stamps the filing document until it is resolved.
        prose_blockers = filed_text_blockers(verification)
        if prose_blockers:
            determination.setdefault("filing_blockers", []).extend(prose_blockers)

    # ---- Restore identifiers locally (anonymising tier only) -------------
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
            "reconciled": bool(reconciliation),
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
