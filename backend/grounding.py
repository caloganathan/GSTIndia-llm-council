"""Current-law briefing.

A model arguing GST from training data alone is arguing from a frozen
snapshot, and in GST the things that move are exactly the things in dispute:
amnesty windows under s.128A, GSTAT procedure, retrospective ITC relief under
s.16(5)/(6), rate changes, and limitation extensions under s.168A. A counsel
that computes limitation without knowing an extension notification issued last
quarter has computed it wrongly, however good the reasoning.

Citation verification does not close this. It confirms an authority exists; it
does not, on its own, tell the panel that the position moved after the model
was trained.

So the panel opens with ONE web-grounded briefing, shared by every counsel:

- one search per run rather than one per counsel, which is cheaper and keeps
  the whole panel arguing from the same facts;
- capped output, because this is orientation and not analysis;
- explicitly permitted to return "nothing material has changed", which is the
  correct answer most of the time and must not be padded.

Failure here is never fatal. If the briefing cannot be produced the panel runs
without it, and says so, rather than blocking the matter.
"""

from typing import Any, Dict, Optional, Tuple

from . import config
from .openrouter import query_model

# Marker the briefing model returns when the settled position still holds.
NO_CHANGE = "NO MATERIAL CHANGE"


def build_briefing_prompt(matter: Dict[str, Any], pack) -> str:
    """Ask only about what is actually in issue in this matter."""
    notice = pack.NOTICE_TYPES.get(
        matter.get("notice_type"), pack.NOTICE_TYPES.get("OTHER")
    )
    facets = [
        f"Notice type: {notice.code} — {notice.name}",
        f"Statutory basis: {notice.statute}",
    ]
    for label, key in (
        ("Provision invoked", "section_invoked"),
        ("Tax period", "tax_period"),
        ("State", "state"),
    ):
        if matter.get(key):
            facets.append(f"{label}: {matter[key]}")

    issues = (matter.get("issues") or "").strip()
    issues_block = f"\nIssues raised in the notice:\n{issues}\n" if issues else ""

    return f"""\
You are a tax research assistant for an Indian chartered accountancy firm.
Search the web and report ONLY what a practitioner must know about the CURRENT
position before arguing the matter below. This is orientation for counsel, not
analysis — do not argue the matter.

{chr(10).join(facets)}
{issues_block}
Report, for {pack.SHORT_NAME} as it stands today:

1.  AMENDMENTS to the provisions in issue that affect this tax period,
    including any retrospective operation.
2.  CIRCULARS, NOTIFICATIONS OR INSTRUCTIONS issued or withdrawn that bear on
    these issues. Give number and date.
3.  LIMITATION — any extension notification (for example under section 168A)
    applicable to this period, and whether its validity is itself under
    challenge.
4.  AMNESTY OR RELIEF schemes open for this period, with the operative dates.
5.  PROCEDURAL CHANGES to the forum: appellate procedure, tribunal
    constitution and functioning, filing requirements.
6.  RECENT JUDICIAL DEVELOPMENTS that a practitioner would be expected to
    know — including any decision that has unsettled a previously settled
    position.

Rules:
- Give DATES for everything. A practitioner cannot rely on "recently".
- State only what you actually found. Do not infer, and do not fill gaps with
  what you expect to be true.
- If you find nothing material, reply with exactly "{NO_CHANGE}" and stop.
  That is a correct and useful answer — padding it is not.
- Be brief. Six short points at most, one or two sentences each.
- If a source conflicts with another, say so rather than picking one."""


def _tier_grounding_model(tier: Dict[str, Any]) -> str:
    return tier.get("grounding") or tier.get("verifier") or ""


async def build_briefing(
    matter: Dict[str, Any],
    pack,
    tier: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Produce the current-law briefing for this matter.

    Returns (briefing, usage). `briefing` is None when grounding is disabled
    or unavailable — the panel then proceeds ungrounded and records that.
    """
    if not config.PANEL_WEB_GROUNDING:
        return None, None

    model = _tier_grounding_model(tier)
    if not model:
        return None, None

    result = await query_model(
        model,
        [{"role": "user", "content": build_briefing_prompt(matter, pack)}],
        effort=config.role_effort("briefing"),
        max_tokens=config.role_max_tokens("briefing"),
        web_search=True,
        web_max_results=config.WEB_MAX_RESULTS,
    )

    if not result.get("ok"):
        return {
            "available": False,
            "model": model,
            "error": result.get("error", "unknown"),
            "content": "",
        }, None

    content = (result.get("content") or "").strip()
    material = bool(content) and NO_CHANGE.lower() not in content.lower()

    return {
        "available": True,
        "model": model,
        "content": content,
        "material_change": material,
    }, result.get("usage")


def briefing_block(briefing: Optional[Dict[str, Any]]) -> str:
    """
    Render the briefing for injection into a counsel prompt.

    When grounding was unavailable the counsel is told so explicitly, rather
    than being left to assume its training data is current. A counsel that
    knows it is working blind argues more carefully.
    """
    if briefing is None:
        return ""

    if not briefing.get("available"):
        return """\
CURRENT-LAW BRIEFING: unavailable for this run.

Your training data may be out of date on amendments, circulars, limitation
extensions and amnesty windows. Where your argument depends on the current
position, mark the point "[VERIFY CURRENT POSITION]" so the reviewer checks it
before filing. Do not present a possibly-stale position as settled.
"""

    if not briefing.get("material_change"):
        return """\
CURRENT-LAW BRIEFING: a search of current sources found no material change to
the provisions in issue for this period. Argue the settled position.
"""

    return f"""\
CURRENT-LAW BRIEFING (from a search of current sources, for this matter):

{briefing['content']}

This briefing takes precedence over your training data wherever the two
conflict. If it shows a provision was amended, a circular withdrawn, or
limitation extended, argue the position as it now stands and say so.
"""
