"""Citation verification.

The single most dangerous failure mode of this product is a fabricated or
misdescribed authority reaching a signing partner. This module extracts every
authority the chairman relied on and checks it against live sources, then
labels it:

    VERIFIED    the authority exists and supports the stated proposition
    UNVERIFIED  it exists but the proposition could not be confirmed, or the
                check was inconclusive
    NOT_FOUND   no such authority could be located — treat as fabricated
                until proven otherwise

Nothing here silently upgrades a doubtful citation. When the checker itself
fails, the result is UNVERIFIED, never VERIFIED.
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from .openrouter import query_model

VERIFIED = "VERIFIED"
UNVERIFIED = "UNVERIFIED"
NOT_FOUND = "NOT_FOUND"

# Cap the checks per run so a chatty chairman cannot blow up latency or cost.
MAX_AUTHORITIES = 25


def extract_citations(text: str, pack) -> List[str]:
    """Pull candidate citations out of free text using the pack's patterns."""
    if not text:
        return []
    found: List[str] = []
    seen = set()
    for pattern in pack.CITATION_PATTERNS:
        for match in pattern.finditer(text):
            citation = match.group(0).strip(" .,;:")
            key = re.sub(r"\s+", " ", citation).lower()
            if len(citation) < 6 or key in seen:
                continue
            seen.add(key)
            found.append(citation)
    return found


def collect_authorities(determination: Dict[str, Any], pack) -> List[Dict[str, str]]:
    """
    Gather everything that needs checking.

    Primary source is the chairman's structured `authorities` list. Anything
    cited in the draft reply or in issue analysis but missing from that list
    is also picked up — a citation that reaches the client's reply without
    appearing in the authorities table is exactly the one that gets missed.
    """
    authorities: List[Dict[str, str]] = []
    seen = set()

    def add(citation: str, proposition: str, source: str, certainty: str = ""):
        citation = (citation or "").strip()
        if not citation:
            return
        key = re.sub(r"\s+", " ", citation).lower()
        if key in seen:
            return
        seen.add(key)
        authorities.append({
            "citation": citation,
            "proposition": (proposition or "").strip(),
            "source": source,
            "certainty": certainty or "asserted",
        })

    for item in determination.get("authorities") or []:
        if isinstance(item, dict):
            add(item.get("citation", ""), item.get("proposition", ""),
                "authorities_table", item.get("certainty", "asserted"))
        elif isinstance(item, str):
            add(item, "", "authorities_table")

    scan_targets = [determination.get("draft_reply", "")]
    for issue in determination.get("issues") or []:
        if isinstance(issue, dict):
            scan_targets.append(issue.get("authority", ""))
    scan_targets.append(determination.get("lead_argument", ""))

    for text in scan_targets:
        for citation in extract_citations(text or "", pack):
            add(citation, "", "draft_body")

    return authorities[:MAX_AUTHORITIES]


def _build_check_prompt(authorities: List[Dict[str, str]], pack) -> str:
    listing = "\n".join(
        f'{i + 1}. CITATION: {a["citation"]}\n   CITED FOR: {a["proposition"] or "(not stated)"}'
        for i, a in enumerate(authorities)
    )
    return f"""\
You are a legal research verifier for an Indian chartered accountancy firm
working on a {pack.SHORT_NAME} matter. Your ONLY job is to check whether each
authority below actually exists and whether it says what it is cited for.

Search the web for each one. Be sceptical: AI-generated legal drafts routinely
contain citations that look plausible and do not exist. Finding nothing is a
legitimate and important result.

Rules:
- "{VERIFIED}" ONLY if you found the authority AND it supports the stated
  proposition (or, where no proposition is stated, the authority plainly
  exists in the form cited).
- "{UNVERIFIED}" if it appears to exist but you could not confirm the
  proposition, the citation details differ, it has been overruled or is under
  challenge, or your search was inconclusive.
- "{NOT_FOUND}" if you could not locate it at all. Do not guess that an
  authority probably exists because the name sounds right.
- For statutory provisions (sections, rules), verify the provision exists in
  the relevant Act/Rules and broadly covers the proposition.
- For circulars and notifications, verify the number and date.
- NEVER mark something {VERIFIED} to be helpful. An incorrect {VERIFIED} is
  worse than every other outcome, because it removes the reviewer's warning.

AUTHORITIES TO CHECK:
{listing}

Return a SINGLE JSON object and nothing else:

{{
  "results": [
    {{
      "index": 1,
      "status": "{VERIFIED}" | "{UNVERIFIED}" | "{NOT_FOUND}",
      "note": "one sentence: what you found, or why you could not confirm it",
      "correction": "the correct citation if the one given is wrong, else empty"
    }}
  ]
}}"""


