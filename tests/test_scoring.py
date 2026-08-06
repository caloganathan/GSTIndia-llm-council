"""Eval scoring tests.

The scorer's job is to be a reliable regression signal. If it can be fooled by
a bad determination, prompt changes get graded wrongly and the whole loop is
worthless.
"""

from evals.scoring import (
    aggregate,
    score_defects,
    score_evidence_gaps,
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
        "defects": [
            {"index": 1, "heading": "ITC mismatch",
             "our_position": "s.16(2) satisfied"},
            {"index": 2, "heading": "Interest",
             "submission": "Interest under section 50 is payable on the net liability."},
        ],
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
            "recommended_position": "x", "preliminary_submissions": "y",
            "defects": [{"index": 1, "heading": "z"}], "working_note": "w",
        })
        assert result["passed"] is True

    def test_degraded_output_fails(self):
        result = score_determination_integrity({
            "recommended_position": "x", "preliminary_submissions": "y",
            "defects": [{"index": 1, "heading": "z"}], "working_note": "w",
            "_degraded": True,
        })
        assert result["passed"] is False

    def test_missing_fields_reported(self):
        result = score_determination_integrity({"recommended_position": "x"})
        assert "preliminary_submissions" in result["missing"]
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
                "preliminary_submissions": "The ITC mismatch is explained.",
                "defects": [{"index": 1, "heading": "ITC mismatch"}],
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
                                   "preliminary_submissions": "d", "defects": [{"index": 1, "heading": "x"}],
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
                                   "preliminary_submissions": "d", "defects": [], "working_note": "w"},
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
                              "preliminary_submissions": "d", "defects": [{"index": 1, "heading": "x"}],
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
            "determination": {"recommended_position": "x", "preliminary_submissions": "d",
                              "defects": [{"index": 1, "heading": "y"}],
                              "working_note": "w"},
            "analyses": [], "cross_exams": [],
            "verification": {
                "summary": {"verified": 0, "superseded": 1, "unverified": 0,
                            "not_found": 0, "total": 1},
                "authorities": [{"citation": "Circular 183", "status": "SUPERSEDED"}],
            },
        }
        summary = aggregate([score_matter(golden, result, {"usage": {}})])
        assert summary["superseded_citations"] == [("g1", "Circular 183")]


class TestDefectScoring:
    """
    Scored against the department's own disposal of each limb — the only
    ground truth this work has.
    """

    EXPECTED = [
        {"index": 1, "heading_contains": "Short payment", "posture": "explained"},
        {"index": 2, "heading_contains": "Ineligible ITC", "posture": "partial"},
        {"index": 3, "heading_contains": "late fee", "posture": "agreed_paid"},
    ]

    def test_all_limbs_found_and_postured(self):
        result = score_defects({"defects": [
            {"index": 1, "heading": "Short payment of tax", "posture": "explained"},
            {"index": 2, "heading": "Ineligible ITC", "posture": "partial"},
            {"index": 3, "heading": "GSTR-1 late fee", "posture": "agreed_paid"},
        ]}, self.EXPECTED)
        assert result["found"] == 3
        assert result["posture_matches"] == 3
        assert result["passed"] is True

    def test_a_missing_limb_fails_the_matter(self):
        """An unanswered limb is confirmed unopposed. That is not a near miss."""
        result = score_defects({"defects": [
            {"index": 1, "heading": "Short payment of tax", "posture": "explained"},
        ]}, self.EXPECTED)
        assert result["passed"] is False
        assert len(result["missed"]) == 2

    def test_wrong_posture_is_reported_but_does_not_fail(self):
        """A reviewer can correct a posture; they cannot correct an absence."""
        result = score_defects({"defects": [
            {"index": 1, "heading": "Short payment", "posture": "contested"},
            {"index": 2, "heading": "Ineligible ITC", "posture": "partial"},
            {"index": 3, "heading": "late fee", "posture": "agreed_paid"},
        ]}, self.EXPECTED)
        assert result["passed"] is True
        assert result["posture_errors"][0]["expected"] == "explained"
        assert result["posture_errors"][0]["got"] == "contested"

    def test_matches_on_heading_when_numbering_differs(self):
        result = score_defects({"defects": [
            {"index": 99, "heading": "Short payment of tax on outward supplies",
             "posture": "explained"},
        ]}, [self.EXPECTED[0]])
        assert result["found"] == 1

    def test_no_golden_defects_is_not_a_failure(self):
        assert score_defects({"defects": []}, [])["passed"] is None


