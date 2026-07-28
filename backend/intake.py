"""Notice ingestion.

A partner will not retype a notice into a form. Until the notice can be
uploaded, nothing else about this product matters.

The design principle here is that a GST notice is a highly structured
document, so most of the intake form can be filled WITHOUT a model at all:

    GSTIN            fixed 15-character format
    State            derived from the first two digits of the GSTIN
    Notice type      the form code appears literally in the document
    Reference number labelled and formatted
    Dates            a handful of Indian conventions
    Amounts          labelled with Rs./INR
    Section invoked  "section 73", "u/s 61"
    Tax period       "FY 2019-20", "2019-20"

Regex on a known format beats a model on every axis that matters here: it is
free, it is deterministic, it cannot hallucinate a GSTIN, and — the point that
decides it — nothing has to leave the machine.

A model is used for exactly the two fields regex cannot do: what the issues
are, and a summary of the facts. On the draft tier even that text is
anonymised first, so an uploaded notice is no less private than a typed one.

Scanned notices with no text layer are detected and reported honestly rather
than guessed at. OCR is deliberately out of scope: adding it would pull in a
heavy dependency to serve the minority of notices that are not already
digital, and a wrong OCR read is worse than an empty field.
"""

import io
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from . import config, defects, notice_tables, sanitizer
from .openrouter import query_model

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
SUPPORTED = (".pdf", ".docx", ".txt")

# Text below this length almost certainly means a scanned page with no text
# layer rather than a genuinely short notice.
MIN_USEFUL_TEXT = 200

# How much of the notice reaches the model.
#
# This was 12,000, on the reasoning that the operative part of a notice is at
# the front. It is not. A real scrutiny attachment ran to 21,000 characters
# with its last three defects — including the only limb that went on to a show
# cause notice — beyond the cut, and they were never read at all. Defect
# segmentation now happens locally over the whole document, so the model sees
# the notice for context rather than for structure, but it still must see the
# operative part in full.
MAX_MODEL_CHARS = int(os.getenv("MAX_NOTICE_MODEL_CHARS", "48000"))


# ---------------------------------------------------------------------------
# GSTIN state codes — the first two digits identify the State, which drives
# the jurisdiction weighting. Deriving it costs nothing and is more reliable
# than asking anyone to pick from a dropdown of 36.
# ---------------------------------------------------------------------------

GSTIN_STATE_CODES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana", "07": "Delhi",
    "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
    "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam",
    "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra",
    "29": "Karnataka", "30": "Goa", "31": "Lakshadweep", "32": "Kerala",
    "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman and Nicobar Islands", "36": "Telangana",
    "37": "Andhra Pradesh", "38": "Ladakh",
}

GSTIN_RE = re.compile(r"\b(\d{2})[A-Z]{5}\d{4}[A-Z][0-9A-Z]{3}\b")

# Portal-issued identifiers. These are the handles the officer files the matter
# under, and a reply that does not quote them can be rejected on its face.
#
# The shape is fixed: two letters, a run of digits, then a check character —
# ZD330226255583F for a scrutiny reference, AD330226081676X for an ARN. The
# first version of this matched on the WORD "notice" followed by capitals and
# duly extracted the reference "proposing" from a sentence, so the anchor is
# now the identifier's own format rather than the label beside it.
PORTAL_ID_RE = re.compile(r"\b([A-Z]{2}\d{10,14}[A-Z0-9])\b")

REFERENCE_RE = re.compile(
    r"(?:reference|ref|scrutiny\s+ref)\.?\s*(?:no|number)?\.?\s*[:\-]?\s*"
    r"([A-Z]{2}\d{10,14}[A-Z0-9])",
    re.IGNORECASE,
)

ARN_RE = re.compile(
    r"\bARN\s*[:\-]?\s*([A-Z]{2}\d{10,14}[A-Z0-9])", re.IGNORECASE
)

# Document Identification Number. Circular 128/2/2020-GST makes it mandatory,
# and its absence is a live ground of challenge — so it is captured whether or
# not the notice bothers to supply it.
DIN_RE = re.compile(r"\bDIN\s*[:\-]?\s*([A-Z0-9]{15,25})\b", re.IGNORECASE)

