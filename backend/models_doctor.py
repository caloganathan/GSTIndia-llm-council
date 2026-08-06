"""Check every configured model ID against OpenRouter's live catalogue.

WHY THIS EXISTS
---------------
Model IDs on OpenRouter churn, and this codebase has already been through the
failure once: the retired free tier's IDs went stale and the tier failed
SILENTLY in production — including notice reading, because
`intake.extract_fields_assisted` borrows the tier's grounding model. One root
cause, two symptoms that looked unrelated.

Startup validation reports stale IDs, but it only says WHICH are wrong. It
does not say what to put in their place, and it cannot be run before a deploy.
This can:

    python -m backend.cli check-models
    python -m backend.cli check-models --suggest

It talks to `https://openrouter.ai/api/v1/models`, which is public and needs no
key. Run it wherever that host is reachable — a laptop, or the Render service's
Shell tab against the live configuration.

WHAT IT KNOWS THAT A NAKED ID LIST DOES NOT
-------------------------------------------
The slots are not interchangeable:

  * the VERIFIER and GROUNDING slots issue a web search, so the model must be
    able to carry OpenRouter's web plugin;
  * the CHAIRMAN slot writes the longest single output in the product (a
    determination carrying a draft reply, an authorities table and a working
    note) against a 16,000-token ceiling, so a small context window there
    silently truncates the one output that matters most;
  * the DRAFT tier exists to be cheap, so a suggestion that is not materially
    cheaper than the Pro tier defeats the point of having two tiers.

So a slot is reported as WRONG SHAPE even when the ID exists, and suggestions
are filtered per slot rather than offered as one undifferentiated list.
"""

import json
import os
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from . import config

CATALOGUE_URL = "https://openrouter.ai/api/v1/models"

# The chairman's ceiling is 16k output; anything whose total context cannot
# comfortably hold the prompt AND that output will truncate the determination.
MIN_CONTEXT_CHAIRMAN = 60_000
MIN_CONTEXT_GENERAL = 30_000

# Web slots need MORE context, not a different capability.
#
# OpenRouter's web plugin runs the search itself and injects the results into
# the prompt, so it is not a per-model feature and the catalogue does not
# expose one — an earlier draft of this file pretended to check for it and had
# a context-based fallback that made the check always pass, which is worse than
# not checking. What is genuinely required is room for several search results
# ON TOP of a prompt that already carries every authority and its proposition.
MIN_CONTEXT_WEB = 60_000

# A draft-tier seat above this is not a cheap tier. Dollars per million output
# tokens; the draft tier's whole purpose is cents per run.
MAX_DRAFT_OUTPUT_PRICE = 2.00


def _slots() -> List[Dict[str, Any]]:
    """Every configured model slot, with what that slot actually requires."""
    slots: List[Dict[str, Any]] = []

    def add(env: str, value: str, label: str, needs_web=False,
            is_chairman=False, cheap=False):
        slots.append({
            "env": env, "value": value, "label": label,
            "needs_web": needs_web, "is_chairman": is_chairman, "cheap": cheap,
        })

    for role, model in config.PRO_ROLE_MODELS.items():
        add(f"PRO_MODEL_{role.upper()}", model, f"Pro tier — {role}",
            is_chairman=(role == "chairman"))
    for role, model in config.DRAFT_ROLE_MODELS.items():
        add(f"DRAFT_MODEL_{role.upper()}", model, f"Draft tier — {role}",
            is_chairman=(role == "chairman"), cheap=True)

    add("VERIFIER_MODEL", config.VERIFIER_MODEL,
        "Citation verification (Pro)", needs_web=True)
    add("DRAFT_VERIFIER_MODEL", config.DRAFT_VERIFIER_MODEL,
        "Citation verification (Draft)", needs_web=True, cheap=True)
    add("GROUNDING_MODEL", config.GROUNDING_MODEL,
        "Current-law briefing + notice reading (Pro)", needs_web=True)
    add("DRAFT_GROUNDING_MODEL", config.DRAFT_GROUNDING_MODEL,
        "Current-law briefing + notice reading (Draft)",
        needs_web=True, cheap=True)

    add("TITLE_MODEL", config.TITLE_MODEL, "Conversation titles")
    if config.ENABLE_GENERAL_COUNCIL:
        for index, model in enumerate(config.COUNCIL_MODELS, start=1):
            add("COUNCIL_MODELS", model, f"General Council seat {index}")
        add("CHAIRMAN_MODEL", config.CHAIRMAN_MODEL,
            "General Council chairman", is_chairman=True)

    return slots


