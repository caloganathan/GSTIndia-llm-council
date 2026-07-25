"""DOCX export of the notice reply pack.

What leaves this system is never "the submission". It is a draft plus the
evidence a signing partner needs to decide whether to sign it: the position,
the authorities with their verification status, the risks, and the working
note recording how the position was reached.

The disclaimer is not optional and is not configurable away by the UI.
"""

import io
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

from . import config
from .verification import NOT_FOUND, UNVERIFIED, VERIFIED

STATUS_COLOUR = {
    VERIFIED: RGBColor(0x1B, 0x5E, 0x3A),
    UNVERIFIED: RGBColor(0xB4, 0x53, 0x09),
    NOT_FOUND: RGBColor(0x99, 0x1B, 0x1B),
}

CONFIDENCE_LABEL = {
    "strong": "Strong",
    "defensible": "Defensible",
    "weak": "Weak",
    "insufficient_information": "Insufficient information",
}


def _style_document(doc: Document):
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    normal.paragraph_format.space_after = Pt(6)


def _heading(doc: Document, text: str, level: int = 1):
    heading = doc.add_heading(text, level=level)
    for run in heading.runs:
        run.font.color.rgb = RGBColor(0x1E, 0x3A, 0x5F)
    return heading


def _kv_table(doc: Document, rows):
    rows = [(k, v) for k, v in rows if v not in (None, "", [])]
    if not rows:
        return
    table = doc.add_table(rows=0, cols=2)
    table.style = "Light List Accent 1"
    for key, value in rows:
        cells = table.add_row().cells
        cells[0].text = str(key)
        cells[1].text = str(value)
        for paragraph in cells[0].paragraphs:
            for run in paragraph.runs:
                run.bold = True
    doc.add_paragraph()


def _disclaimer(doc: Document, watermark: Optional[str] = None):
    if watermark:
        para = doc.add_paragraph()
        run = para.add_run(watermark)
        run.bold = True
        run.font.size = Pt(12)
        run.font.color.rgb = RGBColor(0xB4, 0x53, 0x09)
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    para = doc.add_paragraph()
    run = para.add_run(config.EXPORT_DISCLAIMER)
    run.italic = True
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x5C, 0x63, 0x70)