# 14.06.2026 / 14-06-2026 / 14/06/2026
NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})\b")
# 14 June 2026 / 14th June, 2026
TEXT_DATE_RE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\,?\s+(\d{4})\b",
    re.IGNORECASE,
)
MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}

AMOUNT_RE = re.compile(
    r"(?:Rs\.?|INR|₹)\s*([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE
)

FY_RE = re.compile(
    r"(?:F\.?Y\.?|financial\s+year|tax\s+period)\s*[:\-]?\s*(\d{4})\s*[-–/]\s*(\d{2,4})",
    re.IGNORECASE,
)
BARE_FY_RE = re.compile(r"\b(20\d{2})\s*[-–]\s*(\d{2})\b")

# Statutory references, WITH their sub-sections.
#
# The earlier version captured "16" from "section 16(2)(aa)" and then took only
# the first match in the whole notice. On a real scrutiny notice that reported
# the single provision "9" — read out of the phrase "section 9(5), if
# applicable" in boilerplate — for a notice issued under section 61. The
# sub-section is not a detail here: 16(2)(aa) and 16(4) are different disputes
# with different defences, and "16" names neither of them.
SECTION_RE = re.compile(
    r"(?:section|sec\.?|u/s)\s*(\d{1,3}[A-Z]?(?:\s*\(\s*[0-9a-zA-Z]{1,3}\s*\))*)",
    re.IGNORECASE,
)

RULE_RE = re.compile(
    r"\brules?\s*(\d{1,3}[A-Z]?(?:\s*\(\s*[0-9a-zA-Z]{1,3}\s*\))*)",
    re.IGNORECASE,
)

# The portal form states the provision in a labelled row. Where that row is
# present it is authoritative and beats anything scraped from the prose.
LABELLED_SECTION_RE = re.compile(
    r"Section\s+under\s+which\s+(?:the\s+)?notice\s+is\s+issued\s*[:\-]?\s*"
    r"(\d{1,3}[A-Z]?)",
    re.IGNORECASE,
)

LABELLED_DUE_DATE_RE = re.compile(
    r"Date\s+by\s+which\s+(?:the\s+)?reply\s+(?:has\s+to\s+be|is\s+to\s+be|to\s+be)"
    r"\s+submitted\s*[:\-]?\s*(\d{1,2}[./\-]\d{1,2}[./\-]\d{4})",
    re.IGNORECASE,
)

LABELLED_NOTICE_DATE_RE = re.compile(
    r"Reference\s*No\.?\s*[:\-]?\s*[A-Z0-9]+\s*Date\s*[:\-]?\s*"
    r"(\d{1,2}[./\-]\d{1,2}[./\-]\d{4})",
    re.IGNORECASE,
)

# The issuing officer, from the portal form's signature block.
OFFICER_NAME_RE = re.compile(
    r"Signature\s*\n?\s*Name\s*[:\-]\s*([A-Za-z][A-Za-z.\s]{2,40}?)\s*\n",
    re.IGNORECASE,
)
OFFICER_DESIGNATION_RE = re.compile(
    r"Designation\s*[:\-]\s*([A-Za-z()/,.\s]{4,60}?)\s*\n", re.IGNORECASE
)
# Jurisdiction runs onto a second line in the portal form ("RAM NAGAR ,
# Coimbatore-\nII , COIMBATORE , Tamil Nadu"), so a single-line match truncates
# the circle name mid-word.
JURISDICTION_RE = re.compile(
    r"Jurisdiction\s*[:\-]\s*([^\n]{3,90}(?:\n[^\n:]{1,60})?)", re.IGNORECASE
)
CIRCLE_RE = re.compile(
    r"Circle\s*[:\-]\s*([A-Za-z0-9 \-]{3,40})", re.IGNORECASE
)

