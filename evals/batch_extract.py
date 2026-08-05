"""Run every notice in a folder through extraction, and report what happened.

    uv run python -m evals.batch_extract ~/notices
    uv run python -m evals.batch_extract ~/notices --out ~/testing/round1

WHY THIS IS THE FIRST THING TO RUN, BEFORE ANY PAID TESTING
-----------------------------------------------------------
Extraction costs nothing. There are no model calls in this path — segmentation,
figure reading and field extraction are regex and arithmetic in Python — so a
firm can put its entire notice archive through this for zero rupees.

It is also where the failures are most expensive and least visible. A limb that
does not segment is never answered, and an unanswered limb is confirmed
unopposed. A figure misread off an annexure becomes a figure quoted back to the
officer. Neither announces itself: the panel will argue confidently about
whatever it was given, and the output will read perfectly well.

So the order that gets the most information per rupee is: run the whole archive
through extraction first, fix what this surfaces, and only then spend money on
panel runs.

WHAT THIS CAN AND CANNOT TELL YOU
---------------------------------
It cannot tell you whether an extraction is CORRECT. There is no ground truth
for a notice nobody has keyed in. What it can do is:

  - report what was read, in a form that can be checked against the notice in
    seconds rather than minutes;
  - flag every case where the product itself is unsure — a limb whose amount
    could not be read, a field that came from OCR, a notice that segmented to
    nothing;
  - carry out the one check that needs no ground truth at all — whether the
    limbs sum to the total the notice prints for itself.

That last one is the sharpest signal here, and it is free. A notice whose limbs
do not reconcile to its own printed total has a real extraction defect, and you
know that without having read the notice.

The review sheet it writes is where a human supplies the ground truth. Fill it
in as you check, and it becomes the record of how the extraction layer actually
performed on real work — which is the number that decides whether this is ready.
"""

import argparse
import asyncio
import csv
import sys
from pathlib import Path
from typing import Any, Dict, List

from backend import defects as defects_module
from backend import intake, notice_tables, ocr
from backend.domains import get_pack

SUPPORTED = (".pdf", ".docx", ".txt")

# Fields a reply is rejected on its face for getting wrong, or that drive the
# jurisdiction weighting and the deadline. Anything missing here is a blank the
# reviewer has to fill before the panel is worth running.
KEY_FIELDS = ("client_name", "gstin", "notice_type", "state", "tax_period",
              "due_date", "notice_date", "section_invoked")


def find_notices(root: Path) -> List[Path]:
    if root.is_file():
        return [root]
    return sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED
    )


# What the department calls its own demand total. The row carrying one of
# these labels is the only row that is a notice-level total; every other row
# that passes the checksum is a working row.
DEMAND_TOTAL_LABELS = (
    "total tax due", "total tax payable", "total tax liability",
    "net tax payable", "total amount payable", "total demand",
)


def _is_demand_total(label: str) -> bool:
    """
    Whether a row's label names it as the demand total, rather than merely
    following one.

    A row label is the 160 characters printed before its figures, so the rows
    BENEATH the demand total inherit its wording: on a real summary table the
    interest row, the penalty row and the tax-plus-interest-plus-penalty grand
    total all carry "Total tax due" somewhere in their lookback. Taking the
    last of those compared tax-only limbs against a grand total that includes
    interest and penalty, which is a mismatch by construction.

    So the phrase has to be the last thing said before the figures. Anything
    between the phrase and the numbers is allowed to be words — departments
    write "Total tax due in (Excess claim of ITC) above" — but not digits,
    because digits mean another row's figures have intervened.
    """
    text = (label or "").lower()
    for phrase in DEMAND_TOTAL_LABELS:
        position = text.rfind(phrase)
        if position != -1 and not any(
            character.isdigit() for character in text[position + len(phrase):]
        ):
            return True
    return False


