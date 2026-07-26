"""Scoring for panel output against a golden set.

Everything here is a REGRESSION SIGNAL, not a grade. Keyword matching cannot
tell you whether an argument is good — it can tell you whether a prompt change
made the panel stop finding the limitation point it used to find. That is the
question this answers, and it is the question that matters when you are
iterating on prompts.

The grade comes from a partner reading the output. The scorecard asks for it.
"""

import re
from typing import Any, Dict, List, Optional

# Position the chairman effectively adopted, inferred from its own words.
CONTEST_MARKERS = ("contest", "resist", "defend", "challenge", "oppose", "reject the")
CONCEDE_MARKERS = ("concede", "accept the demand", "pay the demand", "settle",
                   "voluntary payment", "avail the amnesty", "discharge the liability")


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())


def _contains_any(haystack: str, needles: List[str]) -> List[str]:
    hay = _normalise(haystack)
    return [n for n in (needles or []) if _normalise(n) and _normalise(n) in hay]


def determination_text(determination: Dict[str, Any]) -> str:
    """Everything the chairman said, flattened for keyword search."""
    parts = [
        determination.get("recommended_position", ""),
        determination.get("lead_argument", ""),
        determination.get("draft_reply", ""),
        determination.get("working_note", ""),
        determination.get("board_summary", ""),
    ]
    for issue in determination.get("issues") or []:
        if isinstance(issue, dict):
            parts.extend([
                issue.get("issue", ""), issue.get("our_position", ""),
                issue.get("authority", ""), issue.get("department_view", ""),
            ])
    for entry in determination.get("panel_disagreements") or []:
        if isinstance(entry, dict):
            parts.extend([entry.get("question", ""), entry.get("resolution", "")])
    parts.extend(str(f) for f in determination.get("risk_flags") or [])
    return "\n".join(str(p) for p in parts)


def counsel_text(analyses: List[Dict[str, Any]], role_key: str = None) -> str:
    """Flatten counsel output, optionally for one counsel only."""
    return "\n".join(
        entry.get("analysis", "")
        for entry in analyses or []
        if role_key is None or entry.get("key") == role_key
    )


def score_citation_integrity(verification: Dict[str, Any]) -> Dict[str, Any]:
    """
    Two failures are never acceptable, and they are equally serious.

    A FABRICATED authority is the obvious one. A SUPERSEDED one is the quiet
    one: it exists, it reads as sound authority, and it will be filed unless
    something catches it. Both fail the matter outright.
    """
    summary = (verification or {}).get("summary") or {}
    total = summary.get("total", 0)
    verified = summary.get("verified", 0)
    not_found = summary.get("not_found", 0)
    superseded = summary.get("superseded", 0)

    authorities = (verification or {}).get("authorities") or []
    fabricated = [a.get("citation") for a in authorities
                  if a.get("status") == "NOT_FOUND"]
    stale = [a.get("citation") for a in authorities
             if a.get("status") == "SUPERSEDED"]

    return {
        "total": total,
        "verified": verified,
        "unverified": summary.get("unverified", 0),
        "superseded": superseded,
        "not_found": not_found,
        "verified_rate": round(verified / total, 3) if total else None,
        "fabricated": fabricated,
        "stale": stale,
        "passed": not_found == 0 and superseded == 0,
    }


def score_issue_coverage(determination: Dict[str, Any],
                         expected_issues: List[str]) -> Dict[str, Any]:
    """Did the panel engage with the issues the notice actually raised?"""
    if not expected_issues:
        return {"expected": 0, "found": 0, "rate": None, "missed": [], "passed": None}

    text = determination_text(determination)
    found = _contains_any(text, expected_issues)
    missed = [i for i in expected_issues if i not in found]

    return {
        "expected": len(expected_issues),
        "found": len(found),
        "rate": round(len(found) / len(expected_issues), 3),
        "missed": missed,
        "passed": len(missed) == 0,
    }


def score_procedural_catch(determination: Dict[str, Any],
                           analyses: List[Dict[str, Any]],
                           expected_points: List[str]) -> Dict[str, Any]:
    """
    Did the panel find the procedural point you found?

    Checked against Procedural Counsel's own analysis as well as the
    determination: a point raised by counsel but dropped by the chairman is a
    different failure from one never raised at all, and worth distinguishing.
    """
    if not expected_points:
        return {"expected": 0, "found": 0, "rate": None, "missed": [],
                "raised_but_dropped": [], "passed": None}

    chairman = determination_text(determination)
    procedural = counsel_text(analyses, "procedural")

    in_chairman = _contains_any(chairman, expected_points)
    in_counsel = _contains_any(procedural, expected_points)

    missed = [p for p in expected_points if p not in in_counsel and p not in in_chairman]
    dropped = [p for p in in_counsel if p not in in_chairman]

    return {
        "expected": len(expected_points),
        "found": len(set(in_chairman) | set(in_counsel)),
        "rate": round(len(set(in_chairman) | set(in_counsel)) / len(expected_points), 3),
        "missed": missed,
        "raised_but_dropped": dropped,
        "passed": len(missed) == 0,
    }


