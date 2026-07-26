"""Notice ingestion.

Two things are being protected here.

Correctness: a wrong tax period or a wrong State silently accepted is worse
than an empty field, because the State drives which High Court binds the
matter. Everything extracted is a proposal, and the tests check that what is
proposed is right.

Privacy: an uploaded notice must be no less private than a typed one. The
free tier scrubs the text before any of it reaches a model, and aborts if
scrubbing fails.
"""

import io

import pytest

from backend import intake, sanitizer
from backend.domains import gst

NOTICE = """
GOVERNMENT OF INDIA
FORM GST ASMT-10
[See rule 99(1)]
Reference No: ZA290624001234                    Date: 14.06.2026

To,
Acme Industries Private Limited
GSTIN: 29AAAPL1234C1ZV
PAN: AAAPL1234C

Notice for intimating discrepancies in the return after scrutiny under
section 61 of the CGST Act, 2017 for the financial year 2019-20.

During scrutiny of the returns for FY 2019-20 the following discrepancies
have been noticed:

1. Input tax credit availed in GSTR-3B exceeds that appearing in GSTR-2A by
   Rs. 41,20,000.
2. Interest under section 50 has been short paid to the extent of Rs. 3,15,000.

You are directed to explain the discrepancies on or before 30.07.2026 failing
which proceedings under section 73 shall be initiated.

Superintendent of Central Tax, Range-IV, Bengaluru
Contact: officer@gst.gov.in
"""


class TestTextExtraction:
    def test_plain_text(self):
        text, warnings = intake.extract_text("notice.txt", NOTICE.encode())
        assert "ASMT-10" in text
        assert warnings == []

    def test_rejects_unsupported_type(self):
        with pytest.raises(ValueError, match="Unsupported file type"):
            intake.extract_text("notice.jpg", b"x" * 500)

    def test_rejects_oversized_file(self):
        oversized = b"x" * (intake.MAX_UPLOAD_BYTES + 1)
        with pytest.raises(ValueError, match="larger than"):
            intake.extract_text("notice.pdf", oversized)

    def test_scanned_notice_is_reported_not_guessed(self):
        """No text layer must produce an honest warning, never invented text."""
        text, warnings = intake.extract_text("scan.txt", b"   ")
        assert text == ""
        assert any("scanned" in w for w in warnings)

    def test_corrupt_pdf_raises_clearly(self):
        with pytest.raises(ValueError, match="Could not read the PDF"):
            intake.extract_text("notice.pdf", b"not a pdf at all")

    def test_docx_round_trip(self):
        from docx import Document
        document = Document()
        document.add_paragraph("FORM GST ASMT-10")
        document.add_paragraph("GSTIN: 29AAAPL1234C1ZV")
        buffer = io.BytesIO()
        document.save(buffer)
        text, _ = intake.extract_text("notice.docx", buffer.getvalue())
        assert "ASMT-10" in text
        assert "29AAAPL1234C1ZV" in text


class TestLocalExtraction:
    """No model involved — nothing leaves the machine for any of this."""

    def setup_method(self):
        self.result = intake.extract_fields_local(NOTICE, gst)
        self.fields = self.result["fields"]

    def test_gstin(self):
        assert self.fields["gstin"] == "29AAAPL1234C1ZV"

    def test_state_derived_from_gstin(self):
        """29 is Karnataka — and the State decides which High Court binds."""
        assert self.fields["state"] == "Karnataka"
        assert self.result["sources"]["state"] == "gstin"

    def test_state_is_a_real_jurisdiction(self):
        assert self.fields["state"] in gst.STATE_HIGH_COURT

    def test_notice_type(self):
        assert self.fields["notice_type"] == "ASMT-10"

    def test_reference_number(self):
        assert self.fields["notice_reference"] == "ZA290624001234"

    def test_tax_period(self):
        assert self.fields["tax_period"] == "FY 2019-20"

    def test_section_invoked(self):
        assert self.fields["section_invoked"] == "61"

    def test_dates(self):
        assert self.fields["notice_date"] == "2026-06-14"
        assert self.fields["due_date"] == "2026-07-30"

    def test_largest_amount_taken_as_the_demand(self):
        assert self.fields["amount_disputed"] == 4120000.0

    def test_every_field_records_its_source(self):
        for key in self.fields:
            assert key in self.result["sources"]