def notice_printed_total(text: str, limb_totals: List[float]) -> float:
    """
    The total the notice prints for itself — 0.0 where it prints none.

    Taken from the row the department LABELS as its demand total, and from
    nowhere else.

    This used to be the largest head-wise row in the document that passed its
    own checksum. On synthetic notices, where the only tables are the limb
    annexures, that is the same thing. On real ones it is not: a scrutiny
    notice carries an ITC reconciliation whose working rows dwarf the demand,
    and the largest row in the document is "ITC on inward supplies as per
    GSTR-3B" — the whole year's credit. Reading that as the notice total
    reported Rs. 17.53 crore against limbs of Rs. 20.8 lakh, and did it on
    twelve notices out of twelve.

    That is worse than useless. The reconciliation flag is the one check in
    this harness that needs no ground truth, so it is the one a reviewer will
    trust; firing it on every notice teaches them to ignore it, and it is then
    not there on the notice where a limb really has absorbed its neighbour's
    figure.

    Where no labelled demand total is printed the answer is 0.0 and the report
    says so, which is a true statement about the notice rather than a false
    one about the extraction.
    """
    labelled = [row for row in notice_tables.find_head_rows(text)
                if _is_demand_total(row["label"])]
    if not labelled:
        return 0.0

    # Departmental summaries build to their conclusion, so the last such row
    # is the operative one.
    total = labelled[-1]["total"]

    # A form that prints only its limb rows and calls one of them a total is
    # not stating a notice-level figure. An RFD-08 objecting to a refund on
    # two grounds prints the two grounds and nothing else, and reading its
    # larger ground as the notice total reports a discrepancy against a figure
    # the notice never claimed.
    if any(abs(total - limb) <= 2.0 for limb in limb_totals):
        return 0.0
    return total


async def extract_one(path: Path, pack) -> Dict[str, Any]:
    content = path.read_bytes()
    try:
        result = await intake.read_notice_set(
            [(path.name, content)], pack, {"anonymise": False}, use_model=False,
        )
    except Exception as e:
        return {"file": path.name, "error": str(e)}

    fields = result.get("fields") or {}
    limbs = fields.get("defects") or []
    sources = result.get("sources") or {}

    limb_totals = [sum((limb.get("amount_by_head") or {}).values())
                   for limb in limbs]
    limb_total = sum(limb_totals)
    printed = notice_printed_total(result.get("text") or "", limb_totals)
    reconciles = bool(printed) and abs(limb_total - printed) <= 2.0

    triaged = defects_module.triage(limbs) if limbs else {}

    return {
        "file": path.name,
        "error": None,
        "source": "OCR" if result.get("scanned") else "text",
        "text_length": result.get("text_length", 0),
        "fields": fields,
        # A notice that gives a period running from service prints no calendar
        # date, and reporting due_date as "not found" invites someone to go
        # looking for one. The period is what there is to know.
        "reply_window_days": fields.get("reply_window_days"),
        "missing_fields": [
            f for f in KEY_FIELDS
            if not fields.get(f)
            and not (f == "due_date" and fields.get("reply_window_days"))
        ],
        "ocr_fields": [k for k, v in sources.items() if str(v).endswith("-ocr")],
        "limbs": limbs,
        "limb_count": len(limbs),
        "argued_count": triaged.get("argue_count", 0),
        "unread_amounts": [l.get("heading") for l in limbs
                           if l.get("amount_unread")],
        "limb_total": limb_total,
        "printed_total": printed,
        "reconciles": reconciles,
        "warnings": result.get("warnings") or [],
    }


