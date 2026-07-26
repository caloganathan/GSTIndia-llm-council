"""Eval scoring tests.

The scorer's job is to be a reliable regression signal. If it can be fooled by
a bad determination, prompt changes get graded wrongly and the whole loop is
worthless.
"""

from evals.scoring import (
    aggregate,
    infer_position,
    score_citation_integrity,
    score_determination_integrity,
    score_issue_coverage,
    score_matter,
    score_position,
    score_procedural_catch,
)


class TestCitationIntegrity:
    def test_clean_run_passes(self):
        result = score_citation_integrity({
            "summary": {"verified": 3, "unverified": 1, "not_found": 0, "total": 4},
            "authorities": [],
        })
        assert result["passed"] is True
        assert result["verified_rate"] == 0.75

    def test_single_fabrication_fails_the_matter(self):
        result = score_citation_integrity({
            "summary": {"verified": 9, "unverified": 0, "not_found": 1, "total": 10},
            "authorities": [{"citation": "(2029) 99 GSTL 999", "status": "NOT_FOUND"}],
        })
        assert result["passed"] is False
        assert result["fabricated"] == ["(2029) 99 GSTL 999"]

    def test_no_authorities(self):
        result = score_citation_integrity({})
        assert result["total"] == 0
        assert result["verified_rate"] is None


class TestIssueCoverage:
    DETERMINATION = {
        "recommended_position": "Contest the ITC mismatch.",
        "issues": [{"issue": "ITC mismatch", "our_position": "s.16(2) satisfied"}],
        "draft_reply": "Interest under section 50 is payable on the net liability.",
    }

    def test_all_issues_found(self):
        result = score_issue_coverage(
            self.DETERMINATION, ["ITC mismatch", "interest under section 50"]
        )
        assert result["rate"] == 1.0
        assert result["passed"] is True

    def test_missed_issue_reported(self):
        result = score_issue_coverage(
            self.DETERMINATION, ["ITC mismatch", "place of supply"]
        )
        assert result["missed"] == ["place of supply"]
        assert result["passed"] is False

    def test_case_insensitive(self):
        assert score_issue_coverage(self.DETERMINATION, ["itc MISMATCH"])["rate"] == 1.0

    def test_no_expectations_is_unscored(self):
        result = score_issue_coverage(self.DETERMINATION, [])
        assert result["passed"] is None


class TestProceduralCatch:
    ANALYSES = [
        {"key": "procedural",
         "analysis": "Limitation under section 73(10) expired on 31.12.2023. "
                     "Jurisdiction of the proper officer is also in question."},
        {"key": "revenue", "analysis": "The department's case is strong."},
    ]

    def test_found_in_chairman_and_counsel(self):
        determination = {"lead_argument": "The notice is barred by limitation."}
        result = score_procedural_catch(determination, self.ANALYSES, ["limitation"])
        assert result["passed"] is True

    def test_raised_by_counsel_but_dropped_by_chairman(self):
        """A distinct failure from never raising it — and worth surfacing."""
        determination = {"lead_argument": "We contest on merits."}
        result = score_procedural_catch(
            determination, self.ANALYSES, ["jurisdiction"]
        )
        assert "jurisdiction" in result["raised_but_dropped"]
        assert result["passed"] is True  # it was found, just not carried

    def test_never_raised_fails(self):
        result = score_procedural_catch({}, self.ANALYSES, ["natural justice"])
        assert result["missed"] == ["natural justice"]
        assert result["passed"] is False

    def test_only_procedural_counsel_text_is_searched(self):
        analyses = [{"key": "revenue", "analysis": "limitation is not an issue"}]
        result = score_procedural_catch({}, analyses, ["limitation"])
        assert result["passed"] is False


class TestPosition:
    def test_infers_contest(self):
        assert infer_position({
            "recommended_position": "Contest the notice and resist the demand."
        }) == "contest"

    def test_infers_concede(self):
        assert infer_position({
            "recommended_position": "Concede and settle via voluntary payment."
        }) == "concede"

    def test_empty_is_none(self):
        assert infer_position({"recommended_position": ""}) is None

    def test_agreement_with_expectation(self):
        result = score_position(
            {"recommended_position": "Contest on limitation.",
             "lead_argument": "Time-barred under section 73."},
            {"position_taken": "contest",
             "position_keywords": ["limitation", "time-barred"]},
        )
        assert result["agrees"] is True
        assert result["keyword_rate"] == 1.0
        assert result["passed"] is True

    def test_disagreement_fails(self):
        result = score_position(
            {"recommended_position": "Concede the demand and settle."},
            {"position_taken": "contest"},
        )
        assert result["agrees"] is False
        assert result["passed"] is False

    def test_forbidden_phrase_fails_even_when_position_agrees(self):
        result = score_position(
            {"recommended_position": "Contest, but concede the entire demand first."},
            {"position_taken": "contest", "must_not_say": ["concede the entire demand"]},
        )
        assert result["violations"] == ["concede the entire demand"]
        assert result["passed"] is False