# Entity name, identified by its statutory suffix.
#
# This is extracted locally for two reasons, and the second matters more: it
# fills the client name field, AND it gives the sanitiser something to scrub.
# Without it the draft tier strips the GSTIN and PAN but leaves the company
# name standing in the notice text — which is exactly the leak the test suite
# caught.
# The suffix group is case-insensitive but the name itself is not. Notices
# print the taxpayer in full capitals — "GRAM ENVOSOLUTION PRIVATE LIMITED" —
# and a wholly case-sensitive pattern silently found nothing on every one of
# them, leaving the sanitiser with no company name to scrub. Making the WHOLE
# pattern case-insensitive is not the fix either: it then matches ordinary
# prose such as "the limited relief sought".
ENTITY_RE = re.compile(
    r"\b((?:[A-Z][\w&.'\-]*\s+){1,6}"
    r"(?i:PRIVATE\s+LIMITED|PVT\.?\s*LTD\.?|PUBLIC\s+LIMITED|LIMITED|LTD\.?"
    r"|LLP|LIMITED\s+LIABILITY\s+PARTNERSHIP|&\s*CO\.?|AND\s+COMPANY"
    r"|&\s*SONS|ENTERPRISES|INDUSTRIES|ASSOCIATES|TRADERS|AGENCIES"
    r"|ELECTRICALS|HOTELS))\b"
)

# "Tvl." (Tamil Nadu), "M/s." and "Messrs." introduce the taxpayer by name and
# are the most reliable signal of all where present.
PREFIXED_ENTITY_RE = re.compile(
    r"(?:M/s\.?|Tvl\.?|Messrs\.?)\s+"
    r"([A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,7})"
)

