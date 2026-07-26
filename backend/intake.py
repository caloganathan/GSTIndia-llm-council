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
are, and a summary of the facts. On the free tier even that text is
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

from . import config, sanitizer
from .openrouter import query_model

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
SUPPORTED = (".pdf", ".docx", ".txt")

# Text below this length almost certainly means a scanned page with no text
# layer rather than a genuinely short notice.
MIN_USEFUL_TEXT = 200

# How much of the notice reaches the model. Notices run long with annexures;
# the operative part is at the front, and sending the rest is waste.
MAX_MODEL_CHARS = 12000


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

REFERENCE_RE = re.compile(
    r"(?:reference|ref|notice)\s*(?:no|number)?\s*[.:\-]?\s*"
    r"([A-Z]{2}[A-Z0-9/\-]{6,30})",
    re.IGNORECASE,
)

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

SECTION_RE = re.compile(
    r"(?:under\s+)?(?:section|sec\.?|u/s)\s*(\d{1,3}[A-Z]?)", re.IGNORECASE
)

# Entity name, identified by its statutory suffix.
#
# This is extracted locally for two reasons, and the second matters more: it
# fills the client name field, AND it gives the sanitiser something to scrub.
# Without it the free tier strips the GSTIN and PAN but leaves the company
# name standing in the notice text — which is exactly the leak the test suite
# caught.
ENTITY_RE = re.compile(
    r"\b((?:[A-Z][\w&.'\-]*\s+){1,6}"
    r"(?:Private\s+Limited|Pvt\.?\s*Ltd\.?|Public\s+Limited|Limited|Ltd\.?"
    r"|LLP|Limited\s+Liability\s+Partnership|&\s*Co\.?|and\s+Company"
    r"|&\s*Sons|Enterprises|Industries|Associates))\b"
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
        # Tolerate ASMT-10, ASMT 10, ASMT10
        pattern = code.replace("-", r"[\s\-]?")
        if re.search(rf"\b{pattern}\b", upper):
            return code
    return None


def find_entity_name(text: str) -> Optional[str]:
    """
    The taxpayer's name, found by its statutory suffix.

    Longest match wins: "Acme Steel Industries Private Limited" should not be
    truncated to "Acme Steel Industries".
    """
    candidates = [m.group(1).strip() for m in ENTITY_RE.finditer(text)]
    if not candidates:
        return None
    # Prefer the longest, then the earliest — notices name the taxpayer before
    # they name anyone else.
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


def extract_fields_local(text: str, pack) -> Dict[str, Any]:
    """
    Everything derivable without a model.

    Each field carries where it came from, so the UI can show the user what
    was read off the notice versus what a model proposed.
    """
    fields: Dict[str, Any] = {}
    sources: Dict[str, str] = {}

    gstin_match = GSTIN_RE.search(text)
    if gstin_match:
        fields["gstin"] = gstin_match.group(0)
        sources["gstin"] = "notice"
        state = GSTIN_STATE_CODES.get(gstin_match.group(1))
        if state:
            fields["state"] = state
            sources["state"] = "gstin"

    entity = find_entity_name(text)
    if entity:
        fields["client_name"] = entity
        sources["client_name"] = "notice"

    notice_type = find_notice_type(text, pack)
    if notice_type:
        fields["notice_type"] = notice_type
        sources["notice_type"] = "notice"

    reference = REFERENCE_RE.search(text)
    if reference:
        fields["notice_reference"] = reference.group(1).strip()
        sources["notice_reference"] = "notice"

    period = find_tax_period(text)
    if period:
        fields["tax_period"] = period
        sources["tax_period"] = "notice"

    section = SECTION_RE.search(text)
    if section:
        fields["section_invoked"] = section.group(1)
        sources["section_invoked"] = "notice"

    dates = find_dates(text)
    if dates:
        # The earliest date in a notice is almost always its own date; the
        # latest is almost always the reply deadline. Both are proposals for
        # the user to confirm, never assumptions.
        fields["notice_date"] = dates[0]
        sources["notice_date"] = "notice"
        if len(dates) > 1:
            fields["due_date"] = dates[-1]
            sources["due_date"] = "notice"

    amounts = find_amounts(text)
    if amounts:
        # The largest figure is usually the demand; smaller ones are usually
        # its tax/interest/penalty components.
        fields["amount_disputed"] = max(amounts)
        sources["amount_disputed"] = "notice"

    return {"fields": fields, "sources": sources}


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
    """
    Turn an uploaded notice into proposed intake fields.

    Nothing here is authoritative. Everything is a proposal the user reviews
    before the panel runs — a wrong tax period silently accepted is worse
    than an empty one.
    """
    text, warnings = extract_text(filename, content)

    local = extract_fields_local(text, pack)
    fields = dict(local["fields"])
    sources = dict(local["sources"])
    usage = None

    if use_model and len(text) >= MIN_USEFUL_TEXT:
        assisted, usage, model_warnings = await extract_fields_assisted(
            text, pack, tier, fields.get("notice_type")
        )
        for key, value in assisted.items():
            fields[key] = value
            sources[key] = "read"
        warnings.extend(model_warnings)

    missing = [f for f in ("notice_type", "state", "tax_period", "issues", "facts")
               if not fields.get(f)]
    if missing:
        warnings.append(
            "Could not determine: " + ", ".join(missing.copy()) +
            ". Complete these before running the panel."
        )

    return {
        "fields": fields,
        "sources": sources,
        "warnings": warnings,
        "text_length": len(text),
        "usage": usage,
        # The extracted text is returned so the user can see what was read and
        # copy from it. The uploaded file itself is never persisted.
        "text": text[:MAX_MODEL_CHARS],
    }
