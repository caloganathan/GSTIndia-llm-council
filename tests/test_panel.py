"""Panel orchestration, roles, users and the domain pack."""

import pytest

from backend import panel, roles, users
from backend.domains import get_pack, gst


class TestJsonExtraction:
    def test_plain_object(self):
        assert panel._extract_json('{"confidence": "strong"}')["confidence"] == "strong"

    def test_fenced_object(self):
        text = '```json\n{"confidence": "weak"}\n```'
        assert panel._extract_json(text)["confidence"] == "weak"

    def test_object_with_surrounding_prose(self):
        text = 'Here is my determination:\n{"confidence": "defensible"}\nRegards.'
        assert panel._extract_json(text)["confidence"] == "defensible"

    def test_nested_braces_inside_strings(self):
        text = '{"draft_reply": "Use {this} form", "confidence": "strong"}'
        parsed = panel._extract_json(text)
        assert parsed["draft_reply"] == "Use {this} form"

    def test_unparseable_returns_none(self):
        assert panel._extract_json("no json here") is None
        assert panel._extract_json("") is None


class TestFallbackDetermination:
    def test_degraded_output_is_flagged_and_warned(self):
        result = panel._fallback_determination("raw text", "chairman broke")
        assert result["_degraded"] is True
        assert result["confidence"] == "insufficient_information"
        assert any("must not be filed" in flag for flag in result["risk_flags"])


class TestUsageAggregation:
    def test_sums_across_stages_ignoring_none(self):
        usage = panel._sum_usage(
            [{"total_tokens": 100, "cost": 0.01}, None],
            [{"total_tokens": 50, "cost": 0.005}],
        )
        assert usage["total_tokens"] == 150
        assert usage["total_cost"] == pytest.approx(0.015)

    def test_empty_is_zero(self):
        assert panel._sum_usage([], []) == {"total_tokens": 0, "total_cost": 0.0}


class TestRoles:
    def test_four_adversarial_roles(self):
        keys = [r.key for r in roles.PANEL_ROLES]
        assert keys == ["revenue", "assessee", "procedural", "risk"]

    def test_prompts_carry_the_anti_fabrication_rule(self):
        matter = {"notice_type": "ASMT-10", "state": "Karnataka", "facts": "x"}
        for role in roles.PANEL_ROLES:
            prompt = roles.build_role_prompt(role, matter, gst)
            assert "[UNCERTAIN]" in prompt
            assert "NEVER invent a case" in prompt

    def test_procedural_counsel_alone_gets_the_grounds_checklist(self):
        matter = {"notice_type": "DRC-01", "state": "Tamil Nadu"}
        procedural = roles.build_role_prompt(roles.PROCEDURAL_COUNSEL, matter, gst)
        revenue = roles.build_role_prompt(roles.REVENUE_ADVOCATE, matter, gst)
        assert "PROCEDURAL AND JURISDICTIONAL GROUNDS" in procedural
        assert "PROCEDURAL AND JURISDICTIONAL GROUNDS" not in revenue

    def test_cross_exam_prompt_includes_peers_and_demands_concessions(self):
        matter = {"notice_type": "ASMT-10", "state": "Maharashtra"}
        peers = [
            {"key": "assessee", "title": "Assessee's Advocate", "analysis": "ITC is valid"},
            {"key": "risk", "title": "Risk Counsel", "analysis": "penalty exposure"},
        ]
        prompt = roles.build_cross_exam_prompt(
            roles.REVENUE_ADVOCATE, matter, gst, peers
        )
        assert "ITC is valid" in prompt
        assert "CONCESSIONS" in prompt

    def test_chairman_prompt_requests_the_json_contract(self):
        matter = {"notice_type": "DRC-01", "state": "Gujarat"}
        prompt = roles.build_chairman_prompt(matter, gst, [], [])
        for field in ("recommended_position", "draft_reply", "authorities",
                      "working_note", "board_summary", "panel_disagreements"):
            assert field in prompt

    def test_matter_formatting_omits_blank_fields(self):
        rendered = roles.format_matter(
            {"notice_type": "ASMT-10", "state": "Kerala", "facts": ""}, gst
        )
        assert "Kerala" in rendered
        assert "FACTS AND BACKGROUND" not in rendered