DUE_DATE_HINT_RE = re.compile(
    r"(?:reply|response|submit|furnish|show cause)[^.]{0,120}?"
    r"(?:on or before|within|by)\s+([^.\n]{0,60})",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


def extract_text(filename: str, content: bytes) -> Tuple[str, List[str]]:
    """
    Pull text out of an uploaded notice. Entirely local — nothing is sent
    anywhere at this stage.

    Returns (text, warnings). Warnings are shown to the user rather than
    swallowed: an empty field they can see is safe, one they cannot is not.
    """
    warnings: List[str] = []
    name = (filename or "").lower()

    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
        )
    if not any(name.endswith(ext) for ext in SUPPORTED):
        raise ValueError(
            f"Unsupported file type. Upload one of: {', '.join(SUPPORTED)}."
        )

    text = ""
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted:
                try:
                    reader.decrypt("")
                except Exception:
                    raise ValueError(
                        "This PDF is password protected. Remove the password "
                        "and upload again."
                    )
            pages = []
            for page in reader.pages:
                try:
                    pages.append(page.extract_text() or "")
                except Exception:
                    warnings.append("One page could not be read and was skipped.")
            text = "\n".join(pages)
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Could not read the PDF: {e}")

    elif name.endswith(".docx"):
        try:
            from docx import Document
            document = Document(io.BytesIO(content))
            parts = [p.text for p in document.paragraphs]
            for table in document.tables:
                for row in table.rows:
                    parts.extend(cell.text for cell in row.cells)
            text = "\n".join(parts)
        except Exception as e:
            raise ValueError(f"Could not read the document: {e}")

    else:
        for encoding in ("utf-8", "utf-16", "latin-1"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

    text = re.sub(r"[ \t]+", " ", text or "")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    if len(text) < MIN_USEFUL_TEXT:
        warnings.append(
            "Very little text could be read. This is usually a scanned notice "
            "with no text layer — paste the text of the notice manually, or "
            "upload a digitally generated copy."
        )

    return text, warnings


# ---------------------------------------------------------------------------
# Local field extraction — no model, nothing leaves the machine
# ---------------------------------------------------------------------------


def _iso_date(day: int, month: int, year: int) -> Optional[str]:
    if not (1 <= month <= 12 and 1 <= day <= 31 and 1900 < year < 2200):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def find_dates(text: str) -> List[str]:
    """All dates in the notice, in document order, as ISO strings."""
    found: List[Tuple[int, str]] = []
    for match in NUMERIC_DATE_RE.finditer(text):
        day, month, year = (int(g) for g in match.groups())
        iso = _iso_date(day, month, year)
        if iso:
            found.append((match.start(), iso))
    for match in TEXT_DATE_RE.finditer(text):
        day, month_name, year = match.groups()
        iso = _iso_date(int(day), MONTHS[month_name.lower()], int(year))
        if iso:
            found.append((match.start(), iso))
    found.sort()
    seen, ordered = set(), []
    for _, iso in found:
        if iso not in seen:
            seen.add(iso)
            ordered.append(iso)
    return ordered


def find_notice_type(text: str, pack) -> Optional[str]:
    """
    Identify the form code. Longest codes are matched first so that DRC-01A is
    never mistaken for DRC-01.
    """
    codes = sorted(
        (c for c in pack.NOTICE_TYPES if c != "OTHER"),
        key=len, reverse=True,
    )
    upper = text.upper()
    for code in codes:
        # Tolerate ASMT-10, ASMT 10, ASMT10 and "GST ASMT - 10", which is how
        # the portal actually prints the form header.
        pattern = code.replace("-", r"[\s\-]*")
        if re.search(rf"\b{pattern}\b", upper):
            return code
    return None


def find_sections(text: str) -> List[str]:
    """
    Every statutory section in the text, sub-sections intact, in document order.

    Deduplicated but never truncated to one: a notice engages several
    provisions and the reply has to answer each of them.
    """
    return _collect(SECTION_RE, text)


def find_rules(text: str) -> List[str]:
    return _collect(RULE_RE, text)


def _collect(pattern: re.Pattern, text: str) -> List[str]:
    seen, ordered = set(), []
    for match in pattern.finditer(text or ""):
        # "16 ( 2 ) ( aa )" and "16(2)(aa)" are the same provision.
        reference = re.sub(r"\s+", "", match.group(1))
        if reference and reference not in seen:
            seen.add(reference)
            ordered.append(reference)
    return ordered


def find_entity_name(text: str) -> Optional[str]:
    """
    The taxpayer's name.

    A "Tvl."/"M/s." prefix is the strongest signal and is preferred outright.
    Failing that, the statutory suffix is used and the longest match wins, so
    "Acme Steel Industries Private Limited" is not truncated to "Acme Steel
    Industries".
    """
    prefixed = [m.group(1).strip(" .,") for m in PREFIXED_ENTITY_RE.finditer(text or "")]
    if prefixed:
        return max(prefixed, key=len)
    candidates = [m.group(1).strip() for m in ENTITY_RE.finditer(text or "")]
    if not candidates:
        return None
    return max(candidates, key=len)


def find_amounts(text: str) -> List[float]:
    amounts = []
    for match in AMOUNT_RE.finditer(text):
        try:
            amounts.append(float(match.group(1).replace(",", "")))
        except ValueError:
            continue
    return amounts


def find_tax_period(text: str) -> Optional[str]:
    match = FY_RE.search(text)
    if not match:
        match = BARE_FY_RE.search(text)
    if not match:
        return None
    start, end = match.group(1), match.group(2)
    if len(end) == 4:
        end = end[2:]
    return f"FY {start}-{end}"


def _iso_from_numeric(raw: str) -> Optional[str]:
    match = NUMERIC_DATE_RE.search(raw or "")
    if not match:
        return None
    day, month, year = (int(g) for g in match.groups())
    return _iso_date(day, month, year)


def extract_fields_local(text: str, pack) -> Dict[str, Any]:
    """
    Everything derivable without a model.

    Each field carries where it came from, so the UI can show the user what was
    read off the notice versus what a model proposed.

    Dates and the provision invoked are taken from the portal form's LABELLED
    rows wherever those rows exist, and only fall back to position heuristics
    when they do not. The heuristics that used to run unconditionally — first
    date in the document is the notice date, last date is the deadline — read a
    rate-notification date from 2022 as the date of a 2026 notice and an
    invoice date from an annexure as the reply deadline. Position is a poor
    proxy for meaning in a document that carries dozens of dates.
    """
    fields: Dict[str, Any] = {}
    sources: Dict[str, str] = {}

    def put(key: str, value: Any, source: str):
        if value not in (None, "", []):
            fields[key] = value
            sources[key] = source

    gstin_match = GSTIN_RE.search(text)
    if gstin_match:
        put("gstin", gstin_match.group(0), "notice")
        put("state", GSTIN_STATE_CODES.get(gstin_match.group(1)), "gstin")

    put("client_name", find_entity_name(text), "notice")
    put("notice_type", find_notice_type(text, pack), "notice")
    put("tax_period", find_tax_period(text), "notice")

    # --- Identifiers ------------------------------------------------------
    reference = REFERENCE_RE.search(text)
    if reference:
        put("notice_reference", reference.group(1).strip(), "notice")
    else:
        loose = PORTAL_ID_RE.search(text)
        if loose:
            put("notice_reference", loose.group(1), "notice")

    arn = ARN_RE.search(text)
    if arn:
        put("notice_arn", arn.group(1), "notice")

    din = DIN_RE.search(text)
    if din:
        put("din", din.group(1), "notice")

    # --- Provision invoked ------------------------------------------------
    labelled_section = LABELLED_SECTION_RE.search(text)
    sections = find_sections(text)
    if labelled_section:
        put("section_invoked", labelled_section.group(1), "notice-labelled")
    elif sections:
        put("section_invoked", sections[0], "notice")
    put("sections_cited", sections, "notice")
    put("rules_cited", find_rules(text), "notice")

    # --- Dates ------------------------------------------------------------
    labelled_notice_date = LABELLED_NOTICE_DATE_RE.search(text)
    if labelled_notice_date:
        put("notice_date", _iso_from_numeric(labelled_notice_date.group(1)),
            "notice-labelled")

    labelled_due = LABELLED_DUE_DATE_RE.search(text)
    if labelled_due:
        put("due_date", _iso_from_numeric(labelled_due.group(1)),
            "notice-labelled")

    if not fields.get("notice_date"):
        dates = find_dates(text)
        if dates:
            put("notice_date", dates[0], "notice-inferred")

    # --- Issuing officer --------------------------------------------------
    officer_name = OFFICER_NAME_RE.search(text)
    designation = OFFICER_DESIGNATION_RE.search(text)
    parts = [
        officer_name.group(1).strip() if officer_name else "",
        designation.group(1).strip() if designation else "",
    ]
    put("issuing_officer", ", ".join(p for p in parts if p), "notice")

    jurisdiction = JURISDICTION_RE.search(text)
    if jurisdiction:
        office = re.sub(r"\s*\n\s*", "", jurisdiction.group(1))
        office = re.sub(r"\s*,\s*", ", ", office).strip(" ,")
        put("jurisdiction_office", office, "notice")
    else:
        circle = CIRCLE_RE.search(text)
        if circle:
            put("jurisdiction_office", circle.group(1).strip(" ,"), "notice")

    return {"fields": fields, "sources": sources}


def extract_defects(text: str, pack) -> List[Dict[str, Any]]:
    """
    Decompose a notice into the limbs it will actually be decided in.

    Each defect gets its own head-wise amount read straight off the department's
    own annexure, its own sections, and the evidence list for its type. Where a
    figure cannot be read with confidence the defect is flagged rather than
    filled — a reviewer who can see an empty amount will supply it; one who
    cannot see a wrong amount will file it.
    """
    catalogue = getattr(pack, "DEFECT_TYPES", [])
    found = defects.segment(text, catalogue)
    if not found:
        return []

    head_order = notice_tables.detect_head_order(text)

    for defect in found:
        body = defect.get("notice_extract", "")
        row = notice_tables.read_defect_amount(
            body, head_order, defect.pop("preamble", ""),
        )
        if row:
            defect["amount_by_head"] = defects.normalise_heads(row["amounts"])
            defect["amount_basis"] = row.get("basis")
            defect["amount_label"] = row.get("label")
        else:
            defect["amount_unread"] = True

        # Sections stated inside the limb beat the catalogue's defaults, which
        # are only a starting point.
        cited = find_sections(body)
        if cited:
            defect["sections"] = _merge_preserving_order(defect["sections"], cited)
        cited_rules = find_rules(body)
        if cited_rules:
            defect["rules"] = _merge_preserving_order(defect["rules"], cited_rules)

    return found


def _merge_preserving_order(primary: List[str], extra: List[str]) -> List[str]:
    merged = list(primary)
    for item in extra:
        if item not in merged:
            merged.append(item)
    return merged


# ---------------------------------------------------------------------------
# Model-assisted extraction — only the two fields regex cannot do
# ---------------------------------------------------------------------------


def _build_reading_prompt(text: str, pack, notice_type: Optional[str]) -> str:
    notice = pack.NOTICE_TYPES.get(notice_type) if notice_type else None
    context = (
        f"The document appears to be a {notice.code} — {notice.name}, issued "
        f"under {notice.statute}.\n\n" if notice else ""
    )
    return f"""\
Read the {pack.SHORT_NAME} notice below and report only what it says. You are
transcribing, not advising: do not analyse the merits, do not suggest a reply,
and do not add anything the notice does not contain.

{context}NOTICE:
\"\"\"
{text[:MAX_MODEL_CHARS]}
\"\"\"

Return a SINGLE JSON object and nothing else:

{{
  "issues": "The discrepancies or allegations the notice raises, one per line, numbered. Use the notice's own framing and its own figures. If it annexes a table of differences, describe what the table alleges rather than reproducing it.",
  "facts": "Two to four sentences on what the notice states about the taxpayer and the period: nature of business if mentioned, what the officer says was found, and any prior correspondence referred to. Facts only, from the notice.",
  "officer": "Designation and office of the issuing officer, if stated, else empty",
  "confidence": "high" | "medium" | "low"
}}

Set confidence to "low" if the text is garbled, truncated, or does not read
like a tax notice. An honest "low" is useful; a confident misreading is not."""


async def extract_fields_assisted(
    text: str,
    pack,
    tier: Dict[str, Any],
    notice_type: Optional[str] = None,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], List[str]]:
    """
    Read the issues and facts out of the notice.

    On the anonymising tier the notice text is scrubbed before it is sent, so
    an uploaded notice is no less private than a typed one.
    """
    warnings: List[str] = []
    if not text.strip():
        return {}, None, ["No text to read."]

    outgoing = text
    if tier.get("anonymise"):
        # The entity name must be found before scrubbing, or the sanitiser has
        # nothing to match on and the company name goes out in clear.
        outgoing = sanitizer.scrub_text(text, {}, client_name=find_entity_name(text))
        leaks = sanitizer.audit_leaks(outgoing[:MAX_MODEL_CHARS])
        if leaks:
            return {}, None, [
                "Identifiers could not be fully removed from this notice, so "
                f"it was not sent for reading ({', '.join(leaks)}). Enter the "
                "issues and facts manually, or use the Pro tier."
            ]

    model = tier.get("grounding") or tier.get("verifier") or ""
    if not model:
        return {}, None, ["No model configured for reading notices."]

    result = await query_model(
        model,
        [{"role": "user", "content": _build_reading_prompt(outgoing, pack, notice_type)}],
        effort=config.role_effort("briefing"),
        max_tokens=config.role_max_tokens("briefing"),
        zdr=config.ENFORCE_ZDR and not tier.get("anonymise"),
    )

    if not result.get("ok"):
        return {}, None, [
            f"The notice could not be read automatically ({result.get('error')}). "
            "Enter the issues and facts manually."
        ]

    parsed = _parse_json(result.get("content", ""))
    if parsed is None:
        return {}, result.get("usage"), [
            "The notice was read but the result could not be interpreted. "
            "Enter the issues and facts manually."
        ]

    if parsed.get("confidence") == "low":
        warnings.append(
            "The notice was difficult to read — check the issues and facts "
            "carefully before running the panel."
        )

    fields = {}
    for key in ("issues", "facts"):
        value = (parsed.get(key) or "").strip()
        if value:
            fields[key] = value
    if parsed.get("officer"):
        fields["issuing_officer"] = parsed["officer"].strip()

    return fields, result.get("usage"), warnings