def flags_for(entry: Dict[str, Any]) -> List[str]:
    """
    Everything about this notice that needs a human before the panel runs.

    Ordered worst first. A notice that segmented to nothing is the most serious
    outcome this tool can report: it means the reply would answer a multi-limb
    notice as a single undifferentiated issue.
    """
    flags = []
    if entry.get("error"):
        return [f"FAILED TO READ: {entry['error']}"]
    if entry["limb_count"] == 0:
        flags.append("NO LIMBS SEGMENTED — the notice would be answered as one issue")
    if entry["printed_total"] and not entry["reconciles"]:
        flags.append(
            f"LIMBS DO NOT RECONCILE — limbs total {entry['limb_total']:,.2f} "
            f"against a printed total of {entry['printed_total']:,.2f}"
        )
    if entry["unread_amounts"]:
        flags.append(
            f"{len(entry['unread_amounts'])} limb(s) with no figure read — "
            "enter from the annexure"
        )
    if entry["source"] == "OCR":
        flags.append("READ BY OCR — check every figure against the notice")
    if entry.get("reply_window_days") and not entry["fields"].get("due_date"):
        flags.append(
            f"Reply due within {entry['reply_window_days']} days of receipt — "
            "the notice prints no calendar date, so the date of service has to "
            "be supplied before this matter can be diarised"
        )
    if entry["missing_fields"]:
        flags.append("Fields not found: " + ", ".join(entry["missing_fields"]))
    if not entry["printed_total"]:
        flags.append("No notice-level total found, so limbs could not be "
                     "reconciled automatically")
    return flags


def write_report(path: Path, entries: List[Dict[str, Any]]):
    lines = [
        "# Extraction report",
        "",
        f"{len(entries)} notice(s). No model calls were made — this cost nothing.",
        "",
        "Check each notice against the figures below. Anything under **Needs "
        "checking** is the product telling you it is unsure; anything not "
        "flagged is the product telling you it is confident, which is not the "
        "same as being right.",
        "",
        "## Summary",
        "",
    ]

    readable = [e for e in entries if not e.get("error")]
    segmented = [e for e in readable if e["limb_count"] > 0]
    reconciled = [e for e in readable if e["reconciles"]]
    checkable = [e for e in readable if e["printed_total"]]
    scanned = [e for e in readable if e["source"] == "OCR"]

    def pct(n, d):
        return f"{n}/{d}" + (f" ({n / d * 100:.0f}%)" if d else "")

    lines += [
        "| Measure | Result |",
        "|---|---|",
        f"| Notices read | {pct(len(readable), len(entries))} |",
        f"| Broke into limbs | {pct(len(segmented), len(readable))} |",
        f"| Limbs reconcile to the notice's own total | "
        f"{pct(len(reconciled), len(checkable))} |",
        f"| Read by OCR | {pct(len(scanned), len(readable))} |",
        f"| Total limbs found | {sum(e['limb_count'] for e in readable)} |",
        f"| Limbs that would convene counsel | "
        f"{sum(e['argued_count'] for e in readable)} |",
        "",
        "**The reconciliation row is the one to watch.** It needs no ground "
        "truth: a notice whose limbs do not add up to the total it prints for "
        "itself has a real extraction defect, whether or not anyone has read it.",
        "",
        "## Notices",
        "",
    ]

    for entry in entries:
        lines.append(f"### {entry['file']}")
        lines.append("")
        if entry.get("error"):
            lines += [f"**Could not be read:** {entry['error']}", ""]
            continue

        fields = entry["fields"]
        lines += [
            f"- Read from: **{entry['source']}** ({entry['text_length']:,} characters)",
            f"- Client: {fields.get('client_name') or '—'}",
            f"- GSTIN: {fields.get('gstin') or '—'}  ·  "
            f"Form: {fields.get('notice_type') or '—'}  ·  "
            f"State: {fields.get('state') or '—'}",
            f"- Period: {fields.get('tax_period') or '—'}  ·  "
            f"Section: {fields.get('section_invoked') or '—'}  ·  "
            f"Reply due: {fields.get('due_date') or '—'}",
            "",
        ]

        if entry["limbs"]:
            lines += ["| # | Limb | Type | Amount |", "|---|---|---|---|"]
            for limb in entry["limbs"]:
                amount = sum((limb.get("amount_by_head") or {}).values())
                shown = "**not read**" if limb.get("amount_unread") \
                    else f"{amount:,.2f}"
                lines.append(
                    f"| {limb.get('index')} | {limb.get('heading', '')[:60]} "
                    f"| {limb.get('type')} | {shown} |"
                )
            lines += [
                "",
                f"Limbs total **{entry['limb_total']:,.2f}** against a printed "
                f"total of **{entry['printed_total']:,.2f}** — "
                + ("reconciles." if entry["reconciles"] else "**does not reconcile.**"),
                "",
            ]

        flags = flags_for(entry)
        if flags:
            lines += ["**Needs checking:**", ""]
            lines += [f"- {flag}" for flag in flags]
            lines.append("")

    path.write_text("\n".join(lines))