def fetch_catalogue(url: str = CATALOGUE_URL,
                    timeout: float = 20.0) -> Tuple[Optional[Dict[str, Any]], str]:
    """Return ({id: record}, "") or (None, reason)."""
    try:
        request = urllib.request.Request(
            url, headers={"Accept": "application/json",
                          "User-Agent": "compliance-panel-model-doctor"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except Exception as problem:  # noqa: BLE001 - any failure is the same answer
        return None, str(problem)

    catalogue = {}
    for entry in payload.get("data", []):
        if entry.get("id"):
            catalogue[entry["id"]] = entry
    if not catalogue:
        return None, "the catalogue came back empty"
    return catalogue, ""


def _price(record: Dict[str, Any], key: str) -> Optional[float]:
    try:
        return float(record.get("pricing", {}).get(key))
    except (TypeError, ValueError):
        return None


def _output_price_per_million(record: Dict[str, Any]) -> Optional[float]:
    price = _price(record, "completion")
    return None if price is None else price * 1_000_000


def _context_floor(slot: Dict[str, Any]) -> Tuple[int, str]:
    """The context this slot needs, and why."""
    if slot["is_chairman"]:
        return (MIN_CONTEXT_CHAIRMAN,
                "the chairman writes the longest output in the product, "
                "against a 16,000-token ceiling")
    if slot["needs_web"]:
        return (MIN_CONTEXT_WEB,
                "this slot issues a web search and the plugin injects the "
                "results into the prompt, on top of every authority it already "
                "carries")
    return MIN_CONTEXT_GENERAL, "a counsel prompt carries the notice limb by limb"


def _fits_slot(slot: Dict[str, Any], record: Dict[str, Any]) -> List[str]:
    """Reasons this model is wrong for this slot. Empty means it fits."""
    problems = []
    context = record.get("context_length") or 0
    floor, because = _context_floor(slot)
    if context and context < floor:
        problems.append(
            f"context {context:,} is below the {floor:,} this slot needs — "
            f"{because}")
    if slot["cheap"]:
        price = _output_price_per_million(record)
        if price is not None and price > MAX_DRAFT_OUTPUT_PRICE:
            problems.append(
                f"${price:.2f}/M output tokens is not a cheap-tier price "
                f"(over ${MAX_DRAFT_OUTPUT_PRICE:.2f})")
    return problems


def suggest(slot: Dict[str, Any], catalogue: Dict[str, Any],
            limit: int = 3) -> List[Tuple[str, Optional[float]]]:
    """
    Candidates for a slot, preferring the same vendor as the stale ID.

    Same vendor first because a firm that chose Anthropic for the assessee seat
    and Google for grounding chose deliberately, and a doctor that reshuffles
    the panel while fixing a typo is not fixing a typo.
    """
    vendor = slot["value"].split("/")[0] if "/" in slot["value"] else ""
    scored = []
    for model_id, record in catalogue.items():
        if _fits_slot(slot, record):
            continue
        price = _output_price_per_million(record)
        if price is None or price <= 0:
            continue          # free endpoints churn; that lesson is already learnt
        scored.append((model_id, record, price))

    def sort_key(item):
        model_id, record, price = item
        same_vendor = 0 if model_id.startswith(f"{vendor}/") else 1
        # Cheap slots want the cheapest that fits; quality slots want the most
        # capable, for which context is the only proxy the catalogue offers.
        rank = price if slot["cheap"] else -(record.get("context_length") or 0)
        return (same_vendor, rank)

    scored.sort(key=sort_key)
    return [(model_id, price) for model_id, _, price in scored[:limit]]


def diagnose(catalogue: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every slot, with its verdict."""
    results = []
    for slot in _slots():
        record = catalogue.get(slot["value"])
        if record is None:
            verdict, problems = "MISSING", ["not in the catalogue at all"]
        else:
            problems = _fits_slot(slot, record)
            verdict = "WRONG SHAPE" if problems else "OK"
        results.append({**slot, "verdict": verdict, "problems": problems,
                        "record": record})
    return results


def report(show_suggestions: bool = False,
           url: str = CATALOGUE_URL) -> int:
    """Print the diagnosis. Returns a process exit code."""
    catalogue, failure = fetch_catalogue(url)
    if catalogue is None:
        print(f"Could not reach the OpenRouter catalogue: {failure}\n")
        print("This check needs outbound access to openrouter.ai. Run it from a")
        print("machine or shell that has it — a laptop, or the Render service's")
        print("Shell tab, which also picks up the live configuration.")
        return 2

    print(f"Checked {len(catalogue):,} models in the OpenRouter catalogue.\n")
    results = diagnose(catalogue)
    broken = [r for r in results if r["verdict"] != "OK"]

    width = max(len(r["env"]) for r in results)
    for result in results:
        mark = {"OK": "ok  ", "MISSING": "GONE", "WRONG SHAPE": "WARN"}[result["verdict"]]
        print(f"[{mark}] {result['env']:<{width}}  {result['value']}")
        print(f"        {result['label']}")
        for problem in result["problems"]:
            print(f"        -> {problem}")
        if result["verdict"] == "OK":
            price = _output_price_per_million(result["record"])
            context = result["record"].get("context_length") or 0
            detail = f"context {context:,}"
            if price is not None:
                detail += f", ${price:.2f}/M output"
            print(f"        {detail}")
        print()

    if not broken:
        print("Every configured model ID resolves and suits its slot.")
        return 0

    print(f"{len(broken)} of {len(results)} slots need attention.\n")

    if not show_suggestions:
        print("Re-run with --suggest for candidate replacements per slot.")
        return 1

    print("=" * 70)
    print("SUGGESTED REPLACEMENTS — read these before pasting them")
    print("=" * 70)
    print("Chosen from the live catalogue, preferring the same vendor as the")
    print("stale ID so the panel's composition is not reshuffled while a typo")
    print("is fixed. Cheap slots are ranked by price, quality slots by context.")
    print("A suggestion is a candidate, not a decision: the roster is a")
    print("professional judgement about which model argues which side.\n")

    env_lines = []
    for result in broken:
        print(f"{result['env']}  ({result['label']})")
        print(f"  currently: {result['value']}  [{result['verdict']}]")
        candidates = suggest(result, catalogue)
        if not candidates:
            print("  no candidate in the catalogue fits this slot's "
                  "requirements — choose by hand.\n")
            continue
        for model_id, price in candidates:
            print(f"    {model_id}"
                  + (f"   (${price:.2f}/M output)" if price else ""))
        if result["env"] != "COUNCIL_MODELS":
            env_lines.append(f"{result['env']}={candidates[0][0]}")
        print()

    if env_lines:
        print("=" * 70)
        print("Paste-ready, using the FIRST candidate for each slot.")
        print("Set these as environment variables — no code change needed,")
        print("and no redeploy beyond the restart that picks them up.")
        print("=" * 70)
        for line in env_lines:
            print(line)
        print()
        print("Then restart the service and confirm with:")
        print("  curl -s https://<your-host>/api/health | "
              "python -m json.tool | grep -A5 model_validation")

    return 1
