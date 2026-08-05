"""Defects: the unit a tax notice is actually decided in.

WHY THIS EXISTS
---------------
The first version of this product modelled a notice as one dispute with one
amount and one confidence rating. Real notices are not shaped like that, and
the department does not decide them like that.

A Tamil Nadu scrutiny notice for a GSTR-9C filer arrives as a parameter-wise
list of defects — short payment, turnover difference, credit notes, ITC excess
against 2B, blocked credit under s.17(5), late fee, e-invoicing, interest on
amendments — each with its own annexure of figures. The officer then answers
them one at a time. In the matter this module was designed against, the
adjudication order says "Hence this defect is dropped" eight separate times.

So a defect, not a notice, is the unit of work. Each one carries its own
allegation, its own arithmetic split across tax heads, its own posture, its own
evidence, its own annexures and its own line in the prayer. A reply that meets
the notice as a single number concedes ground it never needed to concede, and
cannot express the position that actually wins: contest this limb, pay that one
under protest, and concede the third outright.

POSTURES
--------
The five postures below are not a severity scale. They are the five different
things a reply can say about a limb of a notice, and each one produces
materially different drafting:

    explained           the arithmetic is wrong or the documents answer it.
                        Leads with facts and reconciliation. No advocacy.
    contested           the LAW is wrong. Leads with statute and authority.
                        This is the only posture that needs counsel.
    agreed_paid         conceded and discharged. Needs an interest computation
                        and a DRC-03 reference, not an argument.
    paid_under_protest  paid without prejudice on commercial grounds, with the
                        right to refund expressly reserved.
    partial             the limb splits. Carries `splits`, each with its own
                        posture and its own amount.

`undecided` is the honest default. A defect that reaches the export still
undecided is reported as such rather than being quietly assigned a position.
"""

import re
from typing import Any, Dict, Iterable, List, Optional

# ---------------------------------------------------------------------------
# Postures
# ---------------------------------------------------------------------------

EXPLAINED = "explained"
CONTESTED = "contested"
AGREED_PAID = "agreed_paid"
PAID_UNDER_PROTEST = "paid_under_protest"
PARTIAL = "partial"
UNDECIDED = "undecided"

POSTURES = (EXPLAINED, CONTESTED, AGREED_PAID, PAID_UNDER_PROTEST, PARTIAL,
            UNDECIDED)

# How each posture is described to a reader of the reply pack.
POSTURE_LABEL = {
    EXPLAINED: "Explained — drop requested",
    CONTESTED: "Contested",
    AGREED_PAID: "Agreed and paid",
    PAID_UNDER_PROTEST: "Paid under protest",
    PARTIAL: "Part contested, part discharged",
    UNDECIDED: "Not yet settled",
}

# The verb that opens this defect's row in the prayer.
POSTURE_RELIEF_VERB = {
    EXPLAINED: "DROP",
    CONTESTED: "DROP",
    AGREED_PAID: "ACKNOWLEDGE",
    PAID_UNDER_PROTEST: "TAKE ON RECORD",
    PARTIAL: "DROP in part and TAKE ON RECORD in part",
    UNDECIDED: "CONSIDER",
}

# Only these postures need four counsel and a cross-examination round. The
# others are answered with arithmetic, documents or a payment — spending a
# panel on them buys nothing and costs real money on every matter.
PANEL_POSTURES = frozenset({CONTESTED, PARTIAL, UNDECIDED})

TAX_HEADS = ("igst", "cgst", "sgst", "cess")


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------


def empty_heads() -> Dict[str, float]:
    return {head: 0.0 for head in TAX_HEADS}


def normalise_heads(value: Any) -> Dict[str, float]:
    """
    Coerce whatever the caller supplied into a head-wise dict.

    A bare number is treated as an unallocated total rather than being guessed
    into a head — putting an IGST figure in the CGST column is the kind of
    error that survives review and surfaces in front of the officer.
    """
    heads = empty_heads()
    if value in (None, "", []):
        return heads
    if isinstance(value, (int, float)):
        heads["unallocated"] = float(value)
        return heads
    if isinstance(value, dict):
        for key, amount in value.items():
            key = str(key).strip().lower()
            if key in TAX_HEADS or key == "unallocated":
                try:
                    heads[key] = float(amount or 0)
                except (TypeError, ValueError):
                    continue
    return heads


