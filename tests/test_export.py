"""Reply pack formatting tests.

Two things are locked in here.

Typography: Arial 11pt, black only. A document that drifts into another
typeface or picks up colour stops looking like every other file on the
partner's desk, which is exactly what it must look like.

Register: nothing in the deliverable discloses the machinery that produced it.
The pack is the firm's work product, settled and signed by a member — how it
was prepared is internal, and internal vocabulary must not leak into a client
or department-facing document.
"""

import io
import re

import pytest
from docx import Document

from backend import config, export

MATTER = {
    "id": "a1b2c3d4-1111-2222-3333-444455556666",
    "intake": {
        "client_name": "Acme Industries Private Limited",
        "gstin": "29AAAPL1234C1ZV",
        "notice_type": "ASMT-10",
        "state": "Karnataka",
        "tax_period": "FY 2019-20",
        "section_invoked": "61",
        "amount_disputed": 4520000,
        "notice_date": "2026-06-14",
        "due_date": "2026-07-30",
    },
    "metadata": {
        "tier_label": "Pro Council",
        "anonymised": False,
        "models": {"chairman": "some/model", "revenue": "another/model"},
    },
    "result": {
        "determination": {
            "recommended_position": "The notice is barred by limitation.",
            "confidence": "defensible",
            "lead_argument": "Limitation under section 73(10).",
            "issues": [{
                "issue": "Input tax credit availed in excess of GSTR-2A",
                "department_view": "Excess credit of Rs. 41,20,000",
                "our_position": "The conditions in section 16(2) stand satisfied",
                "authority": "Section 16(2)",
                "strength": "strong",
            }],
            "draft_reply": "1. This is in reference to the notice dated 14 June 2026.\n\n"
                           "2. At the outset, it is respectfully submitted that the "
                           "proceedings are barred by limitation.",
            "authorities": [{"citation": "Section 73(10)", "proposition": "Limitation",
                             "certainty": "asserted"}],
            "risk_flags": ["Penalty exposure under section 122(2)(a)."],
            "documents_to_collect": ["Supplier-wise reconciliation"],
            "panel_disagreements": [{
                "question": "Whether to concede part of the demand",
                "positions": "A partial concession was considered",
                "resolution": "Not adopted.",
            }],
            "board_summary": "Gross exposure of Rs. 45.20 lakh.",
            "working_note": "The question of limitation was taken first.",
            "open_questions": [],
        },
        "verification": {
            "checked": True,
            "summary": {"verified": 1, "unverified": 1, "not_found": 0, "total": 2},
            "authorities": [
                {"citation": "Section 73(10)", "proposition": "Limitation",
                 "status": "VERIFIED", "note": "Traced.", "correction": ""},
                {"citation": "Circular No. 183/15/2022-GST", "proposition": "2A mismatch",
                 "status": "UNVERIFIED", "note": "Not confirmed.", "correction": ""},
            ],
        },
    },
}


def _document(matter=None):
    return Document(io.BytesIO(export.build_reply_pack(matter or MATTER)))


def _runs(doc):
    for paragraph in doc.paragraphs:
        for run in paragraph.runs:
            if run.text.strip():
                yield run
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        if run.text.strip():
                            yield run


def _all_text(doc):
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    return "\n".join(parts)


class TestTypography:
    def test_arial_throughout(self):
        fonts = {r.font.name for r in _runs(_document())}
        assert fonts <= {"Arial", None}, f"non-Arial fonts present: {fonts}"

    def test_body_is_eleven_point(self):
        doc = _document()
        assert doc.styles["Normal"].font.size.pt == 11

    def test_monochrome_only(self):
        colours = {
            str(r.font.color.rgb)
            for r in _runs(_document())
            if r.font.color and r.font.color.rgb
        }
        assert colours <= {"000000"}, f"colour present in document: {colours}"

    def test_headings_are_bold_and_black(self):
        doc = _document()
        headings = [
            p for p in doc.paragraphs
            if p.runs and p.runs[0].bold and re.match(r"^\d+\.", p.text.strip())
        ]
        assert len(headings) >= 5
        for heading in headings:
            assert heading.runs[0].font.color.rgb is None or \
                   str(heading.runs[0].font.color.rgb) == "000000"

    def test_no_shading_applied(self):
        """Table shading would reintroduce grey blocks and break monochrome."""
        doc = _document()
        xml = doc.element.xml
        assert 'w:fill="' not in xml or 'w:fill="auto"' in xml or \
               xml.count('w:fill="') == xml.count('w:fill="auto"')