class TestJurisdiction:
    def test_binding_high_court_named(self):
        brief = gst.jurisdiction_brief("Karnataka")
        assert "High Court of Karnataka" in brief
        assert "BIND" in brief

    def test_other_high_courts_are_persuasive(self):
        assert "PERSUASIVE ONLY" in gst.jurisdiction_brief("Tamil Nadu")

    def test_unknown_state_degrades_safely(self):
        brief = gst.jurisdiction_brief("Atlantis")
        assert "persuasive only" in brief.lower()

    def test_empty_state_degrades_safely(self):
        assert "not specified" in gst.jurisdiction_brief("").lower()

    def test_shared_high_courts_mapped(self):
        assert gst.STATE_HIGH_COURT["Punjab"] == gst.STATE_HIGH_COURT["Haryana"]
        assert "Gauhati" in gst.STATE_HIGH_COURT["Assam"]


class TestDomainPack:
    def test_registry_lookup(self):
        assert get_pack("gst") is gst

    def test_unknown_domain_raises(self):
        with pytest.raises(ValueError):
            get_pack("wealth-tax")

    def test_core_notice_types_present(self):
        for code in ("ASMT-10", "DRC-01", "DRC-01A", "DRC-07", "RFD-08", "REG-17"):
            assert code in gst.NOTICE_TYPES

    def test_intake_schema_marks_sensitive_fields(self):
        schema = gst.intake_schema()
        sensitive = {f["key"] for f in schema["fields"] if f.get("sensitive")}
        assert {"client_name", "gstin"} <= sensitive

    def test_statutory_framework_covers_limitation_and_natural_justice(self):
        text = gst.STATUTORY_FRAMEWORK
        assert "s.73" in text and "s.74" in text
        assert "75(4)" in text and "75(7)" in text


class TestUserRoles:
    def test_staff_cannot_see_deliberation_or_export(self):
        perms = users.ROLE_PERMISSIONS["staff"]
        assert perms["view_deliberation"] is False
        assert perms["export"] is False
        assert perms["admin"] is False

    def test_manager_works_but_cannot_administer(self):
        perms = users.ROLE_PERMISSIONS["manager"]
        assert perms["view_deliberation"] is True
        assert perms["export"] is True
        assert perms["manage_users"] is False

    def test_partner_has_everything(self):
        assert all(users.ROLE_PERMISSIONS["partner"].values())

    def test_password_hash_round_trip(self):
        stored = users.hash_password("correct horse battery")
        assert users.verify_password("correct horse battery", stored)
        assert not users.verify_password("wrong password", stored)

    def test_hash_is_salted(self):
        assert users.hash_password("same") != users.hash_password("same")

    def test_malformed_hash_rejected(self):
        assert not users.verify_password("x", "not-a-real-hash")

    def test_can_helper(self):
        partner = {"role": "partner"}
        staff = {"role": "staff"}
        assert users.can(partner, "admin") is True
        assert users.can(staff, "admin") is False
        assert users.can(None, "admin") is False


class TestRoleRedaction:
    def test_staff_output_strips_counsel_arguments(self):
        from backend.auth import redact_for_role

        payload = {
            "id": "m1",
            "result": {
                "analyses": [{"title": "Revenue", "analysis": "internal reasoning"}],
                "cross_exams": [{"title": "Risk", "analysis": "more reasoning"}],
                "determination": {"recommended_position": "visible"},
            },
        }
        redacted = redact_for_role(payload, {"role": "staff"})
        assert redacted["result"]["analyses"] == []
        assert redacted["result"]["cross_exams"] == []
        assert redacted["result"]["determination"]["recommended_position"] == "visible"
        assert redacted["result"]["_redacted"] is True

    def test_partner_sees_everything(self):
        from backend.auth import redact_for_role

        payload = {"result": {"analyses": [{"analysis": "internal"}], "cross_exams": []}}
        assert redact_for_role(payload, {"role": "partner"})["result"]["analyses"]
