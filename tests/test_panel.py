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
        for field in ("recommended_position", "preliminary_submissions",
                      "defects", "posture", "submission", "evidence_gap",
                      "prayer_relief", "authorities", "working_note",
                      "board_summary", "panel_disagreements"):
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


class TestMergeDetermination:
    """
    The notice is authoritative on what was alleged. The chairman is
    authoritative on what we say about it. Keeping that boundary stops a
    drafting model from restating the department's own arithmetic wrongly in
    a document filed against that arithmetic.
    """

    INTAKE = [
        {"index": 1, "heading": "Excess ITC against GSTR-2B",
         "type": "itc_excess_2b", "posture": "undecided",
         "amount_by_head": {"cgst": 58366.0, "sgst": 58366.0},
         "sections": ["16(2)(aa)"], "annexures": [], "splits": [],
         "evidence_required": ["Month-wise GSTR-2B"], "evidence_gap": [],
         "authorities": [], "legal_framework": [], "payment": {}},
        {"index": 2, "heading": "GSTR-1 late fee", "type": "late_fee",
         "posture": "agreed_paid", "amount_by_head": {"cgst": 1150.0, "sgst": 1150.0},
         "sections": ["47(1)"], "annexures": [], "splits": [],
         "evidence_required": [], "evidence_gap": [], "authorities": [],
         "legal_framework": [], "payment": {}},
    ]

    def test_chairman_position_is_applied(self):
        merged = panel.merge_determination(self.INTAKE, {"defects": [
            {"index": 1, "posture": "contested", "submission": "Not sustainable."},
        ]})
        assert merged[0]["posture"] == "contested"
        assert merged[0]["submission"] == "Not sustainable."

    def test_department_figures_are_not_overwritten(self):
        merged = panel.merge_determination(self.INTAKE, {"defects": [
            {"index": 1, "posture": "contested",
             "amount_by_head": {"cgst": 999.0},
             "heading": "Something the model renamed it"},
        ]})
        assert merged[0]["amount_by_head"] == {"cgst": 58366.0, "sgst": 58366.0}
        assert merged[0]["heading"] == "Excess ITC against GSTR-2B"

    def test_a_structured_key_of_the_wrong_shape_is_dropped(self):
        """
        A model asked for an object routinely answers with a sentence. Carried
        forward verbatim, that string reached code indexing a mapping and the
        filing reply raised mid-response — the download died as "Failed to
        fetch". The limb keeps what intake read instead.
        """
        merged = panel.merge_determination(self.INTAKE, {"defects": [
            {"index": 2, "posture": "agreed_paid",
             "payment": "Rs. 2,300 paid vide DRC-03 dated 26/06/2026"},
        ]})
        assert merged[1]["payment"] == {}

    def test_a_wrongly_shaped_value_does_not_block_the_rest_of_the_limb(self):
        merged = panel.merge_determination(self.INTAKE, {"defects": [
            {"index": 1, "posture": "contested", "payment": "paid",
             "submission": "Not sustainable."},
        ]})
        assert merged[0]["submission"] == "Not sustainable."
        assert merged[0]["posture"] == "contested"

    def test_a_list_key_returned_as_prose_is_dropped(self):
        merged = panel.merge_determination(self.INTAKE, {"defects": [
            {"index": 1, "authorities": "Section 16(2) of the CGST Act",
             "evidence_gap": "the August e-invoice"},
        ]})
        assert merged[0]["authorities"] == []
        assert merged[0]["evidence_gap"] == []

    def test_a_correctly_shaped_value_still_applies(self):
        """The guard must not swallow well-formed output."""
        merged = panel.merge_determination(self.INTAKE, {"defects": [
            {"index": 2, "posture": "agreed_paid",
             "payment": {"reference": "AD290626001122B", "date": "26/06/2026"}},
        ]})
        assert merged[1]["payment"]["reference"] == "AD290626001122B"

    def test_an_unanswered_limb_is_flagged_not_dropped(self):
        """A limb missing from the reply is a limb the officer confirms."""
        merged = panel.merge_determination(self.INTAKE, {"defects": [
            {"index": 1, "posture": "contested"},
        ]})
        assert len(merged) == 2
        assert merged[1]["unanswered"] is True
        assert "unanswered" not in merged[0]

    def test_a_limb_the_panel_adds_is_kept(self):
        merged = panel.merge_determination(self.INTAKE, {"defects": [
            {"index": 1, "posture": "contested"},
            {"index": 2, "posture": "agreed_paid"},
            {"index": 3, "heading": "Reverse charge short paid",
             "posture": "contested"},
        ]})
        assert len(merged) == 3
        assert merged[2]["source"] == "panel"

    def test_an_unknown_posture_falls_back_to_undecided(self):
        merged = panel.merge_determination(self.INTAKE, {"defects": [
            {"index": 1, "posture": "definitely_fine"},
        ]})
        assert merged[0]["posture"] == "undecided"

    def test_empty_determination_leaves_the_notice_intact(self):
        merged = panel.merge_determination(self.INTAKE, {})
        assert len(merged) == 2
        assert all(d.get("unanswered") for d in merged)

    def test_result_is_ordered_by_the_departments_numbering(self):
        merged = panel.merge_determination(self.INTAKE, {"defects": [
            {"index": 2, "posture": "agreed_paid"},
            {"index": 1, "posture": "contested"},
        ]})
        assert [d["index"] for d in merged] == [1, 2]