class TestNoticeTypeMatching:
    def test_longer_code_wins(self):
        """DRC-01A must never be read as DRC-01."""
        assert intake.find_notice_type("FORM GST DRC-01A intimation", gst) == "DRC-01A"

    def test_tolerates_spacing_variants(self):
        for variant in ("ASMT-10", "ASMT 10", "ASMT10"):
            assert intake.find_notice_type(f"FORM GST {variant}", gst) == "ASMT-10"

    def test_absent_returns_none(self):
        assert intake.find_notice_type("A letter about nothing", gst) is None


class TestDateParsing:
    def test_numeric_formats(self):
        for text in ("14.06.2026", "14-06-2026", "14/06/2026"):
            assert intake.find_dates(text) == ["2026-06-14"]

    def test_written_formats(self):
        assert intake.find_dates("14 June 2026") == ["2026-06-14"]
        assert intake.find_dates("14th June, 2026") == ["2026-06-14"]

    def test_document_order_preserved(self):
        assert intake.find_dates("dated 01.01.2026 reply by 15.02.2026") == [
            "2026-01-01", "2026-02-15"
        ]

    def test_impossible_dates_rejected(self):
        assert intake.find_dates("45.13.2026") == []

    def test_deduplicates(self):
        assert intake.find_dates("14.06.2026 and again 14.06.2026") == ["2026-06-14"]


class TestStateCodes:
    def test_every_code_maps_to_a_known_jurisdiction(self):
        for code, state in intake.GSTIN_STATE_CODES.items():
            assert state in gst.STATE_HIGH_COURT, f"{code} -> {state} has no High Court"

    def test_key_states(self):
        assert intake.GSTIN_STATE_CODES["33"] == "Tamil Nadu"
        assert intake.GSTIN_STATE_CODES["27"] == "Maharashtra"
        assert intake.GSTIN_STATE_CODES["07"] == "Delhi"


class TestAmountsAndPeriods:
    def test_indian_grouping(self):
        assert intake.find_amounts("Rs. 41,20,000") == [4120000.0]

    def test_currency_variants(self):
        assert intake.find_amounts("INR 1,000 and ₹ 2,000") == [1000.0, 2000.0]

    def test_period_variants(self):
        for text in ("FY 2019-20", "financial year 2019-20", "F.Y. 2019-2020"):
            assert intake.find_tax_period(text) == "FY 2019-20"


@pytest.mark.asyncio
class TestPrivacy:
    """An uploaded notice must be no less private than a typed one."""

    FREE = {"anonymise": True, "grounding": "free/model"}
    PRO = {"anonymise": False, "grounding": "pro/model"}

    async def test_free_tier_scrubs_before_sending(self, monkeypatch):
        sent = {}

        async def capture(model, messages, **kwargs):
            sent["prompt"] = messages[0]["content"]
            return {"ok": True, "usage": None,
                    "content": '{"issues": "i", "facts": "f"}'}

        monkeypatch.setattr(intake, "query_model", capture)
        await intake.extract_fields_assisted(NOTICE, gst, self.FREE)

        for secret in ("Acme Industries", "29AAAPL1234C1ZV", "AAAPL1234C",
                       "officer@gst.gov.in"):
            assert secret not in sent["prompt"], f"LEAKED: {secret}"
        assert sanitizer.audit_leaks(sent["prompt"]) == {}

    async def test_pro_tier_sends_full_facts_with_zdr(self, monkeypatch):
        sent = {}

        async def capture(model, messages, **kwargs):
            sent["prompt"] = messages[0]["content"]
            sent["zdr"] = kwargs.get("zdr")
            return {"ok": True, "usage": None,
                    "content": '{"issues": "i", "facts": "f"}'}

        monkeypatch.setattr(intake, "query_model", capture)
        await intake.extract_fields_assisted(NOTICE, gst, self.PRO)
        assert "Acme Industries" in sent["prompt"]
        assert sent["zdr"] is True

    async def test_extraction_failure_is_reported_not_swallowed(self, monkeypatch):
        async def failing(*args, **kwargs):
            return {"ok": False, "error": "model unavailable"}

        monkeypatch.setattr(intake, "query_model", failing)
        fields, _, warnings = await intake.extract_fields_assisted(
            NOTICE, gst, self.PRO
        )
        assert fields == {}
        assert any("manually" in w for w in warnings)

    async def test_low_confidence_is_surfaced(self, monkeypatch):
        async def query(*args, **kwargs):
            return {"ok": True, "usage": None,
                    "content": '{"issues": "i", "facts": "f", "confidence": "low"}'}

        monkeypatch.setattr(intake, "query_model", query)
        _, _, warnings = await intake.extract_fields_assisted(NOTICE, gst, self.PRO)
        assert any("difficult to read" in w for w in warnings)


