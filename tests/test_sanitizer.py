"""Sanitizer tests.

These are the most important tests in the repository. A failure here means
client identifiers can reach a free endpoint that may retain or train on
them — a professional confidentiality breach, not a bug.
"""

import pytest

from backend import sanitizer


class TestIdentifierStripping:
    def test_pan_removed(self):
        replacements = {}
        out = sanitizer.scrub_text("PAN is AAAPL1234C on record.", replacements)
        assert "AAAPL1234C" not in out
        assert "[PAN-1]" in out
        assert replacements["[PAN-1]"] == "AAAPL1234C"

    def test_gstin_removed_and_not_split_by_pan_rule(self):
        replacements = {}
        out = sanitizer.scrub_text("GSTIN 29AAAPL1234C1ZV was cancelled.", replacements)
        assert "29AAAPL1234C1ZV" not in out
        assert "[GSTIN-1]" in out
        # The embedded PAN must not leak as a separate fragment
        assert "AAAPL1234C" not in out

    def test_email_phone_aadhaar_account(self):
        text = ("Contact ravi@acme.co.in or 9876543210. "
                "Aadhaar 4321 8765 2109. Account 123456789012.")
        out = sanitizer.scrub_text(text, {})
        assert "ravi@acme.co.in" not in out
        assert "9876543210" not in out
        assert "4321 8765 2109" not in out
        assert "123456789012" not in out

    def test_client_name_replaced_including_bare_head(self):
        replacements = {}
        out = sanitizer.scrub_text(
            "Acme Industries Private Limited received the notice. Acme replied late.",
            replacements,
            client_name="Acme Industries Private Limited",
        )
        assert "Acme" not in out
        assert sanitizer.TAXPAYER_PLACEHOLDER in out

    def test_multiple_identifiers_numbered_distinctly(self):
        replacements = {}
        out = sanitizer.scrub_text("PANs AAAPL1234C and BBBPL5678D.", replacements)
        assert "[PAN-1]" in out and "[PAN-2]" in out
        assert replacements["[PAN-1]"] == "AAAPL1234C"
        assert replacements["[PAN-2]"] == "BBBPL5678D"

    def test_empty_input_safe(self):
        assert sanitizer.scrub_text("", {}) == ""
        assert sanitizer.scrub_text(None, {}) == ""


class TestSanitizeMatter:
    MATTER = {
        "client_name": "Acme Industries Private Limited",
        "gstin": "29AAAPL1234C1ZV",
        "notice_type": "ASMT-10",
        "state": "Karnataka",
        "tax_period": "FY 2019-20",
        "amount_disputed": 4_500_000,
        "issues": "ITC mismatch for Acme against GSTIN 29AAAPL1234C1ZV",
        "facts": "Acme Industries Private Limited filed returns. PAN AAAPL1234C.",
        "documents_available": "Ledgers, invoices, mail to ravi@acme.co.in",
    }

    def test_identity_fields_dropped(self):
        clean, _ = sanitizer.sanitize_matter(self.MATTER)
        assert "client_name" not in clean
        assert "gstin" not in clean
        assert clean["_anonymised"] is True

    def test_legal_fields_preserved(self):
        """Stripping must not destroy the facts the analysis depends on."""
        clean, _ = sanitizer.sanitize_matter(self.MATTER)
        assert clean["notice_type"] == "ASMT-10"
        assert clean["state"] == "Karnataka"
        assert clean["tax_period"] == "FY 2019-20"

    def test_no_identifier_survives_anywhere(self):
        """The sacred test: nothing identifying may remain in outgoing text."""
        clean, _ = sanitizer.sanitize_matter(self.MATTER)
        outgoing = " ".join(str(v) for v in clean.values())

        for secret in ("Acme", "AAAPL1234C", "29AAAPL1234C1ZV", "ravi@acme.co.in"):
            assert secret not in outgoing, f"LEAKED: {secret}"

        assert sanitizer.audit_leaks(outgoing) == {}

    def test_amount_bucketed(self):
        clean, replacements = sanitizer.sanitize_matter(self.MATTER)
        assert clean["amount_disputed"] == "INR 10-50 lakh"
        assert replacements["[AMOUNT]"] == "4500000"

    def test_amount_bucket_boundaries(self):
        cases = [
            (50_000, "under INR 1 lakh"),
            (500_000, "INR 1-10 lakh"),
            (2_000_000, "INR 10-50 lakh"),
            (80_000_000, "INR 5-10 crore"),
            (500_000_000, "over INR 10 crore"),
        ]
        for amount, expected in cases:
            clean, _ = sanitizer.sanitize_matter({**self.MATTER, "amount_disputed": amount})
            assert clean["amount_disputed"] == expected

    def test_bucketing_can_be_disabled(self):
        clean, _ = sanitizer.sanitize_matter(self.MATTER, bucket_amounts=False)
        assert clean["amount_disputed"] == 4_500_000


class TestRestore:
    def test_round_trip_restores_identifiers(self):
        matter = {"client_name": "Acme Ltd", "facts": "Acme Ltd has PAN AAAPL1234C."}
        clean, replacements = sanitizer.sanitize_matter(matter)
        assert "AAAPL1234C" not in clean["facts"]

        restored = sanitizer.restore_text(clean["facts"], replacements)
        assert "AAAPL1234C" in restored
        assert "Acme Ltd" in restored

    def test_restore_nested_structures(self):
        replacements = {"[PAN-1]": "AAAPL1234C", "the Taxpayer": "Acme Ltd"}
        payload = {
            "draft": "the Taxpayer holds [PAN-1]",
            "items": [{"note": "[PAN-1] verified"}],
        }
        restored = sanitizer.restore_structure(payload, replacements)
        assert restored["draft"] == "Acme Ltd holds AAAPL1234C"
        assert restored["items"][0]["note"] == "AAAPL1234C verified"

    def test_restore_noop_without_replacements(self):
        assert sanitizer.restore_structure({"a": "b"}, {}) == {"a": "b"}


class TestAuditLeaks:
    def test_flags_each_identifier_type(self):
        leaks = sanitizer.audit_leaks("PAN AAAPL1234C, GSTIN 29AAAPL1234C1ZV")
        assert "PAN" in leaks or "GSTIN" in leaks

    def test_clean_text_reports_nothing(self):
        assert sanitizer.audit_leaks("the Taxpayer disputes the ITC reversal") == {}
