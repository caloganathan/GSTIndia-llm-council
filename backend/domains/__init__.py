"""Domain packs supply the law-specific knowledge injected into panel prompts.

Each pack exposes the same interface so the adversarial panel engine stays
law-agnostic:

    NAME, SHORT_NAME       human labels
    NOTICE_TYPES           dict of code -> NoticeType
    STATUTORY_FRAMEWORK    prompt text: the stable statutory anchors
    PROCEDURAL_GROUNDS     prompt text: where matters are actually won
    CITATION_PATTERNS      regexes for the verification layer
    intake_schema()        fields the UI collects for this domain
"""

from . import gst

PACKS = {
    "gst": gst,
}


def get_pack(domain: str):
    """Return the domain pack for a workflow key, or raise ValueError."""
    pack = PACKS.get(domain)
    if pack is None:
        raise ValueError(
            f"Unknown domain '{domain}'. Available: {', '.join(sorted(PACKS))}"
        )
    return pack


def available_domains() -> list:
    return [
        {"key": key, "name": pack.NAME, "short_name": pack.SHORT_NAME}
        for key, pack in sorted(PACKS.items())
    ]
