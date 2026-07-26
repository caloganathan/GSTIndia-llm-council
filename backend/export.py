"""Reply pack export.

The deliverable is a professional work product: a submission drafted for the
engagement partner to settle and sign, with the analysis and the schedule of
authorities that support it. It is formatted the way a tax practice in India
formats a file that goes to a partner and then to the department.

Typography is deliberately plain — Arial 11pt throughout, black on white,
bold for headings and nothing else. No colour, no shading, no decoration. A
document that looks designed looks amateur; a document that looks like every
other well-run file on the partner's desk gets read.
"""

import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from . import config
from .verification import ACTIONABLE, NOT_FOUND, SUPERSEDED, UNVERIFIED, VERIFIED

BLACK = RGBColor(0x00, 0x00, 0x00)
GREY = RGBColor(0x40, 0x40, 0x40)

BODY_FONT = "Arial"
BODY_SIZE = Pt(11)

# Plain-language equivalents. The reviewer needs to know what to check; the
# internal vocabulary of the verification layer is not what they need to read.
STATUS_LABEL = {
    VERIFIED: "Verified",
    SUPERSEDED: "Superseded",
    UNVERIFIED: "To be confirmed",
    NOT_FOUND: "Not traced",
}

STRENGTH_LABEL = {
    "strong": "Strong",
    "defensible": "Defensible",
    "weak": "Weak",
}

CONFIDENCE_LABEL = {
    "strong": "Strong",
    "defensible": "Defensible",
    "weak": "Weak",
    "insufficient_information": "Further information required",
}


# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------


def _configure_styles(doc: Document):
    """Arial 11pt, black, throughout. Headings differ only by weight."""
    normal = doc.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = BODY_SIZE
    normal.font.color.rgb = BLACK
    # East Asian font mapping, or Word substitutes on some systems
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.15

    for name in ("Heading 1", "Heading 2", "Heading 3", "Title"):
        try:
            style = doc.styles[name]
        except KeyError:
            continue
        style.font.name = BODY_FONT
        style.font.color.rgb = BLACK
        style.font.bold = True
        style.font.italic = False
        style.font.size = Pt(13) if name in ("Heading 1", "Title") else Pt(11)
        style.paragraph_format.space_before = Pt(12)
        style.paragraph_format.space_after = Pt(4)

    for name in ("List Bullet", "List Number"):
        try:
            style = doc.styles[name]
        except KeyError:
            continue
        style.font.name = BODY_FONT
        style.font.size = BODY_SIZE
        style.font.color.rgb = BLACK


def _para(doc: Document, text: str = "", bold: bool = False,
          italic: bool = False, size: Pt = None, align=None, space_after=None):
    paragraph = doc.add_paragraph()
    if align is not None:
        paragraph.alignment = align
    if space_after is not None:
        paragraph.paragraph_format.space_after = space_after
    if text:
        run = paragraph.add_run(text)
        run.font.name = BODY_FONT
        run.font.size = size or BODY_SIZE
        run.font.color.rgb = BLACK
        run.bold = bold
        run.italic = italic
    return paragraph


def _heading(doc: Document, text: str, level: int = 1):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(14 if level == 1 else 10)
    paragraph.paragraph_format.space_after = Pt(4)
    paragraph.paragraph_format.keep_with_next = True
    run = paragraph.add_run(text.upper() if level == 1 else text)
    run.font.name = BODY_FONT
    run.font.size = Pt(11)
    run.font.color.rgb = BLACK
    run.bold = True
    return paragraph


def _rule(doc: Document):
    """A thin horizontal rule — the only ornament this document uses."""
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(2)
    paragraph.paragraph_format.space_after = Pt(8)
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:color"), "000000")
    borders.append(bottom)
    paragraph._p.get_or_add_pPr().append(borders)
    return paragraph


def _plain_table(doc: Document, columns: int):
    table = doc.add_table(rows=0, cols=columns)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    return table