# ---------------------------------------------------------------------------
# The anonymisation gate, end to end
# ---------------------------------------------------------------------------


class TestTheAnonymisationGate:
    """
    The gate CLAUDE.md calls sacred, tested through the stream it protects.

    Two properties, and both are needed: identifiers planted in the defect
    text — the notice's own prose, which the intake form scrub does not touch
    but every counsel prompt carries — must be scrubbed before any model call;
    and if the scrub ever fails, the run must abort before a single request
    leaves the machine.
    """

    def _matter(self):
        from backend import defects
        return {
            "client_name": "Acme Industries Private Limited",
            "gstin": "29AAAPL1234C1ZV",
            "notice_type": "ASMT-10",
            "state": "Karnataka",
            "tax_period": "FY 2019-20",
            "issues": "ITC availed in excess of GSTR-2B.",
            "facts": "Returns were filed in time.",
            "defects": [defects.new_defect(
                1,
                "Excess ITC availed by Acme Industries Private Limited "
                "(GSTIN 29AAAPL1234C1ZV)",
                "itc_excess_2b",
                department_contention=(
                    "Tvl. Acme Industries Private Limited, GSTIN "
                    "29AAAPL1234C1ZV, availed credit in excess of GSTR-2B."),
                amount_by_head={"cgst": 50000, "sgst": 50000},
            )],
        }

    async def test_defect_text_is_scrubbed_before_any_model_call(
            self, monkeypatch):
        from backend import config
        monkeypatch.setattr(config, "PANEL_WEB_GROUNDING", False)

        prompts = []

        async def fake_query(model, messages, **kwargs):
            prompts.append(messages[0]["content"])
            return {"ok": True, "content": "analysis", "usage": None,
                    "model": model}

        monkeypatch.setattr(panel, "query_model", fake_query)

        events = []
        async for event in panel.run_panel_stream(
                self._matter(), tier_name="draft", skip_verification=True):
            events.append(event)

        assert not any(e["type"] == "error" for e in events), \
            "the scrub should succeed, not abort"
        assert prompts, "no model was ever called"
        outgoing = "\n".join(prompts)
        for secret in ("29AAAPL1234C1ZV", "AAAPL1234C", "Acme"):
            assert secret not in outgoing, f"LEAKED to a model prompt: {secret}"

    async def test_the_run_aborts_when_the_scrub_fails(self, monkeypatch):
        """If sanitisation ever regresses, the probe — built from the same
        rendered block the prompts use — must catch it and abort."""
        from backend import config
        monkeypatch.setattr(config, "PANEL_WEB_GROUNDING", False)
        monkeypatch.setattr(panel.sanitizer, "sanitize_matter",
                            lambda matter, **kw: (dict(matter), {}))

        called = []

        async def fake_query(*args, **kwargs):
            called.append(1)
            return {"ok": True, "content": ""}

        monkeypatch.setattr(panel, "query_model", fake_query)

        events = []
        async for event in panel.run_panel_stream(
                self._matter(), tier_name="draft", skip_verification=True):
            events.append(event)

        assert events[0]["type"] == "error"
        assert "Anonymisation failed" in events[0]["message"]
        assert not called, "a request left the machine after the gate failed"

    async def test_a_surviving_client_name_alone_is_enough_to_abort(
            self, monkeypatch):
        """The trade name carries no regex signature, so the audit must be
        told it. A matter whose only leak is the client's name must abort."""
        from backend import config
        monkeypatch.setattr(config, "PANEL_WEB_GROUNDING", False)
        monkeypatch.setattr(panel.sanitizer, "sanitize_matter",
                            lambda matter, **kw: (dict(matter), {}))

        async def fake_query(*args, **kwargs):
            raise AssertionError("no request may leave after the gate fails")

        monkeypatch.setattr(panel, "query_model", fake_query)

        matter = self._matter()
        matter["gstin"] = ""
        matter["defects"][0]["heading"] = \
            "Excess ITC availed by Acme Industries Private Limited"
        matter["defects"][0]["department_contention"] = ""

        events = []
        async for event in panel.run_panel_stream(
                matter, tier_name="draft", skip_verification=True):
            events.append(event)

        assert events[0]["type"] == "error"
        assert "CLIENT_NAME" in events[0]["message"]


