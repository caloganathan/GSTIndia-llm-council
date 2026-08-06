"""Citation verification tests.

The governing rule under test: nothing is ever silently upgraded to VERIFIED.
When the checker fails, is unparseable, or returns garbage, the result must be
UNVERIFIED — the reviewer keeps their warning.
"""

import pytest

from backend import verification
from backend.domains import gst
from backend.verification import NOT_FOUND, UNVERIFIED, VERIFIED


class TestExtractCitations:
    def test_reported_citation(self):
        found = verification.extract_citations(
            "See (2023) 45 GSTL 123 for the proposition.", gst
        )
        assert any("GSTL" in c for c in found)

    def test_taxmann_citation(self):
        found = verification.extract_citations(
            "Relied on [2024] 160 taxmann.com 78 (Guj).", gst
        )
        assert any("taxmann" in c.lower() for c in found)

    def test_case_name_pattern(self):
        found = verification.extract_citations(
            "In Bharti Airtel Ltd v. Union of India, the Court held...", gst
        )
        assert any("Airtel" in c for c in found)

    def test_circular_and_notification(self):
        found = verification.extract_citations(
            "Circular No. 183/15/2022-GST dated 27.12.2022 clarifies this. "
            "See also Notification No. 09/2023-Central Tax.",
            gst,
        )
        joined = " ".join(found)
        assert "Circular" in joined
        assert "Notification" in joined

    def test_writ_petition_number(self):
        found = verification.extract_citations("W.P. No. 1234 of 2023 (Mad)", gst)
        assert any("1234" in c for c in found)

    def test_deduplicates_case_insensitively(self):
        found = verification.extract_citations(
            "(2023) 45 GSTL 123 and again (2023) 45 gstl 123", gst
        )
        assert len(found) == 1

    def test_empty_text(self):
        assert verification.extract_citations("", gst) == []
        assert verification.extract_citations(None, gst) == []


class TestCollectAuthorities:
    def test_reads_the_authorities_table(self):
        determination = {
            "authorities": [
                {"citation": "Section 16(4) CGST Act", "proposition": "ITC time limit"},
            ],
            "draft_reply": "",
        }
        collected = verification.collect_authorities(determination, gst)
        assert collected[0]["citation"] == "Section 16(4) CGST Act"
        assert collected[0]["source"] == "authorities_table"

    def test_catches_citations_only_in_filed_text(self):
        """A citation reaching the reply but not the table is the dangerous one."""
        determination = {
            "authorities": [],
            "defects": [{
                "index": 1,
                "heading": "Blocked credit",
                "authorities": [],
                "submission": "As held in (2022) 40 GSTL 500, the demand fails.",
            }],
        }
        collected = verification.collect_authorities(determination, gst)
        assert any("GSTL" in a["citation"] for a in collected)
        assert collected[0]["source"] == "filed_text"

    def test_authorities_carry_the_defect_they_belong_to(self):
        """
        The export puts verified authority into the filing document and routes
        the rest to the file note. It can only do that per limb.
        """
        determination = {
            "defects": [{
                "index": 5,
                "heading": "Blocked credit under Section 17(5)",
                "authorities": [
                    {"citation": "Safari Retreats, C.A. 2948 of 2023",
                     "proposition": "Functional test governs 17(5)(d)"},
                ],
            }],
        }
        collected = verification.collect_authorities(determination, gst)
        entry = next(a for a in collected if "Safari" in a["citation"])
        assert entry["defect_index"] == 5
        assert entry["defect_heading"] == "Blocked credit under Section 17(5)"

    def test_no_duplicates_across_sources(self):
        determination = {
            "authorities": [{"citation": "(2022) 40 GSTL 500", "proposition": "x"}],
            "draft_reply": "Again (2022) 40 GSTL 500 applies.",
        }
        collected = verification.collect_authorities(determination, gst)
        assert len(collected) == 1

    def test_respects_the_cap(self):
        determination = {
            "authorities": [
                {"citation": f"({2000 + i}) {i} GSTL {i}", "proposition": ""}
                for i in range(1, 40)
            ],
            "draft_reply": "",
        }
        collected = verification.collect_authorities(determination, gst)
        assert len(collected) <= verification.MAX_AUTHORITIES

    def test_handles_plain_string_authorities(self):
        determination = {"authorities": ["Section 73 CGST Act"], "draft_reply": ""}
        collected = verification.collect_authorities(determination, gst)
        assert collected[0]["citation"] == "Section 73 CGST Act"