def infer_position(determination: Dict[str, Any]) -> Optional[str]:
    """Infer whether the chairman decided to contest or concede."""
    text = _normalise(
        f"{determination.get('recommended_position', '')} "
        f"{determination.get('lead_argument', '')}"
    )
    if not text.strip():
        return None
    contest = sum(text.count(m) for m in CONTEST_MARKERS)
    concede = sum(text.count(m) for m in CONCEDE_MARKERS)
    if contest == concede:
        return "mixed"
    return "contest" if contest > concede else "concede"


def score_position(determination: Dict[str, Any],
                   expected: Dict[str, Any]) -> Dict[str, Any]:
    """Did the chairman land where your firm actually landed?"""
    expected_position = expected.get("position_taken")
    keywords = expected.get("position_keywords") or []
    forbidden = expected.get("must_not_say") or []

    inferred = infer_position(determination)
    text = determination_text(determination)
    matched = _contains_any(text, keywords)
    violations = _contains_any(text, forbidden)

    agrees = None
    if expected_position and inferred:
        agrees = inferred == expected_position or inferred == "mixed"

    return {
        "expected_position": expected_position,
        "inferred_position": inferred,
        "agrees": agrees,
        "keywords_expected": len(keywords),
        "keywords_matched": len(matched),
        "keyword_rate": round(len(matched) / len(keywords), 3) if keywords else None,
        "violations": violations,
        "passed": (agrees is not False) and not violations,
    }


def score_determination_integrity(determination: Dict[str, Any]) -> Dict[str, Any]:
    """Did the chairman return usable structured output at all?"""
    degraded = bool(determination.get("_degraded"))
    required = ("recommended_position", "draft_reply", "issues", "working_note")
    present = [f for f in required if determination.get(f)]

    return {
        "degraded": degraded,
        "fields_present": len(present),
        "fields_required": len(required),
        "missing": [f for f in required if f not in present],
        "confidence": determination.get("confidence"),
        "passed": not degraded and len(present) == len(required),
    }


def score_matter(golden: Dict[str, Any], result: Dict[str, Any],
                 metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Score one matter end to end."""
    determination = result.get("determination") or {}
    verification = result.get("verification") or {}
    analyses = result.get("analyses") or []
    expected = golden.get("expected") or {}

    scores = {
        "citations": score_citation_integrity(verification),
        "issues": score_issue_coverage(determination, expected.get("issues_expected")),
        "procedural": score_procedural_catch(
            determination, analyses, expected.get("procedural_points")
        ),
        "position": score_position(determination, expected),
        "integrity": score_determination_integrity(determination),
    }

    # A matter passes only if nothing that CAN fail did.
    checks = [s.get("passed") for s in scores.values()]
    passed = all(c is not False for c in checks)

    return {
        "id": golden.get("id"),
        "description": golden.get("description", ""),
        "passed": passed,
        "scores": scores,
        "counsel_count": len(analyses),
        "cross_exam_count": len(result.get("cross_exams") or []),
        "usage": metadata.get("usage") or {},
        "tier": metadata.get("tier"),
        "failures": metadata.get("failures") or {},
    }


def aggregate(matter_scores: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Roll individual matters up into the numbers you track over time."""
    if not matter_scores:
        return {}

    def rate(extract):
        values = [extract(m) for m in matter_scores]
        values = [v for v in values if v is not None]
        return round(sum(values) / len(values), 3) if values else None

    total_cost = sum((m.get("usage") or {}).get("total_cost", 0) or 0
                     for m in matter_scores)
    fabricated = [
        (m["id"], c)
        for m in matter_scores
        for c in m["scores"]["citations"]["fabricated"]
    ]
    stale = [
        (m["id"], c)
        for m in matter_scores
        for c in m["scores"]["citations"].get("stale", [])
    ]

    return {
        "matters": len(matter_scores),
        "passed": sum(1 for m in matter_scores if m["passed"]),
        "pass_rate": round(
            sum(1 for m in matter_scores if m["passed"]) / len(matter_scores), 3
        ),
        "citation_verified_rate": rate(lambda m: m["scores"]["citations"]["verified_rate"]),
        "fabricated_citations": fabricated,
        "superseded_citations": stale,
        "issue_coverage": rate(lambda m: m["scores"]["issues"]["rate"]),
        "procedural_catch": rate(lambda m: m["scores"]["procedural"]["rate"]),
        "position_agreement": rate(
            lambda m: 1.0 if m["scores"]["position"]["agrees"] else
            (0.0 if m["scores"]["position"]["agrees"] is False else None)
        ),
        "determination_integrity": rate(
            lambda m: 1.0 if m["scores"]["integrity"]["passed"] else 0.0
        ),
        "total_cost": round(total_cost, 4),
        "cost_per_matter": round(total_cost / len(matter_scores), 4),
    }