class TestEvidenceGapScoring:
    """
    The sharpest signal on the scorecard. It is measured against a limb that
    was actually lost — argued correctly, and lost anyway because one system
    report was not attached.
    """

    EXPECTED = [{
        "index": 7,
        "heading_contains": "E-invoicing",
        "required_evidence_that_was_missing": [
            "IRP portal data report for tax period 08/2023 — the first month "
            "of mandatory applicability — listing every B2B invoice with its "
            "IRN and status"
        ],
    }]

    def test_caught_when_demanded_in_the_evidence_list(self):
        result = score_evidence_gaps({"defects": [{
            "index": 7,
            "evidence_required": [
                "IRP portal data report for 08/2023 showing IRN status for "
                "every B2B invoice"
            ],
        }]}, self.EXPECTED)
        assert result["found"] == 1
        assert result["passed"] is True

    def test_caught_when_flagged_as_a_gap(self):
        result = score_evidence_gaps({"defects": [{
            "index": 7,
            "evidence_gap": ["IRP portal report, 08/2023, IRN per B2B invoice"],
        }]}, self.EXPECTED)
        assert result["passed"] is True

    def test_a_good_argument_without_the_document_fails(self):
        """This is exactly what happened in the golden matter."""
        result = score_evidence_gaps({"defects": [{
            "index": 7,
            "evidence_required": ["GSTR-9C for FY 2022-23 showing turnover"],
            "submission": "The mandate applied only from 01.08.2023.",
        }]}, self.EXPECTED)
        assert result["passed"] is False
        assert "IRP portal" in result["missed"][0]["document"]

    def test_nothing_to_score_when_the_golden_case_records_no_loss(self):
        assert score_evidence_gaps({"defects": []}, [{"index": 1}])["passed"] is None


class TestScorecardSurfacesWhatItScores:
    """
    A metric that is computed but never printed cannot do its job.

    `defect_coverage` and `evidence_gap_catch` are the two numbers this
    product is judged on, and `aggregate()` computed both correctly while the
    scorecard showed neither — so a regression in either could ship without
    anyone seeing a changed number. These assert the report renders them.
    """

    MATTER = {
        "id": "gst-001",
        "description": "reference matter",
        "passed": False,
        "usage": {"total_cost": 0.01},
        "scores": {
            "citations": {"verified": 1, "unverified": 0, "not_found": 0,
                          "superseded": 0, "verified_rate": 1.0,
                          "fabricated": [], "stale": [], "passed": True},
            "issues": {"expected": 1, "found": 1, "rate": 1.0, "missed": [],
                       "passed": True},
            "procedural": {"expected": 1, "found": 1, "rate": 1.0, "missed": [],
                           "raised_but_dropped": [], "passed": True},
            "position": {"expected_position": "contest",
                         "inferred_position": "contest", "agrees": True,
                         "violations": [], "passed": True},
            "integrity": {"confidence": "defensible", "passed": True},
            "defects": {"expected": 8, "found": 7, "posture_matches": 6,
                        "rate": 0.875, "posture_rate": 0.75,
                        "missed": ["E-invoicing"],
                        "posture_errors": [{"defect": "Late fee",
                                            "expected": "agreed_paid",
                                            "got": "contested"}],
                        "passed": False},
            "evidence": {"expected": 1, "found": 0, "rate": 0.0,
                         "missed": [{"defect": "E-invoicing",
                                     "document": "first e-invoice for August 2023"}],
                         "passed": False},
        },
    }

    def _scorecard(self, tmp_path):
        from evals.run import write_scorecard
        summary = aggregate([self.MATTER])
        out = tmp_path / "scorecard.md"
        write_scorecard(out, summary, [self.MATTER], "draft")
        return out.read_text()

    def test_the_two_headline_metrics_appear(self, tmp_path):
        text = self._scorecard(tmp_path)
        assert "Defect coverage" in text
        assert "Evidence gap catch" in text

    def test_a_missed_limb_is_named(self, tmp_path):
        assert "E-invoicing" in self._scorecard(tmp_path)

    def test_a_document_never_demanded_is_called_out(self, tmp_path):
        text = self._scorecard(tmp_path)
        assert "CRITICAL EVIDENCE NOT DEMANDED" in text
        assert "first e-invoice for August 2023" in text

    def test_a_wrong_posture_is_named_with_both_sides(self, tmp_path):
        text = self._scorecard(tmp_path)
        assert "Late fee" in text
        assert "agreed_paid" in text