class TestParseResults:
    def test_plain_json(self):
        parsed = verification._parse_results(
            '{"results": [{"index": 1, "status": "VERIFIED"}]}'
        )
        assert parsed[0]["status"] == VERIFIED

    def test_fenced_json(self):
        parsed = verification._parse_results(
            'Here:\n```json\n{"results": [{"index": 1, "status": "NOT_FOUND"}]}\n```'
        )
        assert parsed[0]["status"] == NOT_FOUND

    def test_json_with_surrounding_prose(self):
        parsed = verification._parse_results(
            'I checked them.\n{"results": [{"index": 1, "status": "UNVERIFIED"}]}\nDone.'
        )
        assert parsed[0]["status"] == UNVERIFIED

    def test_unparseable_returns_none(self):
        assert verification._parse_results("no json at all") is None
        assert verification._parse_results("") is None


@pytest.mark.asyncio
class TestVerifyAuthorities:
    async def test_no_authorities_short_circuits(self):
        result, usage = await verification.verify_authorities(
            {"authorities": [], "draft_reply": ""}, gst, "any/model"
        )
        assert result["checked"] is True
        assert result["summary"]["total"] == 0
        assert usage == []

    async def test_zdr_is_passed_through_to_the_checker(self, monkeypatch):
        """The check prompt carries every citation with its proposition —
        client-derived on the pro tier — so it routes ZDR like every other
        stage. The panel passes the run's tier down; verification honours it."""
        captured = {}

        async def query(model, messages, **kwargs):
            captured["zdr"] = kwargs.get("zdr")
            return {"ok": True, "usage": None,
                    "content": '{"results": [{"index": 1, "status": "VERIFIED"}]}'}

        monkeypatch.setattr(verification, "query_model", query)
        determination = {
            "authorities": [{"citation": "Section 73 CGST Act", "proposition": "x"}],
        }
        await verification.verify_authorities(determination, gst, "m", zdr=True)
        assert captured["zdr"] is True

        await verification.verify_authorities(determination, gst, "m", zdr=False)
        assert captured["zdr"] is False

    async def test_checker_failure_marks_everything_unverified(self, monkeypatch):
        async def failing_query(*args, **kwargs):
            return {"ok": False, "error": "network down"}

        monkeypatch.setattr(verification, "query_model", failing_query)

        determination = {
            "authorities": [{"citation": "(2023) 45 GSTL 123", "proposition": "x"}],
            "draft_reply": "",
        }
        result, _ = await verification.verify_authorities(determination, gst, "m")

        assert result["checked"] is False
        assert all(a["status"] == UNVERIFIED for a in result["authorities"])
        assert result["summary"]["verified"] == 0

    async def test_statuses_applied_from_checker(self, monkeypatch):
        async def query(*args, **kwargs):
            return {
                "ok": True,
                "content": '{"results": ['
                           '{"index": 1, "status": "VERIFIED", "note": "found"},'
                           '{"index": 2, "status": "NOT_FOUND", "note": "no such case"}'
                           ']}',
                "usage": {"total_tokens": 10, "cost": 0.01},
            }

        monkeypatch.setattr(verification, "query_model", query)

        determination = {
            "authorities": [
                {"citation": "Section 73 CGST Act", "proposition": "demand"},
                {"citation": "(2029) 99 GSTL 999", "proposition": "invented"},
            ],
            "draft_reply": "",
        }
        result, _ = await verification.verify_authorities(determination, gst, "m")

        assert result["summary"]["verified"] == 1
        assert result["summary"]["not_found"] == 1
        assert "must be removed or replaced" in result["note"]

    async def test_panel_flagged_citation_cannot_come_back_verified(self, monkeypatch):
        """A counsel's own [UNCERTAIN] flag outranks a clean checker result."""
        async def query(*args, **kwargs):
            return {
                "ok": True,
                "content": '{"results": [{"index": 1, "status": "VERIFIED"}]}',
                "usage": None,
            }

        monkeypatch.setattr(verification, "query_model", query)

        determination = {
            "authorities": [
                {"citation": "(2023) 45 GSTL 123", "proposition": "x",
                 "certainty": "to_verify"},
            ],
            "draft_reply": "",
        }
        result, _ = await verification.verify_authorities(determination, gst, "m")
        assert result["authorities"][0]["status"] == UNVERIFIED

    async def test_garbage_status_falls_back_to_unverified(self, monkeypatch):
        async def query(*args, **kwargs):
            return {
                "ok": True,
                "content": '{"results": [{"index": 1, "status": "PROBABLY FINE"}]}',
                "usage": None,
            }

        monkeypatch.setattr(verification, "query_model", query)

        determination = {
            "authorities": [{"citation": "Section 16 CGST Act", "proposition": "ITC"}],
            "draft_reply": "",
        }
        result, _ = await verification.verify_authorities(determination, gst, "m")
        assert result["authorities"][0]["status"] == UNVERIFIED

    async def test_missing_result_entry_defaults_to_unverified(self, monkeypatch):
        async def query(*args, **kwargs):
            return {"ok": True, "content": '{"results": []}', "usage": None}

        monkeypatch.setattr(verification, "query_model", query)

        determination = {
            "authorities": [{"citation": "Section 16 CGST Act", "proposition": "ITC"}],
            "draft_reply": "",
        }
        result, _ = await verification.verify_authorities(determination, gst, "m")
        assert result["authorities"][0]["status"] == UNVERIFIED


