"""Citation verification.

The single most dangerous failure mode of this product is a fabricated or
misdescribed authority reaching a signing partner. This module extracts every
authority the chairman relied on and checks it against live sources, then
labels it:

    VERIFIED    exists, supports the stated proposition, and is still good law
    SUPERSEDED  exists, but has been amended, withdrawn, overruled or stayed —
                the quiet killer, because a stale authority reads as a sound
                one and a verifier that only asks "does this exist?" passes it
    UNVERIFIED  exists but the proposition could not be confirmed, or the check
                was inconclusive
    NOT_FOUND   no such authority could be located — treat as fabricated until
                proven otherwise

Nothing here silently upgrades a doubtful citation. When the checker itself
fails, the result is UNVERIFIED, never VERIFIED.
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from . import config
from .openrouter import query_model

VERIFIED = "VERIFIED"
SUPERSEDED = "SUPERSEDED"
UNVERIFIED = "UNVERIFIED"
NOT_FOUND = "NOT_FOUND"

# Statuses that must never reach a filing without a reviewer touching them.
ACTIONABLE = (SUPERSEDED, UNVERIFIED, NOT_FOUND)

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

    Primary source is each defect's structured `authorities` list. Anything
    cited in filed text — the submissions, the factual answers, the legal
    framework tables — but missing from those lists is also picked up. A
    citation that reaches the officer's desk without appearing in any
    authorities list is exactly the one that gets missed, and it is the one
    that matters.

    Every authority carries the defect it belongs to, so the export can put
    verified authority into the filing document and route the rest to the
    internal file note rather than caveating the filed reply.
    """
    authorities: List[Dict[str, str]] = []
    seen = set()

    def add(citation: str, proposition: str, source: str, certainty: str = "",
            defect_index=None, defect_heading: str = ""):
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
            "defect_index": defect_index,
            "defect_heading": defect_heading,
        })

    for item in determination.get("authorities") or []:
        if isinstance(item, dict):
            add(item.get("citation", ""), item.get("proposition", ""),
                "authorities_table", item.get("certainty", "asserted"))
        elif isinstance(item, str):
            add(item, "", "authorities_table")

    for defect in determination.get("defects") or []:
        if not isinstance(defect, dict):
            continue
        index = defect.get("index")
        heading = defect.get("heading", "")

        for item in defect.get("authorities") or []:
            if isinstance(item, dict):
                add(item.get("citation", ""), item.get("proposition", ""),
                    "defect", item.get("certainty", "asserted"), index, heading)
            elif isinstance(item, str):
                add(item, "", "defect", "asserted", index, heading)

        for entry in defect.get("legal_framework") or []:
            if isinstance(entry, dict):
                add(entry.get("provision", ""), entry.get("relevance", ""),
                    "legal_framework", "asserted", index, heading)

        # Filed text, scanned for anything cited but not listed.
        for field in ("submission", "facts", "our_position"):
            for citation in extract_citations(defect.get(field) or "", pack):
                add(citation, "", "filed_text", "asserted", index, heading)

    for field in ("preliminary_submissions", "lead_argument",
                  "unstructured_output"):
        for citation in extract_citations(determination.get(field) or "", pack):
            add(citation, "", "filed_text")

    return authorities[:MAX_AUTHORITIES]


