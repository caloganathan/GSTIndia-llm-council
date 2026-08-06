"""Run cost in rupees — estimated before, actual after.

WHY THIS EXISTS
---------------
Every model call already reports its dollar cost and the totals are already
aggregated and persisted. What was missing is the only form of the number a
partner can act on. A firm prices an engagement in rupees, recovers it in
rupees, and decides whether a second opinion is worth running by comparing it
to what the limb is worth in rupees. "$0.87" is a number nobody in the office
converts, so nobody forms an intuition about cost, so cost stops being managed.

HOW THE ESTIMATE IS PRODUCED, AND WHY NOT FROM A PRICE TABLE
------------------------------------------------------------
The obvious implementation is per-model token pricing multiplied by expected
tokens. It was rejected for the reason written into `config.py` about the free
tier: **anything keyed to a model ID goes stale silently.** Prices change,
models are replaced, and a hardcoded table would quietly produce confident
wrong figures long after anyone remembered it existed — the exact failure this
codebase has already been through once.

So the estimate comes from the firm's own completed matters. Cost scales with
the number of limbs that convene counsel, so past runs are normalised to a
per-convened-limb figure and the median of those is applied to the matter
about to be run. The median rather than the mean: one matter with a runaway
annexure should not move the estimate for everything after it.

With no history there is nothing to learn from, so a stated default range is
used and labelled as such. The range is deliberately wide, and it is better to
say "roughly Rs. 30 to Rs. 120, we have not run one of these yet" than to
publish a precise figure derived from nothing.
"""

import os
from typing import Any, Dict, Iterable, List, Optional

from . import config

# The conversion rate. A stated constant, not a live feed: a currency API is a
# network dependency, a failure mode and a privacy question, in exchange for
# precision this number does not need. Set it once a quarter.
USD_INR = float(os.getenv("USD_INR_RATE", "88.0"))

# Fallback per-convened-limb cost in USD, used only until the firm has run
# enough matters to know its own. Derived from observed runs: a convened limb
# is four counsel openings, a cross-examination round and a share of the
# chairman and verifier.
DEFAULT_COST_PER_LIMB = {
    "draft": 0.02,
    "pro": 0.18,
}

# Fixed cost of a run regardless of limb count: grounding briefing, chairman
# assembly, citation verification. These do not scale with the number of limbs.
DEFAULT_FIXED_COST = {
    "draft": 0.01,
    "pro": 0.12,
}

# How wide the estimate is quoted. Model output length varies with the notice,
# and a single figure implies a precision that does not exist.
ESTIMATE_SPREAD = 0.45

# Below this many completed matters on a tier, the firm's own history is not
# yet a better guide than the stated default.
MIN_HISTORY = 3


def to_inr(usd: Optional[float]) -> Optional[float]:
    if usd is None:
        return None
    return round(float(usd) * USD_INR, 2)


def format_inr(amount: Optional[float], paise: bool = True) -> str:
    """
    Indian digit grouping: 12,34,567.89, not 1,234,567.89.

    A figure grouped in thousands reads as a foreign number to the person
    checking it, and this application prints money for Indian tax practice.
    """
    if amount is None:
        return "—"
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return "—"

    negative = value < 0
    value = abs(value)
    whole = int(value)
    fraction = value - whole

    digits = str(whole)
    if len(digits) > 3:
        last3, rest = digits[-3:], digits[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        grouped = ",".join(groups + [last3])
    else:
        grouped = digits

    text = f"Rs. {grouped}"
    if paise:
        text += f".{int(round(fraction * 100)):02d}"
    return f"-{text}" if negative else text


def observed_rates(matters: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    What runs have actually cost this firm, per tier, per convened limb.

    Only completed matters with both a cost and a limb count contribute. A
    matter that failed halfway carries a real cost but not a representative
    one, and would drag every future estimate down.
    """
    by_tier: Dict[str, List[float]] = {}

    for matter in matters or []:
        if matter.get("status") != "complete":
            continue
        usage = matter.get("usage") or {}
        cost = usage.get("total_cost")
        if not cost or cost <= 0:
            continue
        limbs = matter.get("panel_defect_count") or matter.get("defect_count")
        if not limbs or limbs <= 0:
            continue
        # Resolve through the one alias table config keeps — matters created
        # under the retired free tier were run on the draft models, and any
        # future alias must land here without a second hardcoded map.
        tier = config.get_tier(matter.get("tier") or "pro")["key"]
        by_tier.setdefault(tier, []).append(float(cost) / float(limbs))

    result = {}
    for tier, rates in by_tier.items():
        rates.sort()
        middle = len(rates) // 2
        median = (rates[middle] if len(rates) % 2
                  else (rates[middle - 1] + rates[middle]) / 2)
        result[tier] = {"per_limb": median, "samples": len(rates)}
    return result


def estimate_run(defect_count: int, panel_count: int, tier: str,
                 history: Iterable[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    What this run will cost, before it is run.

    `panel_count` is the number of limbs that will actually convene counsel —
    triage means most limbs do not, and estimating on the total would overstate
    a typical eight-limb notice by a factor of four.
    """
    tier = config.get_tier(tier or "pro")["key"]
    rates = observed_rates(history or [])
    tier_history = rates.get(tier) or {}

    if tier_history.get("samples", 0) >= MIN_HISTORY:
        per_limb = tier_history["per_limb"]
        fixed = 0.0          # already inside the observed per-limb figure
        basis = (f"your firm's last {tier_history['samples']} completed "
                 f"{tier} runs")
        learned = True
    else:
        per_limb = DEFAULT_COST_PER_LIMB.get(tier, DEFAULT_COST_PER_LIMB["pro"])
        fixed = DEFAULT_FIXED_COST.get(tier, DEFAULT_FIXED_COST["pro"])
        basis = ("typical observed runs — this firm has not yet completed "
                 f"enough {tier} matters to estimate from its own history")
        learned = False

    central = fixed + per_limb * max(panel_count, 0)
    low = central * (1 - ESTIMATE_SPREAD)
    high = central * (1 + ESTIMATE_SPREAD)

    return {
        "tier": tier,
        "defect_count": defect_count,
        "panel_count": panel_count,
        "usd": {"low": round(low, 4), "high": round(high, 4),
                "central": round(central, 4)},
        "inr": {"low": to_inr(low), "high": to_inr(high),
                "central": to_inr(central)},
        "label": f"{format_inr(to_inr(low), paise=False)} to "
                 f"{format_inr(to_inr(high), paise=False)}",
        "basis": basis,
        "learned_from_history": learned,
        "rate_used": USD_INR,
    }


def describe_usage(usage: Dict[str, Any]) -> Dict[str, Any]:
    """Actual spend on a completed run, in both currencies."""
    usage = usage or {}
    cost = usage.get("total_cost")
    return {
        "usd": round(float(cost), 4) if cost else None,
        "inr": to_inr(cost),
        "label": format_inr(to_inr(cost)) if cost else "—",
        "tokens": usage.get("total_tokens"),
        "rate_used": USD_INR,
    }