class TestSupersededStatus:
    """
    The stale-authority hole. A real circular that was withdrawn last quarter
    reads exactly like sound authority; a verifier that only asks "does this
    exist?" passes it straight through to a filing.
    """

    def test_prompt_demands_a_currency_check(self):
        from backend.domains import gst
        prompt = verification._build_check_prompt(
            [{"citation": "Circular No. 183/15/2022-GST", "proposition": "x"}], gst
        )
        assert "IS IT STILL GOOD LAW TODAY?" in prompt
        assert verification.SUPERSEDED in prompt
        assert "withdrawn" in prompt and "overruled" in prompt

    def test_superseded_is_actionable(self):
        assert verification.SUPERSEDED in verification.ACTIONABLE
        assert verification.VERIFIED not in verification.ACTIONABLE

    async def test_superseded_counted_and_called_out(self, monkeypatch):
        from backend.domains import gst

        async def query(*args, **kwargs):
            return {
                "ok": True,
                "content": '{"results": [{"index": 1, "status": "SUPERSEDED",'
                           ' "note": "withdrawn w.e.f. 01.04.2025",'
                           ' "correction": "Circular No. 220/2025"}]}',
                "usage": None,
            }

        monkeypatch.setattr(verification, "query_model", query)
        determination = {
            "authorities": [{"citation": "Circular No. 183/15/2022-GST",
                             "proposition": "2A mismatch"}],
            "draft_reply": "",
        }
        result, _ = await verification.verify_authorities(determination, gst, "m")

        assert result["summary"]["superseded"] == 1
        assert result["summary"]["verified"] == 0
        assert "no longer represent the current position" in result["note"]
        assert result["authorities"][0]["correction"] == "Circular No. 220/2025"

    async def test_as_of_is_carried_through(self, monkeypatch):
        from backend.domains import gst

        async def query(*args, **kwargs):
            return {"ok": True, "usage": None,
                    "content": '{"results": [{"index": 1, "status": "VERIFIED",'
                               ' "as_of": "July 2026"}]}'}

        monkeypatch.setattr(verification, "query_model", query)
        result, _ = await verification.verify_authorities(
            {"authorities": [{"citation": "Section 73", "proposition": "x"}],
             "draft_reply": ""}, gst, "m")
        assert result["authorities"][0]["as_of"] == "July 2026"

    async def test_clean_run_says_so_plainly(self, monkeypatch):
        from backend.domains import gst

        async def query(*args, **kwargs):
            return {"ok": True, "usage": None,
                    "content": '{"results": [{"index": 1, "status": "VERIFIED"}]}'}

        monkeypatch.setattr(verification, "query_model", query)
        result, _ = await verification.verify_authorities(
            {"authorities": [{"citation": "Section 73", "proposition": "x"}],
             "draft_reply": ""}, gst, "m")
        assert "remain good law" in result["note"]