def total_of(heads: Any) -> float:
    """Sum a head-wise dict. Accepts a bare number for convenience."""
    if isinstance(heads, (int, float)):
        return float(heads)
    return round(sum(float(v or 0) for v in normalise_heads(heads).values()), 2)


def add_heads(*groups: Any) -> Dict[str, float]:
    """Add head-wise dicts together, preserving the head split."""
    out: Dict[str, float] = {}
    for group in groups:
        for key, amount in normalise_heads(group).items():
            if amount:
                out[key] = round(out.get(key, 0.0) + float(amount), 2)
    return out


def format_heads(heads: Any) -> str:
    """Render a head split the way a reply states it: 'CGST 58,366 + SGST 58,366'."""
    parts = []
    normalised = normalise_heads(heads)
    for head in TAX_HEADS + ("unallocated",):
        amount = normalised.get(head) or 0
        if amount:
            label = "" if head == "unallocated" else head.upper() + " "
            parts.append(f"{label}{indian_number(amount)}")
    return " + ".join(parts) if parts else "—"


def indian_number(value: Any) -> str:
    """Indian digit grouping: 1,23,716.68 rather than 123,716.68."""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    negative = amount < 0
    amount = abs(amount)
    whole = int(amount)
    paise = round(amount - whole, 2)
    text = str(whole)
    if len(text) > 3:
        head, tail = text[:-3], text[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        text = ",".join(groups + [tail])
    if paise:
        text = f"{text}.{int(round(paise * 100)):02d}"
    return ("-" if negative else "") + text


# ---------------------------------------------------------------------------
# The defect record
# ---------------------------------------------------------------------------


def new_defect(
    index: int,
    heading: str,
    defect_type: str = "other",
    **fields: Any,
) -> Dict[str, Any]:
    """
    Build a defect record with every key present.

    Records are plain dicts rather than a class so they round-trip through JSON
    storage and the SSE stream without a serialisation layer. The cost is that
    every producer must agree on the shape, which is why this constructor is the
    only sanctioned way to make one.
    """
    defect: Dict[str, Any] = {
        "index": index,
        "type": defect_type,
        "heading": heading,

        # What the notice says, in the notice's own words, plus any table it
        # annexed in support.
        "department_contention": fields.get("department_contention", ""),
        "notice_extract": fields.get("notice_extract", ""),
        "tables": fields.get("tables") or [],

        # Statute. Sections are held with their sub-sections intact —
        # "16(2)(aa)", never "16".
        "sections": list(fields.get("sections") or []),
        "rules": list(fields.get("rules") or []),
        "statute": fields.get("statute", ""),

        # Money, split by head. `amount_by_head` is what the notice alleges;
        # `conceded_by_head` and `contested_by_head` are how the reply answers
        # it, and must add back to it.
        "amount_by_head": normalise_heads(fields.get("amount_by_head")),
        "conceded_by_head": normalise_heads(fields.get("conceded_by_head")),
        "contested_by_head": normalise_heads(fields.get("contested_by_head")),

        # Position
        "posture": fields.get("posture", UNDECIDED),
        "splits": list(fields.get("splits") or []),
        "our_position": fields.get("our_position", ""),
        "facts": fields.get("facts", ""),
        "legal_framework": list(fields.get("legal_framework") or []),
        "authorities": list(fields.get("authorities") or []),
        "strength": fields.get("strength", ""),

        # Evidence. The gap between what the officer will demand and what the
        # client actually holds is the single most valuable thing this product
        # produces — it is what decides matters that are otherwise won.
        "evidence_required": list(fields.get("evidence_required") or []),
        "evidence_held": list(fields.get("evidence_held") or []),
        "evidence_gap": list(fields.get("evidence_gap") or []),
        "annexures": list(fields.get("annexures") or []),

        # Discharge
        "payment": fields.get("payment") or {},

        # Drafting output
        "submission": fields.get("submission", ""),
        "prayer_relief": fields.get("prayer_relief", ""),

        # Provenance: did a human confirm this, or is it still a proposal?
        "source": fields.get("source", "notice"),
        "confirmed": bool(fields.get("confirmed", False)),
    }
    return defect


def defect_total(defect: Dict[str, Any]) -> float:
    return total_of(defect.get("amount_by_head"))


def matter_total(defects: Iterable[Dict[str, Any]]) -> float:
    return round(sum(defect_total(d) for d in defects), 2)


def needs_panel(defect: Dict[str, Any]) -> bool:
    """Is this defect worth convening four counsel over?"""
    return defect.get("posture", UNDECIDED) in PANEL_POSTURES


def triage(defects: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Split defects into those that need argument and those that need arithmetic.

    This is the cost control and the quality control at once. On a real
    eight-defect scrutiny notice, six limbs are answered by reconciliation,
    documents or a payment; convening a full adversarial panel on those six
    produces prose where a table was wanted, and pays four frontier models to
    generate it.
    """
    argue = [d for d in defects if needs_panel(d)]
    settle = [d for d in defects if not needs_panel(d)]
    return {
        "argue": argue,
        "settle": settle,
        "argue_count": len(argue),
        "settle_count": len(settle),
        "total_count": len(defects),
        "argued_amount": matter_total(argue),
        "settled_amount": matter_total(settle),
        "total_amount": matter_total(defects),
    }


def validate(defect: Dict[str, Any]) -> List[str]:
    """
    Problems that must be resolved before this defect can be filed on.

    Returned rather than raised: a half-settled defect is a normal state during
    preparation, and the reviewer needs to see every problem at once rather
    than the first one.
    """
    problems: List[str] = []
    posture = defect.get("posture", UNDECIDED)
    heading = defect.get("heading") or f"Defect {defect.get('index', '?')}"

    if posture not in POSTURES:
        problems.append(f"{heading}: unknown posture '{posture}'.")

    if posture == UNDECIDED:
        problems.append(
            f"{heading}: no position has been settled. Every defect must carry "
            "a posture before the reply is filed."
        )

    if posture in (AGREED_PAID, PAID_UNDER_PROTEST):
        payment = defect.get("payment") or {}
        if not payment.get("reference"):
            problems.append(
                f"{heading}: {POSTURE_LABEL[posture].lower()} but no DRC-03 "
                "reference is recorded. The officer closes a conceded limb on "
                "the payment reference, not on the concession."
            )

    if posture == PARTIAL:
        if not defect.get("splits"):
            problems.append(
                f"{heading}: marked as part-contested but no split is recorded. "
                "State which amount is contested and which is discharged."
            )
        else:
            split_total = round(
                sum(total_of(s.get("amount_by_head")) for s in defect["splits"]), 2
            )
            alleged = defect_total(defect)
            if alleged and abs(split_total - alleged) > 1.0:
                problems.append(
                    f"{heading}: the splits total {indian_number(split_total)} "
                    f"but the notice alleges {indian_number(alleged)}. These "
                    "must reconcile."
                )

    if posture in (EXPLAINED, CONTESTED, PARTIAL) and not defect.get("annexures"):
        problems.append(
            f"{heading}: no annexure is listed. A limb answered on documents "
            "needs the documents identified and indexed."
        )

    if defect.get("evidence_gap"):
        problems.append(
            f"{heading}: evidence gap outstanding — "
            + "; ".join(str(g) for g in defect["evidence_gap"])
        )

    return problems


def validate_all(defects: List[Dict[str, Any]]) -> List[str]:
    problems: List[str] = []
    for defect in defects:
        problems.extend(validate(defect))
    return problems


# ---------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------

# The department numbers its own limbs in the adjudication order: "Defect -1:",
# "Defect - 2 :". Where that numbering is present it is authoritative, because
# it is the numbering the officer will answer against.
DEFECT_MARKER_RE = re.compile(
    r"^\s*[•\-\*]?\s*Defect\s*[-–—]?\s*(\d{1,2})\s*[:.]?\s*(.*)$",
    re.IGNORECASE | re.MULTILINE,
)

# The scrutiny notice itself uses bulleted parameter headings instead.
BULLET_HEADING_RE = re.compile(
    r"^\s*[•‣▪]\s*(.{3,90}?)\s*:\s*$", re.MULTILINE,
)

# A plainly numbered heading: "1. Short payment of tax on outward supplies".
#
# This is how most departmental notices actually number their limbs — far more
# often than they write "Defect -1:", which is an adjudication-order
# convention. Without this signal a notice numbered 1., 2., 3. fell through to
# the catalogue fallback below, which can only ever produce ONE limb per
# defect type: an RFD-08 raising two distinct refund objections came back as a
# single limb carrying both figures, and a DRC-01B raising one came back with
# none at all.
NUMBERED_HEADING_RE = re.compile(
    r"^\s*(\d{1,2})\s*[.)]\s+(\S.{5,118})$", re.MULTILINE,
)


def find_defect_headings(text: str, catalogue: Iterable[Any]) -> List[Dict[str, Any]]:
    """
    Locate every defect heading in a notice, in document order.

    Three signals, and they are NOT merged — the strongest available one decides
    the boundaries on its own:

    1.  The department's own "Defect -N" numbering, used in adjudication orders.
        Where present this is authoritative, because it is the numbering the
        officer answers against and the numbering the reply must mirror.
    2.  Bulleted parameter headings, used in the scrutiny notice itself.
    3.  Catalogue patterns, for notices that run their headings into prose.

    Mixing signals was the first implementation and it over-counted badly: an
    order carries BOTH "Defect -1:" and the bulleted heading beneath it, and
    treating each as a boundary split every limb in two and inserted the
    department's own section banners ("Output turnover discrepancies") as
    phantom defects. When numbering is present the bullets inside a segment are
    demoted to what they actually are — the heading text for that segment.
    """
    markers = [
        {
            "start": match.start(),
            "trailing": (match.group(2) or "").strip(),
            "declared_index": int(match.group(1)),
            "signal": "numbered",
        }
        for match in DEFECT_MARKER_RE.finditer(text)
    ]

    bullets = [
        {
            "start": match.start(),
            "heading": match.group(1).strip(),
            "declared_index": None,
            "signal": "bullet",
        }
        for match in BULLET_HEADING_RE.finditer(text)
    ]

    if markers:
        found = []
        for position, marker in enumerate(markers):
            end = (markers[position + 1]["start"]
                   if position + 1 < len(markers) else len(text))
            # The department's own bulleted heading inside this segment names
            # the limb far better than the bare "Defect -N" does.
            inner = next(
                (b["heading"] for b in bullets
                 if marker["start"] <= b["start"] < end), "",
            )
            found.append({
                "start": marker["start"],
                "heading": inner or marker["trailing"]
                           or f"Defect {marker['declared_index']}",
                "declared_index": marker["declared_index"],
                "signal": "numbered",
            })
        return found

    if bullets:
        return bullets

    numbered = _numbered_headings(text, catalogue)
    if numbered:
        return numbered

    found = []
    seen_spans: List[tuple] = []
    for entry in catalogue:
        for pattern in entry.patterns:
            match = pattern.search(text)
            if not match:
                continue
            if any(not (match.end() <= s or match.start() >= e)
                   for s, e in seen_spans):
                continue
            found.append({
                "start": match.start(),
                "heading": entry.label,
                "declared_index": None,
                "signal": "catalogue",
            })
            seen_spans.append(match.span())
            break

    found.sort(key=lambda f: f["start"])
    return found


def _numbered_headings(text: str, catalogue: Iterable[Any]) -> List[Dict[str, Any]]:
    """
    Numbered lines that are genuinely defect headings.

    The numbering alone is not enough of a signal — a notice is full of
    numbered prose, numbered annexure references and numbered sub-clauses. So
    a candidate line qualifies only if the heading text ITSELF matches a
    catalogue pattern. Numbering says "this is a boundary"; the catalogue says
    "this is a defect"; both are required.

    That combination is also what keeps the metadata block out. "ARN of refund
    application: AA240925004417P" matches the refund pattern but carries no
    number, and "1." on its own matches no pattern, so neither becomes a limb.

    The declared numbers must ascend. A run that jumps around is a list inside
    a paragraph rather than the notice's own limb numbering.
    """
    candidates = []
    for match in NUMBERED_HEADING_RE.finditer(text):
        heading = match.group(2).strip()
        # Trailing full stops mean a sentence, not a heading. Departmental
        # headings do not carry them, and requiring their absence removes most
        # of the numbered prose that would otherwise qualify.
        if heading.endswith("."):
            continue
        if not any(pattern.search(heading)
                   for entry in catalogue for pattern in entry.patterns):
            continue
        candidates.append({
            "start": match.start(),
            "heading": heading,
            "declared_index": int(match.group(1)),
            "signal": "numbered-plain",
        })

    if len(candidates) < 1:
        return []

    ascending = [candidates[0]]
    for candidate in candidates[1:]:
        if candidate["declared_index"] > ascending[-1]["declared_index"]:
            ascending.append(candidate)
    return ascending


def classify_heading(heading: str, body: str, catalogue: Iterable[Any]) -> Any:
    """
    Match a heading to a catalogue entry.

    The heading is tested first and carries far more weight than the body: a
    credit-note defect mentions ITC, and an ITC defect mentions credit notes,
    so scoring them equally reliably mislabels both.
    """
    best, best_score = None, 0
    for entry in catalogue:
        score = 0
        for pattern in entry.patterns:
            if pattern.search(heading or ""):
                score += 10
            elif pattern.search(body or ""):
                score += 1
        if score > best_score:
            best, best_score = entry, score
    return best


# Where the operative part of a notice stops and the detailed annexures begin.
# Everything after this belongs to the notice as a whole, not to the last
# defect — without the boundary the final limb absorbs every annexure in the
# document and its figures come out orders of magnitude wrong.
ANNEXURE_BOUNDARY_RE = re.compile(
    r"(?:"
    r"For\s+the\s+above\s+discrepanc\w+\s*,?\s*kindly\s+substantiate"
    r"|In\s+case\s+of\s+accepted\s+discrepancy"
    r"|^\s*Proper\s+officer\s*$"
    r"|^\s*GSTIN\s*:\s*\w{15}\s+Name\s*:"
    r")",
    re.IGNORECASE | re.MULTILINE,
)


def operative_region(text: str) -> str:
    """
    The part of a notice that states the defects, with annexures trimmed off.

    Trimming is refused if it would remove most of the document — a short
    notice whose boundary phrase appears early would otherwise be gutted.

    EVERY candidate boundary is considered, not just the first. One of the
    boundary patterns is the repeated `GSTIN : ... Name : ...` block that heads
    an annexure — and that is also the shape of the notice's OWN header, which
    the portal prints in the first few lines. Testing only the first match
    therefore found the header at around 1% of the document, declined to trim
    on the "would gut it" guard, and returned the whole notice: the real
    boundary further down was never reached, and the last limb went on to
    absorb every annexure in the file. That is the failure that once read a
    Rs. 44 interest limb as Rs. 1.24 crore, and it was live for any notice
    carrying a standard portal header.
    """
    text = text or ""
    for match in ANNEXURE_BOUNDARY_RE.finditer(text):
        if match.start() >= len(text) * 0.3:
            return text[:match.start()]
    return text


def segment(text: str, catalogue: Iterable[Any]) -> List[Dict[str, Any]]:
    """
    Split a notice into defect records.

    Returns [] when nothing defect-shaped is found, which the caller must treat
    as "this notice needs manual decomposition" rather than "this notice has no
    defects".
    """
    catalogue = list(catalogue)
    text = operative_region(text)
    headings = find_defect_headings(text, catalogue)
    if not headings:
        return []

    defects: List[Dict[str, Any]] = []
    for position, entry in enumerate(headings):
        start = entry["start"]
        end = (headings[position + 1]["start"]
               if position + 1 < len(headings) else len(text))
        body = text[start:end].strip()

        matched = classify_heading(entry["heading"], body, catalogue)
        defects.append(new_defect(
            index=entry["declared_index"] or (position + 1),
            heading=entry["heading"] or (matched.label if matched else "Defect"),
            defect_type=matched.key if matched else "other",
            notice_extract=body,
            department_contention=_first_sentences(body),
            sections=list(matched.sections) if matched else [],
            rules=list(matched.rules) if matched else [],
            statute=matched.statute if matched else "",
            posture=matched.default_posture if matched else UNDECIDED,
            evidence_required=list(matched.evidence_required) if matched else [],
            source="notice",
        ))

    # Text before the first heading belongs to no defect, but departmental PDFs
    # do not always emit in reading order — the Tamil Nadu scrutiny attachment
    # prints the first limb's table ABOVE its own bullet heading, so the figures
    # land in this preamble. It is offered to the first defect only, and only
    # when that defect has no figures of its own, so no later limb can be given
    # a number that belongs to its neighbour.
    if defects and headings[0]["start"] > 0:
        defects[0]["preamble"] = text[:headings[0]["start"]].strip()

    return defects


def _first_sentences(body: str, limit: int = 3) -> str:
    """The operative opening of a defect, for the 'Disputes at a Glance' table."""
    cleaned = re.sub(r"\s+", " ", body or "").strip()
    if not cleaned:
        return ""
    sentences = re.split(r"(?<=[.:])\s+", cleaned)
    return " ".join(sentences[:limit])[:800]
