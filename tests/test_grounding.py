"""Current-law grounding and token routing.

The gap this closes: verification confirms an authority exists, but a model
arguing from training data alone does not know that the provision was amended,
the circular withdrawn, or limitation extended after its cutoff. In GST those
are precisely the things in dispute.
"""

import importlib

import pytest

from backend import config, grounding
from backend.domains import gst
from backend.grounding import NO_CHANGE


class TestBriefingPrompt:
    MATTER = {
        "notice_type": "ASMT-10",
        "section_invoked": "61",
        "tax_period": "FY 2019-20",
        "state": "Karnataka",
        "issues": "ITC availed in excess of GSTR-2A",
    }

    def test_asks_about_what_actually_moves(self):
        prompt = grounding.build_briefing_prompt(self.MATTER, gst)
        for topic in ("AMENDMENTS", "CIRCULARS", "LIMITATION", "AMNESTY",
                      "PROCEDURAL CHANGES", "JUDICIAL DEVELOPMENTS"):
            assert topic in prompt

    def test_scoped_to_this_matter(self):
        prompt = grounding.build_briefing_prompt(self.MATTER, gst)
        assert "FY 2019-20" in prompt
        assert "ASMT-10" in prompt
        assert "GSTR-2A" in prompt

    def test_permits_a_nil_return(self):
        """'Nothing changed' must be cheap to say, or it gets padded."""
        prompt = grounding.build_briefing_prompt(self.MATTER, gst)
        assert NO_CHANGE in prompt
        assert "correct and useful answer" in prompt

    def test_forbids_inference(self):
        prompt = grounding.build_briefing_prompt(self.MATTER, gst)
        assert "Do not infer" in prompt

    def test_tolerates_a_sparse_matter(self):
        prompt = grounding.build_briefing_prompt({"notice_type": "DRC-01"}, gst)
        assert "DRC-01" in prompt


class TestBriefingBlock:
    def test_absent_when_disabled(self):
        assert grounding.briefing_block(None) == ""

    def test_unavailable_tells_counsel_it_is_blind(self):
        """A counsel that knows it may be stale argues more carefully."""
        block = grounding.briefing_block({"available": False})
        assert "VERIFY CURRENT POSITION" in block
        assert "may be out of date" in block

    def test_no_change_says_argue_the_settled_position(self):
        block = grounding.briefing_block(
            {"available": True, "material_change": False}
        )
        assert "no material change" in block.lower()

    def test_material_change_overrides_training_data(self):
        block = grounding.briefing_block({
            "available": True, "material_change": True,
            "content": "Section 16(4) relaxed by s.16(5).",
        })
        assert "takes precedence over your training data" in block
        assert "Section 16(4) relaxed" in block