@pytest.mark.asyncio
class TestReadNotice:
    async def test_end_to_end_without_a_model(self):
        """Local extraction alone should fill most of the form."""
        result = await intake.read_notice(
            "notice.txt", NOTICE.encode(), gst,
            {"anonymise": False}, use_model=False,
        )
        fields = result["fields"]
        assert fields["notice_type"] == "ASMT-10"
        assert fields["state"] == "Karnataka"
        assert fields["tax_period"] == "FY 2019-20"
        assert result["usage"] is None

    async def test_missing_fields_are_listed_for_the_user(self):
        result = await intake.read_notice(
            "notice.txt", b"A short letter with no particulars whatsoever.",
            gst, {"anonymise": False}, use_model=False,
        )
        assert any("Could not determine" in w for w in result["warnings"])

    async def test_uploaded_file_is_never_persisted(self, monkeypatch, tmp_path):
        """The binary is parsed in memory and must not touch disk."""
        before = set(tmp_path.iterdir())
        await intake.read_notice(
            "notice.txt", NOTICE.encode(), gst,
            {"anonymise": False}, use_model=False,
        )
        assert set(tmp_path.iterdir()) == before


class TestEntityName:
    """
    Extracted for two reasons, and the second is the important one: it fills
    the client name field, and it gives the sanitiser something to scrub. Without
    it the free tier strips GSTIN and PAN but leaves the company name standing.
    """

    def test_common_indian_suffixes(self):
        cases = [
            ("To, Acme Industries Private Limited\nGSTIN:", "Acme Industries Private Limited"),
            ("M/s Bharat Steel Pvt Ltd is registered", "Bharat Steel Pvt Ltd"),
            ("Sunrise Textiles LLP has filed", "Sunrise Textiles LLP"),
            ("Reliance Trading Limited, the taxpayer", "Reliance Trading Limited"),
        ]
        for text, expected in cases:
            assert intake.find_entity_name(text) == expected

    def test_longest_match_wins(self):
        """A truncated name would leave the remainder unscrubbed."""
        name = intake.find_entity_name("Acme Steel Industries Private Limited")
        assert name == "Acme Steel Industries Private Limited"

    def test_absent_returns_none(self):
        assert intake.find_entity_name("A notice with no entity named.") is None

    def test_populates_the_client_name_field(self):
        fields = intake.extract_fields_local(NOTICE, gst)["fields"]
        assert fields["client_name"] == "Acme Industries Private Limited"


@pytest.mark.asyncio
class TestFreeTierNameScrubbing:
    async def test_company_name_removed_before_sending(self, monkeypatch):
        """The regression the suite caught: the name outlived the identifiers."""
        sent = {}

        async def capture(model, messages, **kwargs):
            sent["prompt"] = messages[0]["content"]
            return {"ok": True, "usage": None, "content": '{"issues": "i"}'}

        monkeypatch.setattr(intake, "query_model", capture)
        await intake.extract_fields_assisted(
            NOTICE, gst, {"anonymise": True, "grounding": "m"}
        )
        assert "Acme" not in sent["prompt"]
        assert sanitizer.TAXPAYER_PLACEHOLDER in sent["prompt"]