class TestDeterminationIntegrity:
    def test_complete_determination_passes(self):
        result = score_determination_integrity({
            "recommended_position": "x", "draft_reply": "y",
            "issues": [{"issue": "z"}], "working_note": "w",
        })
        assert result["passed"] is True

    def test_degraded_output_fails(self):
        result = score_determination_integrity({
            "recommended_position": "x", "draft_reply": "y",
            "issues": [{"issue": "z"}], "working_note": "w", "_degraded": True,
        })
        assert result["passed"] is False

    def test_missing_fields_reported(self):
        result = score_determination_integrity({"recommended_position": "x"})
        assert "draft_reply" in result["missing"]
        assert result["passed"] is False


class TestScoreMatter:
    GOLDEN = {
        "id": "gst-001",
        "expected": {
            "position_taken": "contest",
            "issues_expected": ["ITC mismatch"],
            "procedural_points": ["limitation"],
        },
    }

    def _result(self, fabricated=False):
        return {
            "determination": {
                "recommended_position": "Contest on limitation.",
                "lead_argument": "Time-barred.",
                "draft_reply": "The ITC mismatch is explained.",
                "issues": [{"issue": "ITC mismatch"}],
                "working_note": "Reasoning.",
            },
            "analyses": [{"key": "procedural", "analysis": "limitation expired"}],
            "cross_exams": [],
            "verification": {
                "summary": {"verified": 1, "unverified": 0,
                            "not_found": 1 if fabricated else 0,
                            "total": 2 if fabricated else 1},
                "authorities": ([{"citation": "fake", "status": "NOT_FOUND"}]
                                if fabricated else []),
            },
        }

    def test_good_matter_passes(self):
        scored = score_matter(self.GOLDEN, self._result(), {"usage": {"total_cost": 0.2}})
        assert scored["passed"] is True

    def test_fabrication_fails_the_whole_matter(self):
        scored = score_matter(
            self.GOLDEN, self._result(fabricated=True), {"usage": {"total_cost": 0.2}}
        )
        assert scored["passed"] is False


class TestAggregate:
    def test_rolls_up_and_collects_fabrications(self):
        scores = [
            score_matter(
                {"id": "a", "expected": {"issues_expected": ["x"]}},
                {"determination": {"recommended_position": "x is contested",
                                   "draft_reply": "d", "issues": [{"issue": "x"}],
                                   "working_note": "w"},
                 "analyses": [], "cross_exams": [],
                 "verification": {"summary": {"verified": 1, "unverified": 0,
                                              "not_found": 0, "total": 1},
                                  "authorities": []}},
                {"usage": {"total_cost": 0.1}},
            ),
            score_matter(
                {"id": "b", "expected": {"issues_expected": ["y"]}},
                {"determination": {"recommended_position": "unrelated",
                                   "draft_reply": "d", "issues": [], "working_note": "w"},
                 "analyses": [], "cross_exams": [],
                 "verification": {"summary": {"verified": 0, "unverified": 0,
                                              "not_found": 1, "total": 1},
                                  "authorities": [{"citation": "fake",
                                                   "status": "NOT_FOUND"}]}},
                {"usage": {"total_cost": 0.3}},
            ),
        ]
        summary = aggregate(scores)
        assert summary["matters"] == 2
        assert summary["passed"] == 1
        assert summary["pass_rate"] == 0.5
        assert summary["fabricated_citations"] == [("b", "fake")]
        assert summary["cost_per_matter"] == 0.2

    def test_empty(self):
        assert aggregate([]) == {}


class TestSupersededFailsAMatter:
    """
    Symmetry with fabrication. A superseded authority is arguably worse: it
    survives a naive existence check, so nothing downstream stops it.
    """

    def test_superseded_fails_citation_integrity(self):
        result = score_citation_integrity({
            "summary": {"verified": 4, "superseded": 1, "unverified": 0,
                        "not_found": 0, "total": 5},
            "authorities": [{"citation": "Circular 183", "status": "SUPERSEDED"}],
        })
        assert result["passed"] is False
        assert result["stale"] == ["Circular 183"]

    def test_clean_run_still_passes(self):
        result = score_citation_integrity({
            "summary": {"verified": 5, "superseded": 0, "unverified": 0,
                        "not_found": 0, "total": 5},
            "authorities": [],
        })
        assert result["passed"] is True

    def test_superseded_fails_the_whole_matter(self):
        golden = {"id": "g1", "expected": {"issues_expected": ["x"]}}
        result = {
            "determination": {"recommended_position": "contest x",
                              "draft_reply": "d", "issues": [{"issue": "x"}],
                              "working_note": "w"},
            "analyses": [], "cross_exams": [],
            "verification": {
                "summary": {"verified": 1, "superseded": 1, "unverified": 0,
                            "not_found": 0, "total": 2},
                "authorities": [{"citation": "stale one", "status": "SUPERSEDED"}],
            },
        }
        assert score_matter(golden, result, {"usage": {}})["passed"] is False

    def test_aggregate_surfaces_stale_citations(self):
        golden = {"id": "g1", "expected": {}}
        result = {
            "determination": {"recommended_position": "x", "draft_reply": "d",
                              "issues": [{"issue": "y"}], "working_note": "w"},
            "analyses": [], "cross_exams": [],
            "verification": {
                "summary": {"verified": 0, "superseded": 1, "unverified": 0,
                            "not_found": 0, "total": 1},
                "authorities": [{"citation": "Circular 183", "status": "SUPERSEDED"}],
            },
        }
        summary = aggregate([score_matter(golden, result, {"usage": {}})])
        assert summary["superseded_citations"] == [("g1", "Circular 183")]