def _parse_results(text: str) -> Optional[List[Dict[str, Any]]]:
    if not text:
        return None
    candidates = [text]
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        candidates.insert(0, fence.group(1))
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        results = payload.get("results")
        if isinstance(results, list):
            return results
    return None


async def verify_authorities(
    determination: Dict[str, Any],
    pack,
    verifier_model: str,
) -> Tuple[Dict[str, Any], List[Optional[Dict[str, Any]]]]:
    """
    Check every authority in the determination against live sources.

    Returns (verification_payload, usage_list).
    """
    authorities = collect_authorities(determination, pack)

    if not authorities:
        return {
            "checked": True,
            "authorities": [],
            "summary": {"verified": 0, "unverified": 0, "not_found": 0, "total": 0},
            "note": "The determination cited no authorities. For a tax reply "
                    "that is itself a finding worth questioning.",
        }, []

    result = await query_model(
        verifier_model,
        [{"role": "user", "content": _build_check_prompt(authorities, pack)}],
        web_search=True,
    )
    usage = [result.get("usage") if result.get("ok") else None]

    checked: List[Dict[str, Any]] = []

    if not result.get("ok"):
        # The checker itself failed. Everything stays UNVERIFIED — never
        # upgrade on failure.
        for a in authorities:
            checked.append({**a, "status": UNVERIFIED,
                            "note": f"Verification unavailable: {result.get('error')}",
                            "correction": ""})
        return {
            "checked": False,
            "authorities": checked,
            "summary": {"verified": 0, "unverified": len(checked),
                        "not_found": 0, "total": len(checked)},
            "note": "The verification service could not be reached. Every "
                    "authority must be checked manually before filing.",
        }, usage

    parsed = _parse_results(result["content"])
    by_index = {}
    if parsed:
        for entry in parsed:
            try:
                by_index[int(entry.get("index"))] = entry
            except (TypeError, ValueError):
                continue

    valid_statuses = {VERIFIED, UNVERIFIED, NOT_FOUND}
    for i, authority in enumerate(authorities, start=1):
        entry = by_index.get(i, {})
        status = str(entry.get("status", "")).upper().strip()
        if status not in valid_statuses:
            status = UNVERIFIED
        # A citation the panel itself flagged can never come back clean.
        if authority.get("certainty") == "to_verify" and status == VERIFIED:
            status = UNVERIFIED
        checked.append({
            **authority,
            "status": status,
            "note": entry.get("note", "") or "No verification note returned.",
            "correction": entry.get("correction", "") or "",
        })

    summary = {
        "verified": sum(1 for c in checked if c["status"] == VERIFIED),
        "unverified": sum(1 for c in checked if c["status"] == UNVERIFIED),
        "not_found": sum(1 for c in checked if c["status"] == NOT_FOUND),
        "total": len(checked),
    }

    return {
        "checked": True,
        "authorities": checked,
        "summary": summary,
        "verifier_model": verifier_model,
        "note": (
            f"{summary['not_found']} authority(ies) could not be located and "
            "must be removed or replaced before filing."
            if summary["not_found"] else
            "No fabricated authorities detected. Items marked UNVERIFIED still "
            "require manual confirmation."
        ),
    }, usage
