"""Anonymisation gate for the draft tier.

An endpoint that costs little may be cheap *because* the provider retains or
trains on prompts. Sending a client's PAN, GSTIN, turnover and dispute
particulars to such an endpoint is a breach of professional confidentiality
and a DPDP Act exposure. On any tier marked `anonymise` this module runs
unconditionally: identifiers never leave the machine.

(This gate was written for a free tier that has since been retired; the draft
tier replaced it and inherits the rule unchanged.)

The mapping is kept locally so the identifiers can be restored in the output
the user actually reads. The model sees "the Taxpayer"; the partner sees the
real name in the DOCX.
"""

import re
from typing import Any, Dict, Optional, Tuple

TAXPAYER_PLACEHOLDER = "the Taxpayer"

# Indian statutory identifiers
PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
GSTIN_RE = re.compile(r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]{3}\b")
TAN_RE = re.compile(r"\b[A-Z]{4}[0-9]{5}[A-Z]\b")
CIN_RE = re.compile(r"\b[LUu][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}\b")
AADHAAR_RE = re.compile(r"\b[2-9][0-9]{3}\s?[0-9]{4}\s?[0-9]{4}\b")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\-\s]?)?[6-9][0-9]{9}(?!\d)")
# Bank accounts: 9-18 consecutive digits not already caught above
BANK_RE = re.compile(r"(?<!\d)\d{9,18}(?!\d)")

# Order matters: longest / most specific identifiers first, so a GSTIN is not
# partially consumed by the PAN pattern it contains.
IDENTIFIER_RULES = [
    ("GSTIN", GSTIN_RE),
    ("CIN", CIN_RE),
    ("AADHAAR", AADHAAR_RE),
    ("TAN", TAN_RE),
    ("PAN", PAN_RE),
    ("EMAIL", EMAIL_RE),
    ("PHONE", PHONE_RE),
    ("ACCOUNT", BANK_RE),
]

# Free-text fields that get scrubbed. Structured legal fields (notice_type,
# state, section_invoked, tax_period) carry no client identity and are needed
# for the analysis to be worth anything.
SCRUBBED_FIELDS = ("issues", "facts", "documents_available")
DROPPED_FIELDS = ("client_name", "gstin", "client_ref")


def _bucket_amount(value: float) -> str:
    """Replace an exact figure with an order-of-magnitude band."""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "an undisclosed amount"

    bands = [
        (100_000, "under INR 1 lakh"),
        (1_000_000, "INR 1-10 lakh"),
        (5_000_000, "INR 10-50 lakh"),
        (10_000_000, "INR 50 lakh - 1 crore"),
        (50_000_000, "INR 1-5 crore"),
        (100_000_000, "INR 5-10 crore"),
    ]
    for ceiling, label in bands:
        if amount < ceiling:
            return label
    return "over INR 10 crore"


def scrub_text(
    text: Optional[str],
    replacements: Dict[str, str],
    client_name: Optional[str] = None,
) -> str:
    """Remove identifiers from free text, recording each substitution."""
    if not text:
        return ""

    result = text

    # Client name first: it is the identifier most likely to appear in prose.
    if client_name and len(client_name.strip()) >= 3:
        name = client_name.strip()
        pattern = re.compile(re.escape(name), re.IGNORECASE)
        if pattern.search(result):
            replacements[TAXPAYER_PLACEHOLDER] = name
            result = pattern.sub(TAXPAYER_PLACEHOLDER, result)

        # Also catch the bare first word of a longer name ("Acme" for
        # "Acme Industries Private Limited"), which prose often uses alone.
        head = name.split()[0]
        if len(head) >= 4 and head.lower() not in {"the", "shri", "smt", "messrs"}:
            head_pattern = re.compile(rf"\b{re.escape(head)}\b", re.IGNORECASE)
            result = head_pattern.sub(TAXPAYER_PLACEHOLDER, result)

    counters: Dict[str, int] = {}
    for label, pattern in IDENTIFIER_RULES:
        def _replace(match):
            counters[label] = counters.get(label, 0) + 1
            token = f"[{label}-{counters[label]}]"
            replacements[token] = match.group(0)
            return token

        result = pattern.sub(_replace, result)

    return result


def sanitize_matter(
    matter: Dict[str, Any],
    bucket_amounts: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """
    Produce a version of the matter safe to send to a retaining endpoint.

    Returns (sanitised_matter, replacements). `replacements` maps the
    placeholder back to the original value so output can be restored locally.
    """
    replacements: Dict[str, str] = {}
    clean = dict(matter)
    client_name = matter.get("client_name")

    for field in DROPPED_FIELDS:
        clean.pop(field, None)

    for field in SCRUBBED_FIELDS:
        if clean.get(field):
            clean[field] = scrub_text(clean[field], replacements, client_name)

    if bucket_amounts and clean.get("amount_disputed") not in (None, ""):
        replacements["[AMOUNT]"] = str(clean["amount_disputed"])
        clean["amount_disputed"] = _bucket_amount(clean["amount_disputed"])

    clean["_anonymised"] = True
    return clean, replacements


def restore_text(text: Optional[str], replacements: Dict[str, str]) -> str:
    """Put the real identifiers back into model output, for local display."""
    if not text:
        return ""
    result = text
    for placeholder, original in replacements.items():
        result = result.replace(placeholder, original)
    return result


def restore_structure(payload: Any, replacements: Dict[str, str]) -> Any:
    """Recursively restore identifiers across a nested result object."""
    if not replacements:
        return payload
    if isinstance(payload, str):
        return restore_text(payload, replacements)
    if isinstance(payload, list):
        return [restore_structure(item, replacements) for item in payload]
    if isinstance(payload, dict):
        return {k: restore_structure(v, replacements) for k, v in payload.items()}
    return payload


def audit_leaks(text: str) -> Dict[str, list]:
    """
    Detect identifiers surviving in text that is about to leave the machine.

    Used as a belt-and-braces assertion before any free-tier call, and as the
    basis of the test that must never be allowed to fail.
    """
    found: Dict[str, list] = {}
    for label, pattern in IDENTIFIER_RULES:
        matches = pattern.findall(text or "")
        if matches:
            found[label] = matches
    return found