# ---------------------------------------------------------------------------
# Citations embedded in filed prose
# ---------------------------------------------------------------------------


class TestFiledTextBlockers:
    """A citation inside a filed paragraph cannot be withheld the way a table
    entry is — it must surface as a blocker the reviewer resolves by hand."""

    def test_unverified_prose_citation_becomes_a_blocker(self):
        verification = {"authorities": [
            {"citation": "Bogus Traders v. State of Karnataka",
             "source": "filed_text", "status": "NOT_FOUND",
             "defect_index": 2, "defect_heading": "Blocked credit"},
            {"citation": "Section 73(10)", "source": "defect",
             "status": "UNVERIFIED"},
            {"citation": "Circular No. 172/04/2022-GST",
             "source": "filed_text", "status": "VERIFIED"},
        ]}
        blockers = panel.filed_text_blockers(verification)
        assert len(blockers) == 1
        assert "Bogus Traders v. State of Karnataka" in blockers[0]
        assert "defect 2" in blockers[0]

    def test_a_verified_prose_citation_raises_nothing(self):
        verification = {"authorities": [
            {"citation": "Circular No. 172/04/2022-GST",
             "source": "filed_text", "status": "VERIFIED"},
        ]}
        assert panel.filed_text_blockers(verification) == []

    async def test_the_stream_records_prose_blockers_on_the_determination(
            self, monkeypatch):
        from backend import config
        monkeypatch.setattr(config, "PANEL_WEB_GROUNDING", False)

        async def fake_query(model, messages, **kwargs):
            return {"ok": True, "content": '{"defects": []}', "usage": None,
                    "model": model}

        async def fake_verify(determination, pack, verifier):
            return {
                "checked": True,
                "authorities": [
                    {"citation": "Bogus Traders v. State of Karnataka",
                     "source": "filed_text", "status": "NOT_FOUND",
                     "defect_index": 1, "defect_heading": "Excess ITC"},
                ],
                "summary": {"verified": 0, "superseded": 0, "unverified": 0,
                            "not_found": 1, "total": 1},
            }, []

        monkeypatch.setattr(panel, "query_model", fake_query)
        monkeypatch.setattr(panel, "verify_authorities", fake_verify)

        summary = None
        async for event in panel.run_panel_stream(
                {"issues": "ITC mismatch", "facts": "None.",
                 "notice_type": "ASMT-10"},
                tier_name="pro"):
            if event["type"] == "summary":
                summary = event

        blockers = summary["data"]["determination"]["filing_blockers"]
        assert any("Bogus Traders" in b for b in blockers)