def build_reply_pack(matter: Dict[str, Any]) -> bytes:
    """Render a completed matter into a DOCX reply pack."""
    intake = matter.get("intake", {})
    result = matter.get("result") or {}
    determination = result.get("determination") or {}
    verification = result.get("verification") or {}
    metadata = matter.get("metadata") or {}

    doc = Document()
    _style_document(doc)

    # ---- Cover ----------------------------------------------------------
    title = doc.add_heading("Notice Reply Pack", level=0)
    for run in title.runs:
        run.font.color.rgb = RGBColor(0x1E, 0x3A, 0x5F)

    _disclaimer(doc, metadata.get("watermark"))
    doc.add_paragraph()

    _kv_table(doc, [
        ("Client", intake.get("client_name")),
        ("GSTIN", intake.get("gstin")),
        ("Notice type", intake.get("notice_type")),
        ("Section invoked", intake.get("section_invoked")),
        ("State / jurisdiction", intake.get("state")),
        ("Tax period", intake.get("tax_period")),
        ("Amount in dispute (INR)", intake.get("amount_disputed")),
        ("Date of notice", intake.get("notice_date")),
        ("Reply due date", intake.get("due_date")),
        ("Panel tier", metadata.get("tier_label")),
        ("Prepared", datetime.now(timezone.utc).strftime("%d %B %Y")),
    ])

    # ---- Determination --------------------------------------------------
    _heading(doc, "1. Recommended Position", 1)
    doc.add_paragraph(determination.get("recommended_position", "Not available."))

    confidence = determination.get("confidence", "")
    if confidence:
        para = doc.add_paragraph()
        para.add_run("Confidence: ").bold = True
        para.add_run(CONFIDENCE_LABEL.get(confidence, confidence.title()))

    if determination.get("lead_argument"):
        para = doc.add_paragraph()
        para.add_run("Lead argument: ").bold = True
        para.add_run(determination["lead_argument"])

    # ---- Issue analysis -------------------------------------------------
    issues = determination.get("issues") or []
    if issues:
        _heading(doc, "2. Issue-wise Analysis", 1)
        for i, issue in enumerate(issues, start=1):
            if not isinstance(issue, dict):
                continue
            _heading(doc, f"2.{i}  {issue.get('issue', 'Issue')}", 2)
            _kv_table(doc, [
                ("Department's contention", issue.get("department_view")),
                ("Our position", issue.get("our_position")),
                ("Authority", issue.get("authority")),
                ("Strength", (issue.get("strength") or "").title()),
            ])

    # ---- Draft reply ----------------------------------------------------
    if determination.get("draft_reply"):
        _heading(doc, "3. Draft Reply", 1)
        for block in str(determination["draft_reply"]).split("\n"):
            doc.add_paragraph(block) if block.strip() else doc.add_paragraph()

    # ---- Authorities and verification -----------------------------------
    authorities = verification.get("authorities") or []
    _heading(doc, "4. Authorities and Verification Status", 1)

    if authorities:
        summary = verification.get("summary") or {}
        para = doc.add_paragraph()
        para.add_run(
            f"{summary.get('verified', 0)} verified · "
            f"{summary.get('unverified', 0)} unverified · "
            f"{summary.get('not_found', 0)} not found "
            f"(of {summary.get('total', len(authorities))})"
        ).bold = True

        table = doc.add_table(rows=1, cols=4)
        table.style = "Light Grid Accent 1"
        headers = ["Citation", "Cited for", "Status", "Note"]
        for cell, text in zip(table.rows[0].cells, headers):
            cell.text = text
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.bold = True

        for authority in authorities:
            cells = table.add_row().cells
            cells[0].text = authority.get("citation", "")
            cells[1].text = authority.get("proposition", "") or "—"
            status = authority.get("status", UNVERIFIED)
            cells[2].text = status
            for paragraph in cells[2].paragraphs:
                for run in paragraph.runs:
                    run.bold = True
                    run.font.color.rgb = STATUS_COLOUR.get(status, STATUS_COLOUR[UNVERIFIED])
            note = authority.get("note", "")
            if authority.get("correction"):
                note = f"{note} Suggested correction: {authority['correction']}"
            cells[3].text = note
        doc.add_paragraph()

        if verification.get("note"):
            para = doc.add_paragraph()
            run = para.add_run(verification["note"])
            run.italic = True
    else:
        doc.add_paragraph(
            "No authorities were extracted from the determination. For a tax "
            "reply this is itself a matter for review."
        )

    # ---- Risk -----------------------------------------------------------
    risk_flags = determination.get("risk_flags") or []
    if risk_flags:
        _heading(doc, "5. Risk Flags for the Signing Partner", 1)
        for flag in risk_flags:
            doc.add_paragraph(str(flag), style="List Bullet")

    documents = determination.get("documents_to_collect") or []
    if documents:
        _heading(doc, "6. Documents to be Collected", 1)
        for item in documents:
            doc.add_paragraph(str(item), style="List Bullet")

    # ---- Panel disagreements --------------------------------------------
    disagreements = determination.get("panel_disagreements") or []
    if disagreements:
        _heading(doc, "7. Panel Disagreements and Their Resolution", 1)
        for entry in disagreements:
            if not isinstance(entry, dict):
                continue
            _kv_table(doc, [
                ("Question", entry.get("question")),
                ("Positions taken", entry.get("positions")),
                ("Chairman's ruling", entry.get("resolution")),
            ])

    # ---- Working note ---------------------------------------------------
    if determination.get("working_note"):
        _heading(doc, "8. Working Note for the File", 1)
        doc.add_paragraph(
            "This note records how the firm's position was reached, for peer "
            "review and for any subsequent proceedings."
        ).runs[0].italic = True
        for block in str(determination["working_note"]).split("\n"):
            doc.add_paragraph(block) if block.strip() else doc.add_paragraph()

    if determination.get("board_summary"):
        _heading(doc, "9. Summary for the Board / Audit Committee", 1)
        doc.add_paragraph(determination["board_summary"])

    open_questions = determination.get("open_questions") or []
    if open_questions:
        _heading(doc, "10. Open Questions", 1)
        for item in open_questions:
            doc.add_paragraph(str(item), style="List Bullet")

    # ---- Provenance ------------------------------------------------------
    doc.add_page_break()
    _heading(doc, "Annexure — Panel Composition and Provenance", 1)
    models = metadata.get("models") or {}
    _kv_table(doc, [
        ("Revenue's Advocate", models.get("revenue")),
        ("Assessee's Advocate", models.get("assessee")),
        ("Procedural Counsel", models.get("procedural")),
        ("Risk and Ethics Counsel", models.get("risk")),
        ("Chairman", models.get("chairman")),
        ("Verifier", verification.get("verifier_model")),
        ("Tier", metadata.get("tier_label")),
        ("Client identifiers anonymised", "Yes" if metadata.get("anonymised") else "No"),
        ("Matter reference", matter.get("id")),
    ])
    _disclaimer(doc, metadata.get("watermark"))

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def suggested_filename(matter: Dict[str, Any]) -> str:
    intake = matter.get("intake", {})
    parts = [
        (intake.get("client_name") or "Matter").replace(" ", "_")[:40],
        intake.get("notice_type", "Notice").replace(" ", ""),
        (intake.get("tax_period") or "").replace(" ", "").replace("/", "-")[:20],
    ]
    stem = "_".join(p for p in parts if p)
    return f"{stem or 'Reply_Pack'}.docx"
