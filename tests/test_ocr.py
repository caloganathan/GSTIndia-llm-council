"""Scanned-notice reading.

Two things are under test and the second matters more than the first:

1. That OCR recovers text from a scan at all.
2. That the ABSENCE of the engine degrades exactly as the product behaved
   before OCR existed — an honest report, never a guess. The engine is an
   optional extra, so most installations will not have it, and a crash or a
   silent empty extraction on those installations would be worse than not
   having built this.

Tests that need the engine skip without it. Tests that need it ABSENT simulate
absence, so they run everywhere.
"""

import io

import pytest

from backend import intake, ocr

ENGINE_READY = ocr.available()[0]
needs_engine = pytest.mark.skipif(
    not ENGINE_READY, reason="OCR extra not installed (uv sync --extra ocr)")


def _textless_pdf() -> bytes:
    """
    A PDF with a page and no text layer.

    Built with pypdf, which is a core dependency, so the degradation tests
    below run on a BASE install — the install most firms will have on day one,
    and therefore the behaviour it is least acceptable to leave untested. A
    fixture needing the imaging stack would have skipped exactly there.
    """
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _scanned_pdf(lines, width=1240, height=1754) -> bytes:
    """
    A PDF whose text is drawn as pixels — a scan, with words in it.

    Built rather than committed as a fixture so the test states what it is
    testing. A committed binary would hide whether the page has a text layer,
    which is the entire premise of the test. Needs the imaging stack, which
    arrives with the OCR extra, so only the end-to-end tests use it.
    """
    pytest.importorskip("PIL")
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    y = 80
    for line in lines:
        draw.text((70, y), line, fill="black")
        y += 46

    buffer = io.BytesIO()
    image.save(buffer, format="PDF", resolution=150.0)
    return buffer.getvalue()


NOTICE_LINES = [
    "FORM GST ASMT-10",
    "Reference No: ZD330226255583F   Date: 14.06.2026",
    "GSTIN: 33AAGCG5581D1ZC",
    "Tvl. GRAM ENVOSOLUTION PRIVATE LIMITED",
    "Tax Period: FY 2023-24",
    "Notice for intimating discrepancies in the return",
    "Section under which notice is issued: 61",
]


class TestAvailability:
    def test_reports_a_reason_when_unavailable(self, monkeypatch):
        # The reason belongs in front of the user: "install the OCR extra" is
        # an action they can take.
        monkeypatch.setattr(ocr, "available",
                            lambda: (False, "The OCR engine is not installed."))
        ready, reason = ocr.available()
        assert ready is False
        assert "not installed" in reason

    def test_returns_a_two_tuple_either_way(self):
        ready, reason = ocr.available()
        assert isinstance(ready, bool)
        assert reason is None or isinstance(reason, str)


class TestLineReconstruction:
    """
    Reading order is load-bearing, not cosmetic.

    `defects.segment()` finds limb headings by line structure and
    `notice_tables` validates a row of figures against the total printed on
    that same row. Boxes joined in the wrong order break both.
    """

    def _box(self, left, top, width=100, height=30):
        return [[left, top], [left + width, top],
                [left + width, top + height], [left, top + height]]

    def test_boxes_on_one_row_join_left_to_right(self):
        result = [
            (self._box(400, 100), "50,000", 0.99),
            (self._box(100, 100), "IGST", 0.99),
            (self._box(250, 100), "CGST", 0.99),
        ]
        lines = ocr._lines_from_result(result)
        assert len(lines) == 1
        assert lines[0]["text"] == "IGST CGST 50,000"

    def test_rows_are_ordered_top_to_bottom(self):
        result = [
            (self._box(100, 300), "second", 0.99),
            (self._box(100, 100), "first", 0.99),
        ]
        lines = ocr._lines_from_result(result)
        assert [line["text"] for line in lines] == ["first", "second"]

    def test_a_row_is_only_as_trustworthy_as_its_weakest_cell(self):
        # In an annexure the least legible cell is usually the figure, which
        # is the one thing that must not be trusted silently.
        result = [
            (self._box(100, 100), "Tax", 0.99),
            (self._box(250, 100), "1,24,500", 0.42),
        ]
        lines = ocr._lines_from_result(result)
        assert lines[0]["confidence"] == pytest.approx(0.42)

    def test_rows_do_not_drift_together_on_tall_cells(self):
        # Grouping against a running mean eventually swallows the next row.
        result = [
            (self._box(100, 100), "row one", 0.99),
            (self._box(100, 112), "still row one", 0.99),
            (self._box(100, 160), "row two", 0.99),
        ]
        lines = ocr._lines_from_result(result)
        assert len(lines) == 2

    def test_empty_and_malformed_entries_are_skipped(self):
        result = [
            (self._box(100, 100), "", 0.99),
            (self._box(100, 100), "   ", 0.99),
            ("malformed",),
            (self._box(100, 100), "kept", 0.99),
        ]
        lines = ocr._lines_from_result(result)
        assert [line["text"] for line in lines] == ["kept"]

    def test_no_result_is_no_lines(self):
        assert ocr._lines_from_result([]) == []
        assert ocr._lines_from_result(None) == []