def _parse_json(text: str) -> Optional[Dict[str, Any]]:
    import json
    for candidate in _json_candidates(text):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


def _json_candidates(text: str):
    if not text:
        return
    yield text
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        yield fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        yield text[start:end + 1]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def read_notice(
    filename: str,
    content: bytes,
    pack,
    tier: Dict[str, Any],
    use_model: bool = True,
) -> Dict[str, Any]:
    """Single-document convenience wrapper over `read_notice_set`."""
    return await read_notice_set([(filename, content)], pack, tier, use_model)


async def read_notice_set(
    documents: List[Tuple[str, bytes]],
    pack,
    tier: Dict[str, Any],
    use_model: bool = True,
) -> Dict[str, Any]:
    """
    Turn one or more uploaded documents into a proposed matter.

    A scrutiny notice does not arrive as one file. The portal issues a one-page
    form carrying the reference number, the provision, the reply date and the
    officer's name, and attaches a separate document — often twenty pages —
    carrying the actual defects and their annexures. Neither is sufficient
    alone, and asking a partner to upload them one at a time and reconcile the
    result by hand defeats the point of the upload.

    Documents are read in order and the FIRST value found for a field wins, so
    a portal form uploaded alongside its attachment supplies the identifiers
    while the attachment supplies the defects.

    Nothing here is authoritative. Everything is a proposal the user reviews
    before the panel runs — a wrong tax period silently accepted is worse than
    an empty one.
    """
    warnings: List[str] = []
    fields: Dict[str, Any] = {}
    sources: Dict[str, str] = {}
    read_documents: List[Dict[str, Any]] = []
    combined: List[str] = []
    found_defects: List[Dict[str, Any]] = []
    usage = None

    for filename, content in documents:
        text, file_warnings = extract_text(filename, content)
        warnings.extend(f"{filename}: {w}" for w in file_warnings)
        combined.append(text)

        local = extract_fields_local(text, pack)
        for key, value in local["fields"].items():
            if key not in fields:
                fields[key] = value
                sources[key] = local["sources"].get(key, "notice")

        # The document with the most defects is the attachment; a portal form
        # or a covering letter contributes none and must not displace it.
        document_defects = extract_defects(text, pack)
        if len(document_defects) > len(found_defects):
            found_defects = document_defects

        read_documents.append({
            "filename": filename,
            "text_length": len(text),
            "defects_found": len(document_defects),
        })

    text = "\n\n".join(t for t in combined if t)

    if use_model and len(text) >= MIN_USEFUL_TEXT:
        assisted, usage, model_warnings = await extract_fields_assisted(
            text, pack, tier, fields.get("notice_type")
        )
        for key, value in assisted.items():
            fields[key] = value
            sources[key] = "read"
        warnings.extend(model_warnings)

    if found_defects:
        fields["defects"] = found_defects
        sources["defects"] = "notice"
        summary = defects.triage(found_defects)
        fields["amount_disputed"] = summary["total_amount"]
        sources["amount_disputed"] = "defects"

        unread = [d["heading"] for d in found_defects if d.get("amount_unread")]
        if unread:
            warnings.append(
                "The amount could not be read for "
                f"{len(unread)} of {len(found_defects)} defects "
                f"({'; '.join(unread[:4])}"
                f"{'…' if len(unread) > 4 else ''}). Enter these from the "
                "notice annexure before running the panel."
            )
    else:
        warnings.append(
            "No defect headings were found, so this notice could not be broken "
            "into limbs. Add them by hand — a reply that answers a multi-limb "
            "notice as one issue concedes ground it need not concede."
        )

    missing = [f for f in ("notice_type", "state", "tax_period", "facts")
               if not fields.get(f)]
    if missing:
        warnings.append(
            "Could not determine: " + ", ".join(missing) +
            ". Complete these before running the panel."
        )

    return {
        "fields": fields,
        "sources": sources,
        "warnings": warnings,
        "documents": read_documents,
        "text_length": len(text),
        "usage": usage,
        # The extracted text is returned so the user can see what was read and
        # copy from it. The uploaded files themselves are never persisted.
        "text": text[:MAX_MODEL_CHARS],
    }