def _set_cell(cell, text: str, bold: bool = False):
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.paragraph_format.space_after = Pt(2)
    run = paragraph.add_run(str(text) if text not in (None, "") else "—")
    run.font.name = BODY_FONT
    run.font.size = Pt(10)
    run.font.color.rgb = BLACK
    run.bold = bold


def _particulars(doc: Document, rows):
    """Two-column particulars block, as a file cover sheet is set out."""
    rows = [(k, v) for k, v in rows if v not in (None, "", [])]
    if not rows:
        return
    table = _plain_table(doc, 2)
    table.columns[0].width = Inches(2.1)
    table.columns[1].width = Inches(4.3)
    for key, value in rows:
        cells = table.add_row().cells
        _set_cell(cells[0], key, bold=True)
        _set_cell(cells[1], value)
    _para(doc, space_after=Pt(4))


def _numbered_body(doc: Document, text: str):
    """
    Render pre-numbered draft text.

    The chairman returns paragraphs already numbered, which is how a reply is
    actually written. Indent continuation lines so numbering stays legible.
    """
    for block in str(text or "").split("\n"):
        stripped = block.strip()
        if not stripped:
            continue
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(8)
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        if stripped[:1].isdigit() and ("." in stripped[:5] or ")" in stripped[:5]):
            paragraph.paragraph_format.left_indent = Inches(0.35)
            paragraph.paragraph_format.first_line_indent = Inches(-0.35)
        run = paragraph.add_run(stripped)
        run.font.name = BODY_FONT
        run.font.size = BODY_SIZE
        run.font.color.rgb = BLACK


def _page_footer(doc: Document, reference: str):
    """Matter reference and page number, as any professional file carries."""
    footer = doc.sections[0].footer
    paragraph = footer.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(f"{reference}    |    Page ")
    run.font.name = BODY_FONT
    run.font.size = Pt(8)
    run.font.color.rgb = GREY

    # PAGE field
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    paragraph._p.append(fld)


# ---------------------------------------------------------------------------
# The pack
# ---------------------------------------------------------------------------