def write_review_sheet(path: Path, entries: List[Dict[str, Any]]):
    """
    Where the human supplies the ground truth this tool does not have.

    Filled in, it becomes the record of how extraction performed on real work.
    The two columns that decide readiness are `all_limbs_found` and
    `all_figures_correct` — everything else is diagnosis.
    """
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "file", "read_from", "limbs_found", "limbs_argued",
            "limb_total", "printed_total", "auto_reconciles",
            "--- FILL IN BELOW ---",
            "all_limbs_found_Y_N", "all_figures_correct_Y_N",
            "fields_you_had_to_correct", "minutes_to_verify", "notes",
        ])
        for entry in entries:
            if entry.get("error"):
                writer.writerow([entry["file"], "FAILED", "", "", "", "", "",
                                 "", "", "", "", "", entry["error"]])
                continue
            writer.writerow([
                entry["file"], entry["source"], entry["limb_count"],
                entry["argued_count"], f"{entry['limb_total']:.2f}",
                f"{entry['printed_total']:.2f}",
                "yes" if entry["reconciles"] else "NO",
                "", "", "", "", "", "",
            ])


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract every notice in a folder. No model calls, no cost.")
    parser.add_argument("folder", help="Folder of notices (PDF, DOCX or TXT)")
    parser.add_argument("--out", default="evals/extraction-results",
                        help="Where to write the report and review sheet")
    parser.add_argument("--domain", default="gst")
    args = parser.parse_args()

    root = Path(args.folder).expanduser()
    if not root.exists():
        print(f"No such folder: {root}")
        return 1

    notices = find_notices(root)
    if not notices:
        print(f"No {', '.join(SUPPORTED)} files found in {root}")
        return 1

    engine_ready, reason = ocr.available()
    print(f"Found {len(notices)} notice(s) in {root}")
    if engine_ready:
        print("OCR: available — scanned notices will be read")
    else:
        print(f"OCR: NOT available — {reason}")
        print("     Scanned notices will be reported, not read.")
    print()

    pack = get_pack(args.domain)
    entries = []
    for index, path in enumerate(notices, start=1):
        print(f"[{index}/{len(notices)}] {path.name} … ", end="", flush=True)
        entry = await extract_one(path, pack)
        entries.append(entry)
        if entry.get("error"):
            print("FAILED")
        else:
            status = f"{entry['limb_count']} limb(s)"
            if entry["source"] == "OCR":
                status += ", OCR"
            if entry["printed_total"] and not entry["reconciles"]:
                status += ", DOES NOT RECONCILE"
            elif entry["limb_count"] == 0:
                status += " — NOT SEGMENTED"
            print(status)

    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / "extraction-report.md"
    sheet = out_dir / "review-sheet.csv"
    write_report(report, entries)
    write_review_sheet(sheet, entries)

    readable = [e for e in entries if not e.get("error")]
    segmented = sum(1 for e in readable if e["limb_count"] > 0)
    checkable = [e for e in readable if e["printed_total"]]
    reconciled = sum(1 for e in checkable if e["reconciles"])

    print()
    print("=" * 64)
    print(f"  Read:            {len(readable)}/{len(entries)}")
    print(f"  Segmented:       {segmented}/{len(readable)}")
    print(f"  Reconciled:      {reconciled}/{len(checkable)}"
          f"{' (of those printing a total)' if checkable else ''}")
    print("=" * 64)
    print(f"\nReport:       {report}")
    print(f"Review sheet: {sheet}")
    print("\nFill in the review sheet as you check each notice. Those columns "
          "are the ground truth\nthis tool cannot supply, and they are what "
          "tells you whether extraction is ready.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
