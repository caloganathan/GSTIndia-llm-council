"""Run the panel over a golden set and produce a scorecard.

    uv run python -m evals.run                 # whole golden set, Pro tier
    uv run python -m evals.run --only gst-001  # one matter
    uv run python -m evals.run --tier free     # cheap iteration
    uv run python -m evals.run --dry-run       # validate the set, no model calls
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from backend.panel import run_panel_stream

from .scoring import aggregate, score_matter

ROOT = Path(__file__).resolve().parent
GOLDEN_DIR = ROOT / "golden"
RESULTS_DIR = ROOT / "results"


def load_golden(only: str = None) -> List[Dict[str, Any]]:
    if not GOLDEN_DIR.is_dir():
        return []
    matters = []
    for path in sorted(GOLDEN_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            print(f"  ! {path.name}: invalid JSON — {e}")
            continue
        if not data.get("id"):
            data["id"] = path.stem
        if not data.get("intake"):
            print(f"  ! {path.name}: no 'intake' block, skipping")
            continue
        if only and data["id"] != only:
            continue
        matters.append(data)
    return matters


async def run_one(golden: Dict[str, Any], tier: str) -> Dict[str, Any]:
    """Run the panel over one golden matter."""
    result: Dict[str, Any] = {}
    metadata: Dict[str, Any] = {}
    error = None

    async for event in run_panel_stream(golden["intake"], domain="gst", tier_name=tier):
        if event["type"] == "summary":
            result = event["data"]
            metadata = event["metadata"]
        elif event["type"] == "error":
            error = event["message"]

    if error and not result:
        return {"id": golden["id"], "error": error, "passed": False,
                "scores": {}, "usage": {}}

    scored = score_matter(golden, result, metadata)
    scored["_result"] = result
    return scored


def pct(value) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"


def write_scorecard(path: Path, summary: Dict[str, Any],
                    scores: List[Dict[str, Any]], tier: str):
    lines = [
        "# Panel scorecard",
        "",
        f"Run: {datetime.now(timezone.utc).strftime('%d %B %Y, %H:%M UTC')}  ",
        f"Tier: **{tier}**  ",
        f"Matters: **{summary.get('matters', 0)}**",
        "",
        "## Summary",
        "",
        "| Metric | Result | Target |",
        "|---|---|---|",
        f"| Matters passed | {summary.get('passed', 0)} / {summary.get('matters', 0)}"
        f" ({pct(summary.get('pass_rate'))}) | — |",
        f"| Citation integrity | {pct(summary.get('citation_verified_rate'))} verified | "
        "no fabrications |",
        f"| Issue coverage | {pct(summary.get('issue_coverage'))} | ≥ 90% |",
        f"| Procedural catch | {pct(summary.get('procedural_catch'))} | ≥ 80% |",
        f"| Position agreement | {pct(summary.get('position_agreement'))} | ≥ 70% |",
        f"| Determination integrity | {pct(summary.get('determination_integrity'))} | 100% |",
        f"| Cost per matter | ${summary.get('cost_per_matter', 0):.4f} | your call |",
        "",
    ]

    stale = summary.get("superseded_citations") or []
    if stale:
        lines += [
            "> ## \u26a0 SUPERSEDED AUTHORITIES",
            ">",
            "> These exist but are no longer good law. They read as sound",
            "> authority and will be filed unless caught here.",
            ">",
        ]
        lines += [f"> - `{mid}` \u2014 {citation}" for mid, citation in stale]
        lines.append("")

    fabricated = summary.get("fabricated_citations") or []
    if fabricated:
        lines += [
            "> ## ⚠ FABRICATED CITATIONS",
            ">",
            "> These authorities could not be located. Treat as fabricated until",
            "> proven otherwise — this is the failure that ends the product's",
            "> credibility if it reaches a client.",
            ">",
        ]
        lines += [f"> - `{mid}` — {citation}" for mid, citation in fabricated]
        lines.append("")

    lines += ["## Matters", ""]

    for entry in scores:
        if entry.get("error"):
            lines += [f"### {entry['id']} — RUN FAILED", "",
                      f"```\n{entry['error']}\n```", ""]
            continue

        s = entry["scores"]
        status = "PASS" if entry["passed"] else "FAIL"
        lines += [
            f"### {entry['id']} — {status}",
            "",
            f"{entry.get('description', '')}",
            "",
            f"- **Citations**: {s['citations']['verified']} verified, "
            f"{s['citations'].get('superseded', 0)} superseded, "
            f"{s['citations']['unverified']} unverified, "
            f"{s['citations']['not_found']} not found",
            f"- **Issues**: {s['issues']['found']}/{s['issues']['expected']} covered"
            + (f" — missed: {', '.join(s['issues']['missed'])}"
               if s['issues']['missed'] else ""),
            f"- **Procedural**: {s['procedural']['found']}/{s['procedural']['expected']} found"
            + (f" — missed: {', '.join(s['procedural']['missed'])}"
               if s['procedural']['missed'] else ""),
        ]
        if s["procedural"].get("raised_but_dropped"):
            lines.append(
                f"  - ⚠ raised by counsel but dropped by the chairman: "
                f"{', '.join(s['procedural']['raised_but_dropped'])}"
            )
        lines += [
            f"- **Position**: expected `{s['position']['expected_position']}`, "
            f"inferred `{s['position']['inferred_position']}`",
            f"- **Confidence**: {s['integrity']['confidence']}",
            f"- **Cost**: ${(entry.get('usage') or {}).get('total_cost', 0):.4f}",
        ]
        if s["position"].get("violations"):
            lines.append(
                f"- ⚠ **Said something it must not**: {', '.join(s['position']['violations'])}"
            )
        lines.append("")

    lines += [
        "---",
        "",
        "## Partner grading",
        "",
        "The metrics above are a regression signal. They cannot tell you whether",
        "the argument is any good. Score each matter yourself — this is the part",
        "that decides whether the product is real.",
        "",
        "| Matter | Would you sign it? | Found anything you missed? | Said anything wrong? | Minutes to a filable draft |",
        "|---|---|---|---|---|",
    ]
    for entry in scores:
        lines.append(f"| {entry['id']} | | | | |")

    lines += [
        "",
        "**Would you sign it**: yes / with minor edits / no. This is the only",
        "metric that ultimately matters. Seven of ten at 'yes' or 'minor edits'",
        "is the bar for inviting an outside firm.",
        "",
    ]

    path.write_text("\n".join(lines))


async def main():
    parser = argparse.ArgumentParser(description="Score the panel against a golden set")
    parser.add_argument("--tier", default="pro", choices=["free", "pro"])
    parser.add_argument("--only", help="Run a single matter by id")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate the golden set without calling any model")
    args = parser.parse_args()

    matters = load_golden(args.only)
    if not matters:
        print(f"No golden matters found in {GOLDEN_DIR}")
        print("Create one JSON file per matter — see evals/README.md for the shape.")
        return 1

    print(f"Loaded {len(matters)} golden matter(s) from {GOLDEN_DIR}")

    if args.dry_run:
        for matter in matters:
            expected = matter.get("expected") or {}
            print(f"  ✓ {matter['id']}: "
                  f"{len(expected.get('issues_expected') or [])} issues, "
                  f"{len(expected.get('procedural_points') or [])} procedural points, "
                  f"position={expected.get('position_taken', 'unset')}")
        print("\nGolden set is valid. Drop --dry-run to run the panel.")
        return 0

    print(f"Running the panel on the {args.tier} tier. "
          "This makes real model calls and costs money.\n")

    scores = []
    for i, matter in enumerate(matters, start=1):
        print(f"[{i}/{len(matters)}] {matter['id']}… ", end="", flush=True)
        try:
            scored = await run_one(matter, args.tier)
        except Exception as e:
            print(f"ERROR: {e}")
            scores.append({"id": matter["id"], "error": str(e), "passed": False,
                           "scores": {}, "usage": {}})
            continue
        if scored.get("error"):
            print(f"FAILED: {scored['error']}")
        else:
            print("PASS" if scored["passed"] else "FAIL")
        scores.append(scored)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = RESULTS_DIR / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    for entry in scores:
        result = entry.pop("_result", None)
        if result is not None:
            (out_dir / f"{entry['id']}.json").write_text(json.dumps(result, indent=2))

    scorable = [s for s in scores if not s.get("error")]
    summary = aggregate(scorable)

    (out_dir / "results.json").write_text(
        json.dumps({"tier": args.tier, "summary": summary, "matters": scores}, indent=2)
    )
    write_scorecard(out_dir / "scorecard.md", summary, scores, args.tier)

    print(f"\n{'=' * 62}")
    print(f"  Passed:              {summary.get('passed', 0)}/{summary.get('matters', 0)}")
    print(f"  Citation integrity:  {pct(summary.get('citation_verified_rate'))} verified")
    print(f"  Issue coverage:      {pct(summary.get('issue_coverage'))}")
    print(f"  Procedural catch:    {pct(summary.get('procedural_catch'))}")
    print(f"  Cost per matter:     ${summary.get('cost_per_matter', 0):.4f}")
    if summary.get("fabricated_citations"):
        print(f"\n  ⚠ {len(summary['fabricated_citations'])} FABRICATED CITATION(S) "
              "— see the scorecard")
    print(f"{'=' * 62}")
    print(f"\nScorecard: {out_dir / 'scorecard.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