def build_reply_pack(matter: Dict[str, Any]) -> bytes:
    """Render a completed matter as a reply pack for partner review."""
    intake = matter.get("intake", {})
    result = matter.get("result") or {}
    determination = result.get("determination") or {}
    verification = result.get("verification") or {}
    metadata = matter.get("metadata") or {}

    doc = Document()
    _configure_styles(doc)

    section = doc.sections[0]
    section.top_margin = Inches(0.9)
    section.bottom_margin = Inches(0.9)
    section.left_margin = Inches(1.0)
    section.right_margin = Inches(1.0)

    reference = f"Ref: {str(matter.get('id', ''))[:8].upper()}"
    _page_footer(doc, reference)

    # ---- Cover -----------------------------------------------------------
    if config.FIRM_NAME:
        _para(doc, config.FIRM_NAME, bold=True, size=Pt(13),
              align=WD_ALIGN_PARAGRAPH.CENTER, space_after=Pt(0))
        _para(doc, config.FIRM_SUBTITLE, size=Pt(10),
              align=WD_ALIGN_PARAGRAPH.CENTER, space_after=Pt(2))
        _rule(doc)

    notice_type = intake.get("notice_type", "")
    _para(doc, "REPLY TO NOTICE — ANALYSIS AND DRAFT SUBMISSION", bold=True,
          size=Pt(13), align=WD_ALIGN_PARAGRAPH.CENTER, space_after=Pt(2))
    _para(doc, f"Notice in Form {notice_type}" if notice_type else "",
          size=Pt(10), align=WD_ALIGN_PARAGRAPH.CENTER)
    _rule(doc)

    _particulars(doc, [
        ("Client", intake.get("client_name")),
        ("GSTIN", intake.get("gstin")),
        ("Notice", notice_type),
        ("Provision invoked", intake.get("section_invoked")),
        ("Jurisdiction", intake.get("state")),
        ("Tax period", intake.get("tax_period")),
        ("Amount in dispute", _rupees(intake.get("amount_disputed"))),
        ("Date of notice", _date(intake.get("notice_date"))),
        ("Reply due", _date(intake.get("due_date"))),
        ("Prepared on", datetime.now(timezone.utc).strftime("%d %B %Y")),
        ("Matter reference", str(matter.get("id", ""))[:8].upper()),
    ])

    _para(doc, config.EXPORT_REVIEW_NOTE, italic=True, size=Pt(9))

    # ---- 1. Position recommended ----------------------------------------
    _heading(doc, "1.  Position Recommended", 1)
    _para(doc, determination.get("recommended_position") or
          "No recommendation was settled on the material available.")

    rows = []
    if determination.get("confidence"):
        rows.append(("Assessment of position",
                     CONFIDENCE_LABEL.get(determination["confidence"],
                                          determination["confidence"].title())))
    if determination.get("lead_argument"):
        rows.append(("Submission taken first", determination["lead_argument"]))
    _particulars(doc, rows)

    # ---- 2. Issues and position ------------------------------------------
    issues = [i for i in (determination.get("issues") or []) if isinstance(i, dict)]
    if issues:
        _heading(doc, "2.  Issues Raised and Position Taken", 1)
        for index, issue in enumerate(issues, start=1):
            _heading(doc, f"2.{index}  {issue.get('issue', 'Issue')}", 2)
            _particulars(doc, [
                ("Contention in the notice", issue.get("department_view")),
                ("Position taken", issue.get("our_position")),
                ("Relied upon", issue.get("authority")),
                ("Assessment", STRENGTH_LABEL.get(
                    (issue.get("strength") or "").lower(), issue.get("strength"))),
            ])

    # ---- 3. Draft reply ---------------------------------------------------
    if determination.get("draft_reply"):
        doc.add_page_break()
        _heading(doc, "3.  Draft Reply", 1)
        _para(doc,
              "To be settled by the engagement partner and issued on the firm's "
              "letterhead over signature.", italic=True, size=Pt(9))
        _rule(doc)
        _numbered_body(doc, determination["draft_reply"])

    # ---- 4. Schedule of authorities --------------------------------------
    authorities = verification.get("authorities") or []
    _heading(doc, "4.  Schedule of Authorities", 1)

    if authorities:
        summary = verification.get("summary") or {}
        outstanding = sum(
            summary.get(k, 0) or 0
            for k in ("superseded", "unverified", "not_found")
        )
        if outstanding:
            _para(doc,
                  f"{outstanding} of {summary.get('total', len(authorities))} "
                  "authorities require confirmation before filing. These are "
                  "identified below.", bold=True)

        table = _plain_table(doc, 4)
        table.columns[0].width = Inches(2.2)
        table.columns[1].width = Inches(1.9)
        table.columns[2].width = Inches(1.1)
        table.columns[3].width = Inches(1.3)
        header = table.add_row().cells
        for cell, label in zip(header, ("Authority", "Cited for", "Status", "Remarks")):
            _set_cell(cell, label, bold=True)

        for authority in authorities:
            cells = table.add_row().cells
            _set_cell(cells[0], authority.get("citation", ""))
            _set_cell(cells[1], authority.get("proposition", ""))
            status = authority.get("status", UNVERIFIED)
            _set_cell(cells[2], STATUS_LABEL.get(status, "To be confirmed"),
                      bold=status != VERIFIED)
            remark = authority.get("note", "")
            if authority.get("correction"):
                remark = f"{remark} Read as: {authority['correction']}"
            _set_cell(cells[3], remark)
        _para(doc, space_after=Pt(4))
        _para(doc,
              "'Verified' indicates the authority was traced, supports the "
              "proposition for which it is cited, and appears to remain good "
              "law. 'Superseded' indicates it has been amended, withdrawn, "
              "overruled or stayed and must not be relied on as cited. 'To be "
              "confirmed' and 'Not traced' are to be settled against the "
              "reported text before filing.",
              italic=True, size=Pt(9))
    else:
        _para(doc,
              "No authority has been cited in support of the position taken. "
              "This is to be considered before the submission is settled.")

    # ---- 5. Points for reviewer attention --------------------------------
    risk_flags = determination.get("risk_flags") or []
    open_questions = determination.get("open_questions") or []
    unresolved = [a for a in authorities if a.get("status") in ACTIONABLE]

    if risk_flags or open_questions or unresolved:
        _heading(doc, "5.  Points for Reviewer Attention", 1)
        counter = 0
        for flag in risk_flags:
            counter += 1
            _para(doc, f"{counter}.  {flag}")
        for authority in unresolved:
            counter += 1
            status = authority.get("status")
            label = STATUS_LABEL.get(status, "to be confirmed")
            detail = f" {authority.get('correction')}" if authority.get("correction") else ""
            action = ("must not be relied on as cited"
                      if status == SUPERSEDED else "to be confirmed before filing")
            _para(doc, f"{counter}.  Authority {action}: "
                       f"{authority.get('citation', '')} ({label}).{detail}")
        for question in open_questions:
            counter += 1
            _para(doc, f"{counter}.  {question}")

    # ---- 6. Documents to be placed on record -----------------------------
    documents = determination.get("documents_to_collect") or []
    if documents:
        _heading(doc, "6.  Documents to be Placed on Record", 1)
        for document in documents:
            _para(doc, f"•  {document}")

    # ---- 7. Note for the file --------------------------------------------
    if determination.get("working_note") or determination.get("panel_disagreements"):
        doc.add_page_break()
        _heading(doc, "7.  Note for the File", 1)
        _para(doc,
              "Record of the basis on which the position was settled, for the "
              "purposes of review and of any subsequent proceedings.",
              italic=True, size=Pt(9))

        if determination.get("working_note"):
            _numbered_body(doc, determination["working_note"])

        alternatives = [
            e for e in (determination.get("panel_disagreements") or [])
            if isinstance(e, dict)
        ]
        if alternatives:
            _heading(doc, "Alternative positions considered and not adopted", 2)
            for entry in alternatives:
                _particulars(doc, [
                    ("Question", entry.get("question")),
                    ("Positions considered", entry.get("positions")),
                    ("Basis on which settled", entry.get("resolution")),
                ])

    # ---- 8. Summary for the board ----------------------------------------
    if determination.get("board_summary"):
        _heading(doc, "8.  Summary for the Board", 1)
        _para(doc, determination["board_summary"])

    # ---- Internal annexure (off by default) ------------------------------
    if config.EXPORT_PROVENANCE:
        doc.add_page_break()
        _heading(doc, "Annexure — Internal Record", 1)
        _para(doc, "For the firm's file. Not for circulation.",
              italic=True, size=Pt(9))
        models = metadata.get("models") or {}
        _particulars(doc, [(k.title(), v) for k, v in models.items()] + [
            ("Client particulars withheld in preparation",
             "Yes" if metadata.get("anonymised") else "No"),
            ("Matter reference", matter.get("id")),
        ])

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _rupees(value) -> Optional[str]:
    if value in (None, ""):
        return None
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    # Indian digit grouping
    whole = int(round(amount))
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
    return f"Rs. {text}"


def _date(value) -> Optional[str]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).strftime("%d %B %Y")
    except ValueError:
        return str(value)


def suggested_filename(matter: Dict[str, Any]) -> str:
    intake = matter.get("intake", {})
    parts = [
        (intake.get("client_name") or "Matter").replace(" ", "_")[:40],
        (intake.get("notice_type") or "Notice").replace(" ", ""),
        (intake.get("tax_period") or "").replace(" ", "").replace("/", "-")[:20],
        "Reply_Pack",
    ]
    return "_".join(p for p in parts if p) + ".docx"