def _build_check_prompt(authorities: List[Dict[str, str]], pack) -> str:
    listing = "\n".join(
        f'{i + 1}. CITATION: {a["citation"]}\n   CITED FOR: {a["proposition"] or "(not stated)"}'
        for i, a in enumerate(authorities)
    )
    return f"""\
You are a legal research verifier for an Indian chartered accountancy firm
working on a {pack.SHORT_NAME} matter. Your job is to check, for each
authority below, THREE things:

    (a) does it exist, in the form cited?
    (b) does it say what it is cited for?
    (c) IS IT STILL GOOD LAW TODAY?

(c) is the one people skip, and it is the one that causes real damage. A
circular that was withdrawn last quarter, a decision since reversed on appeal,
a provision amended with retrospective effect, a notification whose validity
has been stayed — each of these reads exactly like sound authority and will be
filed unless you catch it. Search for the current status, not just the
original text.

Be sceptical throughout: AI-generated legal drafts routinely contain citations
that look plausible and do not exist. Finding nothing is a legitimate and
important result.

Assign exactly one status:
- "{VERIFIED}" — found, supports the proposition, AND still good law. All
  three. If you did not check currency, it is not {VERIFIED}.
- "{SUPERSEDED}" — it exists, but has been amended, withdrawn, replaced,
  overruled, reversed, distinguished into irrelevance, or stayed. Say what
  replaced it and from when.
- "{UNVERIFIED}" — appears to exist but you could not confirm the proposition,
  the citation details differ, or your search was inconclusive.
- "{NOT_FOUND}" — you could not locate it at all. Do not assume an authority
  exists because the name sounds right.

Also:
- For statutory provisions, check for amendments affecting the period in
  issue, including retrospective ones.
- For circulars and notifications, verify number and date, and whether it has
  since been superseded or withdrawn.
- NEVER mark something {VERIFIED} to be helpful. An incorrect {VERIFIED} is
  worse than every other outcome, because it removes the reviewer's warning.

AUTHORITIES TO CHECK:
{listing}

Return a SINGLE JSON object and nothing else:

{{
  "results": [
    {{
      "index": 1,
      "status": "{VERIFIED}" | "{SUPERSEDED}" | "{UNVERIFIED}" | "{NOT_FOUND}",
      "note": "one sentence: what you found, or why you could not confirm it",
      "as_of": "the date or period your finding is current as at, if known",
      "correction": "the citation that now governs, if this one is superseded or wrong; else empty"
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


def _summary_note(summary: Dict[str, int]) -> str:
    """One sentence naming the most serious problem found."""
    problems = []
    if summary.get("not_found"):
        problems.append(
            f"{summary['not_found']} could not be located and must be removed "
            "or replaced before filing"
        )
    if summary.get("superseded"):
        problems.append(
            f"{summary['superseded']} no longer represent the current position "
            "and must not be relied on as cited"
        )
    if problems:
        return "Of the authorities checked, " + "; ".join(problems) + "."
    if summary.get("unverified"):
        return ("No fabricated or superseded authorities detected. Items marked "
                "UNVERIFIED still require manual confirmation before filing.")
    return "All authorities were traced, support the propositions cited, and " \
           "appear to remain good law."


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
            "summary": {"verified": 0, "superseded": 0, "unverified": 0,
                        "not_found": 0, "total": 0},
            "note": "The determination cited no authorities. For a tax reply "
                    "that is itself a finding worth questioning.",
        }, []

    result = await query_model(
        verifier_model,
        [{"role": "user", "content": _build_check_prompt(authorities, pack)}],
        web_search=True,
        web_max_results=config.WEB_MAX_RESULTS,
        # Lookup and comparison, not legal reasoning — do not pay for effort here.
        effort=config.role_effort("verifier"),
        max_tokens=config.role_max_tokens("verifier"),
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
            "summary": {"verified": 0, "superseded": 0,
                        "unverified": len(checked), "not_found": 0,
                        "total": len(checked)},
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

    valid_statuses = {VERIFIED, SUPERSEDED, UNVERIFIED, NOT_FOUND}
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
            "as_of": entry.get("as_of", "") or "",
            "correction": entry.get("correction", "") or "",
        })

    summary = {
        "verified": sum(1 for c in checked if c["status"] == VERIFIED),
        "superseded": sum(1 for c in checked if c["status"] == SUPERSEDED),
        "unverified": sum(1 for c in checked if c["status"] == UNVERIFIED),
        "not_found": sum(1 for c in checked if c["status"] == NOT_FOUND),
        "total": len(checked),
    }

    return {
        "checked": True,
        "authorities": checked,
        "summary": summary,
        "verifier_model": verifier_model,
        "note": _summary_note(summary),
    }, usage