class TestQualityDescription:
    def test_always_says_the_figures_must_be_checked(self):
        warnings = ocr.describe_quality({
            "text": "something", "pages_read": 3, "mean_confidence": 0.97})
        assert any("must be checked" in w for w in warnings)

    def test_poor_scan_is_called_poor(self):
        warnings = ocr.describe_quality({
            "text": "something", "pages_read": 1, "mean_confidence": 0.71})
        assert any("poor quality" in w for w in warnings)

    def test_good_scan_does_not_raise_a_quality_warning(self):
        warnings = ocr.describe_quality({
            "text": "something", "pages_read": 1, "mean_confidence": 0.98})
        assert not any("poor quality" in w for w in warnings)

    def test_doubtful_lines_are_counted_for_the_reviewer(self):
        warnings = ocr.describe_quality({
            "text": "x", "pages_read": 1, "mean_confidence": 0.95,
            "doubtful_count": 4})
        assert any("4 line(s)" in w for w in warnings)

    def test_truncation_tells_the_user_what_to_do(self):
        warnings = ocr.describe_quality({
            "text": "x", "pages_read": 40, "mean_confidence": 0.95,
            "truncated": True})
        assert any("separate document" in w for w in warnings)

    def test_nothing_recovered_is_reported_honestly(self):
        warnings = ocr.describe_quality({"text": "", "pages_read": 2})
        assert len(warnings) == 1
        assert "no text could be recovered" in warnings[0]


class TestDegradationWithoutTheEngine:
    """
    The installation most firms will have on day one.

    Behaviour must be identical to the product before OCR existed: report the
    scan, name the remedy, never guess.
    """

    def test_scanned_pdf_reports_honestly_and_does_not_crash(self, monkeypatch):
        monkeypatch.setattr(
            ocr, "available",
            lambda: (False, "The OCR engine is not installed. "
                            "Install the OCR extra: uv sync --extra ocr"))
        document = intake.extract_document("scan.pdf", _textless_pdf())

        assert document["source"] != "ocr"
        assert document["ocr"] is None
        joined = " ".join(document["warnings"])
        assert "scan with no text layer" in joined
        assert "uv sync --extra ocr" in joined

    def test_no_fields_are_invented_from_an_unread_scan(self, monkeypatch):
        monkeypatch.setattr(ocr, "available", lambda: (False, "not installed"))
        document = intake.extract_document("scan.pdf", _textless_pdf())
        assert len(document["text"]) < intake.MIN_USEFUL_TEXT

    def test_an_engine_that_raises_is_reported_not_swallowed(self, monkeypatch):
        monkeypatch.setattr(ocr, "available", lambda: (True, None))

        def explode(content, **kwargs):
            raise RuntimeError("model file corrupt")

        monkeypatch.setattr(ocr, "ocr_pdf", explode)
        document = intake.extract_document("scan.pdf", _textless_pdf())
        assert any("OCR failed" in w for w in document["warnings"])
        assert any("model file corrupt" in w for w in document["warnings"])


class TestOcrIsNotAppliedToDocumentsThatDoNotNeedIt:
    def test_a_pdf_with_a_text_layer_is_never_re_read_by_ocr(self, monkeypatch):
        called = []
        monkeypatch.setattr(ocr, "available", lambda: (True, None))
        monkeypatch.setattr(ocr, "ocr_pdf",
                            lambda *a, **k: called.append(1) or {"text": ""})

        # A .txt of adequate length stands in for any document whose text was
        # read successfully — the guard is on length, not on file type.
        text = "GSTIN: 33AAGCG5581D1ZC. " * 40
        document = intake.extract_document("notice.txt", text.encode())
        assert document["source"] == "text-layer"
        assert called == []

    def test_ocr_is_not_attempted_on_a_docx(self, monkeypatch):
        called = []
        monkeypatch.setattr(ocr, "available", lambda: (True, None))
        monkeypatch.setattr(ocr, "ocr_pdf",
                            lambda *a, **k: called.append(1) or {"text": ""})

        from docx import Document
        document_file = Document()
        document_file.add_paragraph("short")
        buffer = io.BytesIO()
        document_file.save(buffer)

        intake.extract_document("notice.docx", buffer.getvalue())
        assert called == []


@needs_engine
class TestEndToEndWithTheEngine:
    def test_reads_a_scanned_notice_with_no_text_layer(self):
        document = intake.extract_document("scan.pdf", _scanned_pdf(NOTICE_LINES))
        assert document["source"] == "ocr"
        assert document["ocr"] is not None
        assert "ASMT" in document["text"].upper()

    def test_the_gstin_survives_ocr_and_is_extracted(self):
        from backend.domains import get_pack
        document = intake.extract_document("scan.pdf", _scanned_pdf(NOTICE_LINES))
        fields = intake.extract_fields_local(document["text"], get_pack("gst"))
        assert fields["fields"].get("gstin") == "33AAGCG5581D1ZC"
        assert fields["fields"].get("state") == "Tamil Nadu"

    def test_quality_metadata_travels_with_the_text(self):
        document = intake.extract_document("scan.pdf", _scanned_pdf(NOTICE_LINES))
        result = document["ocr"]
        assert result["pages_read"] == 1
        assert 0 < result["mean_confidence"] <= 1.0

    def test_ocr_read_fields_are_marked_as_such_end_to_end(self):
        """
        The whole point of the provenance chain: a figure read off a scan must
        never be presented to a reviewer as though it were printed text.
        """
        import asyncio
        from backend.domains import get_pack

        result = asyncio.run(intake.read_notice_set(
            [("scan.pdf", _scanned_pdf(NOTICE_LINES))],
            get_pack("gst"),
            {"anonymise": False},
            use_model=False,
        ))
        assert result["scanned"] is True
        assert any(str(source).endswith("-ocr")
                   for source in result["sources"].values())