@pytest.mark.asyncio
class TestBuildBriefing:
    TIER = {"grounding": "some/model", "verifier": "fallback/model"}
    MATTER = {"notice_type": "ASMT-10", "tax_period": "FY 2019-20"}

    async def test_disabled_returns_nothing(self, monkeypatch):
        monkeypatch.setattr(config, "PANEL_WEB_GROUNDING", False)
        briefing, usage = await grounding.build_briefing(self.MATTER, gst, self.TIER)
        assert briefing is None
        assert usage is None

    async def test_uses_web_search_and_a_cap(self, monkeypatch):
        captured = {}

        async def fake_query(model, messages, **kwargs):
            captured.update(kwargs)
            captured["model"] = model
            return {"ok": True, "content": "Circular 183 withdrawn.",
                    "usage": {"total_tokens": 500, "cost": 0.01}}

        monkeypatch.setattr(config, "PANEL_WEB_GROUNDING", True)
        monkeypatch.setattr(grounding, "query_model", fake_query)

        briefing, usage = await grounding.build_briefing(self.MATTER, gst, self.TIER)

        assert captured["web_search"] is True, "grounding must actually search"
        assert captured["max_tokens"] == config.role_max_tokens("briefing")
        assert captured["effort"] == config.role_effort("briefing")
        assert captured["model"] == "some/model"
        assert briefing["available"] is True
        assert briefing["material_change"] is True
        assert usage["total_tokens"] == 500

    async def test_nil_result_is_not_a_material_change(self, monkeypatch):
        async def fake_query(*args, **kwargs):
            return {"ok": True, "content": NO_CHANGE, "usage": None}

        monkeypatch.setattr(config, "PANEL_WEB_GROUNDING", True)
        monkeypatch.setattr(grounding, "query_model", fake_query)

        briefing, _ = await grounding.build_briefing(self.MATTER, gst, self.TIER)
        assert briefing["available"] is True
        assert briefing["material_change"] is False

    async def test_failure_is_never_fatal(self, monkeypatch):
        async def failing(*args, **kwargs):
            return {"ok": False, "error": "search unavailable"}

        monkeypatch.setattr(config, "PANEL_WEB_GROUNDING", True)
        monkeypatch.setattr(grounding, "query_model", failing)

        briefing, usage = await grounding.build_briefing(self.MATTER, gst, self.TIER)
        assert briefing["available"] is False
        assert "search unavailable" in briefing["error"]

    async def test_falls_back_to_the_verifier_model(self, monkeypatch):
        captured = {}

        async def fake_query(model, messages, **kwargs):
            captured["model"] = model
            return {"ok": True, "content": "x", "usage": None}

        monkeypatch.setattr(config, "PANEL_WEB_GROUNDING", True)
        monkeypatch.setattr(grounding, "query_model", fake_query)

        await grounding.build_briefing(
            self.MATTER, gst, {"verifier": "fallback/model"}
        )
        assert captured["model"] == "fallback/model"


class TestTokenRouting:
    def test_reasoning_is_spent_where_it_matters(self):
        """Limitation and the final decision get more than a lookup does."""
        assert config.role_effort("procedural") == "high"
        assert config.role_effort("chairman") == "high"
        assert config.role_effort("verifier") == "low"
        assert config.role_effort("briefing") == "low"

    def test_unknown_role_falls_back_to_the_global_default(self):
        assert config.role_effort("nonexistent") == config.REASONING_EFFORT

    def test_every_stage_is_capped(self):
        for stage in ("opening", "cross_exam", "chairman", "briefing", "verifier"):
            assert config.role_max_tokens(stage) > 0

    def test_cross_exam_is_cheaper_than_an_opening(self):
        """Critique of existing material needs less room than the analysis."""
        assert config.role_max_tokens("cross_exam") < config.role_max_tokens("opening")

    def test_chairman_has_the_most_room(self):
        caps = config.ROLE_MAX_TOKENS
        assert caps["chairman"] == max(caps.values())

    def test_effort_overridable_by_environment(self, monkeypatch):
        monkeypatch.setenv("EFFORT_PROCEDURAL", "low")
        importlib.reload(config)
        assert config.role_effort("procedural") == "low"
        monkeypatch.delenv("EFFORT_PROCEDURAL")
        importlib.reload(config)


class TestPayloadWiring:
    """The routing decisions must actually reach the wire."""

    @staticmethod
    def _body(effort="low", web_search=False, zdr=False,
              max_tokens=None, web_max_results=None):
        from backend.openrouter import _compose_request
        return _compose_request("m", [], effort, web_search, zdr,
                                max_tokens, web_max_results)

    def test_max_tokens_reaches_the_payload(self):
        assert self._body(max_tokens=900)["max_tokens"] == 900

    def test_omitted_when_unset(self):
        assert "max_tokens" not in self._body()

    def test_web_result_count_reaches_the_plugin(self):
        body = self._body(web_search=True, web_max_results=6)
        assert body["plugins"] == [{"id": "web", "max_results": 6}]

    def test_zdr_and_search_coexist(self):
        body = self._body(web_search=True, zdr=True, web_max_results=3)
        assert body["provider"] == {"data_collection": "deny"}
        assert body["plugins"][0]["id"] == "web"

    def test_zdr_absent_unless_asked(self):
        # The confidentiality flag must never be set by accident, in either
        # direction: absent when not requested, exact when requested.
        assert "provider" not in self._body()

    def test_usage_accounting_always_requested(self):
        # The cost figure shown to the user is only truthful if every call
        # asks for it.
        assert self._body()["usage"] == {"include": True}