class TestNoMachineFingerprints:
    BANNED = [
        r"\bAI\b", r"\bLLM\b", "artificial intelligence", "automated",
        r"\bmodel\b", r"\bpanel\b", r"\bchairman\b", r"\bcounsel\b",
        r"\bcouncil\b", "advocate", "machine.generated", "deliberat",
        "openrouter", r"\bgpt\b", r"\bclaude\b", r"\bgemini\b", r"\bgrok\b",
        "deepseek", "prompt",
    ]

    def test_deliverable_carries_no_machinery(self):
        text = _all_text(_document())
        found = [p for p in self.BANNED if re.search(p, text, re.IGNORECASE)]
        assert not found, f"machine vocabulary leaked into the deliverable: {found}"

    def test_provenance_annexure_omitted_by_default(self):
        text = _all_text(_document()).lower()
        assert "some/model" not in text
        assert "internal record" not in text

    def test_provenance_annexure_can_be_enabled(self, monkeypatch):
        """Available for the firm's own file, off for the client deliverable."""
        monkeypatch.setattr(config, "EXPORT_PROVENANCE", True)
        text = _all_text(_document())
        assert "internal record" in text.lower()
        assert "some/model" in text


class TestProfessionalStructure:
    def test_expected_sections_present(self):
        text = _all_text(_document())
        for section in ("POSITION RECOMMENDED", "ISSUES RAISED", "DRAFT REPLY",
                        "SCHEDULE OF AUTHORITIES", "POINTS FOR REVIEWER ATTENTION",
                        "NOTE FOR THE FILE", "SUMMARY FOR THE BOARD"):
            assert section in text, f"missing section: {section}"

    def test_review_note_present(self):
        assert "settled and signed by the engagement partner" in _all_text(_document())

    def test_verification_status_uses_professional_labels(self):
        text = _all_text(_document())
        assert "To be confirmed" in text
        assert "Verified" in text
        # Internal enum values must not surface
        assert "UNVERIFIED" not in text
        assert "NOT_FOUND" not in text

    def test_unresolved_authority_raised_for_the_reviewer(self):
        text = _all_text(_document())
        assert "Circular No. 183/15/2022-GST" in text
        assert "Authority to be confirmed before filing" in text

    def test_firm_name_printed_when_configured(self, monkeypatch):
        monkeypatch.setattr(config, "FIRM_NAME", "JCSS & Associates LLP")
        assert "JCSS & Associates LLP" in _all_text(_document())

    def test_no_firm_heading_when_unset(self, monkeypatch):
        monkeypatch.setattr(config, "FIRM_NAME", "")
        assert "Chartered Accountants" not in _all_text(_document())


class TestIndianConventions:
    def test_rupee_digit_grouping(self):
        assert export._rupees(4520000) == "Rs. 45,20,000"
        assert export._rupees(100000) == "Rs. 1,00,000"
        assert export._rupees(999) == "Rs. 999"
        assert export._rupees(12345678) == "Rs. 1,23,45,678"

    def test_rupees_handles_bad_input(self):
        assert export._rupees(None) is None
        assert export._rupees("") is None
        assert export._rupees("a bucket range") == "a bucket range"

    def test_dates_in_long_form(self):
        assert export._date("2026-06-14") == "14 June 2026"
        assert export._date(None) is None
        assert export._date("not a date") == "not a date"

    def test_filename_is_descriptive(self):
        name = export.suggested_filename(MATTER)
        assert name.endswith("_Reply_Pack.docx")
        assert "Acme_Industries_Private_Limited" in name
        assert "ASMT-10" in name


class TestDegradedInput:
    def test_empty_determination_still_produces_a_document(self):
        matter = {**MATTER, "result": {"determination": {}, "verification": {}}}
        doc = _document(matter)
        assert "POSITION RECOMMENDED" in _all_text(doc)

    def test_missing_authorities_is_called_out(self):
        matter = {**MATTER, "result": {
            "determination": {"recommended_position": "x"},
            "verification": {"authorities": []},
        }}
        assert "No authority has been cited" in _all_text(_document(matter))