class TestTheScorerCannotReportFalseComfort:
    """
    Three ways this scorer used to score an absence of evidence as a pass.
    Each one made a prompt regression invisible, which is worse than a scorer
    that is merely crude — a crude signal is discounted, a false green is
    acted on.
    """

    def test_an_unreadable_position_is_unscorable_not_agreement(self):
        """
        `infer_position` returned "mixed" when it found NO marker of either
        kind, and `score_position` treats "mixed" as agreement — so a
        determination reading like a covering letter scored 100% against
        whatever position the golden case recorded.
        """
        determination = {
            "recommended_position": "File a detailed reply within the time "
                                    "allowed and place the records before the "
                                    "officer.",
            "lead_argument": "",
        }
        assert infer_position(determination) is None

        scored = score_position(determination, {"position_taken": "concede"})
        assert scored["agrees"] is None, (
            "an unreadable position must be excluded from the metric, not "
            "counted as agreeing with the golden case"
        )

    def test_a_genuine_tie_is_still_mixed(self):
        """The fix must not swallow a real tie, which is a different state
        from 'no markers at all'."""
        determination = {
            "recommended_position": "We contest the ITC limb and concede the "
                                    "late fee limb.",
            "lead_argument": "",
        }
        assert infer_position(determination) == "mixed"

    def test_citation_integrity_is_unscorable_when_nothing_was_checked(self):
        """
        `passed` was True on an empty verification: no fabricated citations
        found, because none were looked for. Same failure direction as
        `export._is_filable`, which files nothing when the index is empty.
        """
        result = score_citation_integrity({
            "summary": {"verified": 0, "unverified": 0, "not_found": 0,
                        "total": 0},
            "authorities": [],
        })
        assert result["passed"] is None
        assert result["verified_rate"] is None

    def test_evidence_gap_catch_survives_a_renumbered_limb(self):
        """
        `score_defects` had an index-or-heading fallback and
        `score_evidence_gaps` did not, so a chairman that renumbered the limb
        scored as found for coverage and as a FALSE ZERO for the sharpest
        number on the scorecard — a failure reported on a document that had
        actually been demanded.
        """
        expected = [{
            "index": 7,
            "heading_contains": "E-invoicing",
            "posture": "contested",
            "required_evidence_that_was_missing": [
                "IRP portal data report for tax period 08/2023 listing every "
                "B2B invoice with its IRN and status"
            ],
        }]
        # Same limb, renumbered 7 -> 1 by the chairman.
        determination = {"defects": [{
            "index": 1,
            "heading": "E-invoicing non-compliance under Rule 48(4)",
            "posture": "contested",
            "evidence_required": [
                "IRP portal data report for 08/2023 with the IRN and status "
                "of every B2B invoice"
            ],
        }]}

        coverage = score_defects(determination, expected)
        gaps = score_evidence_gaps(determination, expected)

        assert coverage["passed"] is True, "coverage already had the fallback"
        assert gaps["found"] == 1
        assert gaps["passed"] is True, (
            "the gap scorer must resolve the limb the same way the coverage "
            "scorer does, or the two disagree about which limb is which"
        )

    def test_a_genuinely_missing_limb_still_fails_both(self):
        """The fallback must not make everything match."""
        expected = [{
            "index": 7,
            "heading_contains": "E-invoicing",
            "required_evidence_that_was_missing": ["IRP portal data report"],
        }]
        determination = {"defects": [{
            "index": 1,
            "heading": "Excess input tax credit against GSTR-2B",
            "evidence_required": ["Month-wise GSTR-2B"],
        }]}
        assert score_defects(determination, expected)["passed"] is False
        assert score_evidence_gaps(determination, expected)["passed"] is False
