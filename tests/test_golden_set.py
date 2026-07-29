"""The golden set, scored on everything that does not need a model.

WHY THIS FILE EXISTS SEPARATELY FROM `evals/run.py`
---------------------------------------------------
`evals/run.py` runs the panel and costs real money, so it cannot run on every
push. But two of the things it measures do not need a model at all:

- **Segmentation.** Whether the eight limbs of a notice are found is decided by
  `defects.segment()` in Python. A limb that does not segment is never
  answered, and an unanswered limb is confirmed unopposed — so this is the
  highest-consequence failure in the product and it is free to test.
- **Figure reading.** Whether each limb's head-wise amount is read correctly
  off the annexure is decided by `notice_tables`, also in Python, and also
  free to test.

Both were silently broken when this file was written. Segmentation missed the
most common defect in Indian GST practice because the catalogue pattern
required "excess" and "ITC" adjacent; figure reading returned Rs. 42,152 for a
limb the annexure put at Rs. 84,300, because two digits from the phrase
"GSTR-1" were read as head amounts and their sum landed inside the rounding
tolerance. Neither would have been caught by the paid harness, because nobody
runs the paid harness on every change.

So the golden set earns its keep in CI, and the paid run measures what only a
model can be measured on.
"""

import json
from pathlib import Path

import pytest

from backend import defects, intake
from backend.domains import get_pack

GOLDEN_DIR = Path(__file__).resolve().parent.parent / "evals" / "golden"


def _load():
    cases = []
    for path in sorted(GOLDEN_DIR.glob("*.json")):
        cases.append((path.name, json.loads(path.read_text())))
    return cases


GOLDEN = _load()
WITH_TEXT = [(name, case) for name, case in GOLDEN if case.get("notice_text")]

pytestmark = pytest.mark.skipif(not GOLDEN, reason="no golden set committed")


class TestTheSetIsWellFormed:
    @pytest.mark.parametrize("name,case", GOLDEN, ids=[n for n, _ in GOLDEN])
    def test_required_blocks_are_present(self, name, case):
        assert case.get("id"), f"{name}: no id"
        assert case.get("intake"), f"{name}: no intake block"
        assert case.get("expected"), f"{name}: no expected block"
        assert case.get("expected_defects"), f"{name}: no expected_defects"

    @pytest.mark.parametrize("name,case", GOLDEN, ids=[n for n, _ in GOLDEN])
    def test_ids_match_filenames(self, name, case):
        assert case["id"] == name[:-len(".json")]

    @pytest.mark.parametrize("name,case", GOLDEN, ids=[n for n, _ in GOLDEN])
    def test_every_case_is_marked_synthetic(self, name, case):
        # These ship in a public repository. A golden case built from a real
        # client matter must never be committed, and the flag plus provenance
        # note is what keeps that decision visible rather than assumed.
        assert case.get("synthetic") is True, f"{name}: not marked synthetic"
        assert case.get("provenance"), f"{name}: no provenance note"

    @pytest.mark.parametrize("name,case", GOLDEN, ids=[n for n, _ in GOLDEN])
    def test_expected_postures_are_real_postures(self, name, case):
        for expected in case["expected_defects"]:
            posture = expected.get("posture")
            if posture:
                assert posture in defects.POSTURES, \
                    f"{name}: '{posture}' is not a posture"

    @pytest.mark.parametrize("name,case", GOLDEN, ids=[n for n, _ in GOLDEN])
    def test_defect_types_are_in_the_catalogue(self, name, case):
        pack = get_pack("gst")
        known = {d.key for d in pack.DEFECT_TYPES}
        for defect in case["intake"].get("defects") or []:
            assert defect["type"] in known, \
                f"{name}: unknown defect type '{defect['type']}'"

    @pytest.mark.parametrize("name,case", GOLDEN, ids=[n for n, _ in GOLDEN])
    def test_notice_type_is_in_the_registry(self, name, case):
        pack = get_pack("gst")
        notice_type = case["intake"].get("notice_type")
        assert notice_type in pack.NOTICE_TYPES, \
            f"{name}: '{notice_type}' is not a known form"

    @pytest.mark.parametrize("name,case", GOLDEN, ids=[n for n, _ in GOLDEN])
    def test_expected_defects_line_up_with_the_intake_limbs(self, name, case):
        intake_indices = {d["index"] for d in case["intake"].get("defects") or []}
        for expected in case["expected_defects"]:
            assert expected["index"] in intake_indices, \
                f"{name}: expected defect {expected['index']} has no intake limb"

    def test_the_set_covers_a_spread_of_forms(self):
        forms = {case["intake"]["notice_type"] for _, case in GOLDEN}
        # A set that is eight variations of ASMT-10 measures one code path.
        assert len(forms) >= 6, f"only {len(forms)} distinct forms: {forms}"

    def test_at_least_one_case_scores_the_evidence_gap(self):
        # `evidence_gap_catch` is the number that matters most in the whole
        # scorecard. A set where no case names a missing document cannot
        # produce it.
        targets = [
            item
            for _, case in GOLDEN
            for expected in case["expected_defects"]
            for item in (expected.get("required_evidence_that_was_missing") or [])
        ]
        assert len(targets) >= 5

    def test_the_set_includes_a_matter_that_should_be_conceded(self):
        # Conceding is a positive recommendation, and a golden set of matters
        # that are all winnable trains the panel in the wrong direction.
        positions = {case["expected"].get("position_taken") for _, case in GOLDEN}
        assert "concede" in positions


class TestSegmentation:
    """
    Does the notice break into the limbs it will be decided in?

    Scored per case rather than in aggregate: a set average of 90% hides one
    notice that segmented at 50%, and that notice is a reply with holes in it.
    """

    @pytest.mark.parametrize("name,case", WITH_TEXT,
                             ids=[n for n, _ in WITH_TEXT])
    def test_every_limb_is_found(self, name, case):
        pack = get_pack("gst")
        found = defects.segment(case["notice_text"], pack.DEFECT_TYPES)
        expected = case["intake"]["defects"]

        found_types = [d["type"] for d in found]
        missing = [d["type"] for d in expected if d["type"] not in found_types]

        assert not missing, (
            f"{name}: {len(missing)} limb(s) did not segment: {missing}. "
            f"An unsegmented limb is never answered, and an unanswered limb "
            f"is confirmed unopposed."
        )

    @pytest.mark.parametrize("name,case", WITH_TEXT,
                             ids=[n for n, _ in WITH_TEXT])
    def test_limb_count_matches(self, name, case):
        pack = get_pack("gst")
        found = defects.segment(case["notice_text"], pack.DEFECT_TYPES)
        assert len(found) == len(case["intake"]["defects"]), (
            f"{name}: segmented {len(found)} limbs, expected "
            f"{len(case['intake']['defects'])}"
        )


class TestFigureReading:
    """
    Are the department's own figures read back correctly?

    A reply that restates the department's figures wrongly is worse than one
    that does not restate them at all.
    """

    @pytest.mark.parametrize("name,case", WITH_TEXT,
                             ids=[n for n, _ in WITH_TEXT])
    def test_head_wise_amounts_match_the_annexure(self, name, case):
        pack = get_pack("gst")
        found = intake.extract_defects(case["notice_text"], pack)
        # Keyed by index, not by type. A notice can raise two limbs of the
        # same type — an RFD-08 routinely objects to a refund on two separate
        # grounds — and keying by type silently collapses them.
        expected_by_index = {
            d["index"]: sum((d.get("amount_by_head") or {}).values())
            for d in case["intake"]["defects"]
        }

        errors = []
        for defect in found:
            want = expected_by_index.get(defect["index"])
            if want is None or want == 0:
                continue
            label = f"limb {defect['index']} ({defect['type']})"
            if defect.get("amount_unread"):
                errors.append(f"{label}: unread (expected {want})")
                continue
            got = sum((defect.get("amount_by_head") or {}).values())
            if abs(got - want) > 1.0:
                errors.append(f"{label}: read {got}, expected {want}")

        assert not errors, f"{name}: " + "; ".join(errors)

    @pytest.mark.parametrize("name,case", WITH_TEXT,
                             ids=[n for n, _ in WITH_TEXT])
    def test_limb_totals_reconcile_to_the_notice_total(self, name, case):
        """
        The whole-notice checksum.

        The department prints a total for the notice and a figure for each
        limb, and they must agree. A run where they do not means a limb has
        absorbed a neighbour's figure — the failure that once read a Rs. 44
        interest limb as Rs. 1.24 crore.
        """
        declared = case["intake"].get("amount_disputed")
        if not declared:
            pytest.skip("no notice-level total to reconcile against")

        pack = get_pack("gst")
        found = intake.extract_defects(case["notice_text"], pack)
        if any(d.get("amount_unread") for d in found):
            pytest.skip("a limb was correctly reported unread")

        total = sum(
            sum((d.get("amount_by_head") or {}).values()) for d in found
        )
        assert abs(total - declared) <= 2.0, (
            f"{name}: limbs total {total:,.2f} against a notice total of "
            f"{declared:,.2f}"
        )


class TestNoticeFieldExtraction:
    """The identifiers a reply is rejected on its face for getting wrong."""

    @pytest.mark.parametrize("name,case", WITH_TEXT,
                             ids=[n for n, _ in WITH_TEXT])
    def test_key_fields_are_read_off_the_notice(self, name, case):
        pack = get_pack("gst")
        result = intake.extract_fields_local(case["notice_text"], pack)
        fields = result["fields"]
        expected = case["intake"]

        for key in ("gstin", "notice_type", "state"):
            if expected.get(key):
                assert fields.get(key) == expected[key], (
                    f"{name}: {key} read as {fields.get(key)!r}, "
                    f"expected {expected[key]!r}"
                )

    @pytest.mark.parametrize("name,case", WITH_TEXT,
                             ids=[n for n, _ in WITH_TEXT])
    def test_the_reply_deadline_is_read(self, name, case):
        pack = get_pack("gst")
        fields = intake.extract_fields_local(case["notice_text"], pack)["fields"]
        if case["intake"].get("due_date"):
            assert fields.get("due_date") == case["intake"]["due_date"], (
                f"{name}: a missed reply date is how a matter becomes an appeal"
            )

    @pytest.mark.parametrize("name,case", WITH_TEXT,
                             ids=[n for n, _ in WITH_TEXT])
    def test_extracted_fields_carry_a_snippet_to_check_against(self, name, case):
        pack = get_pack("gst")
        result = intake.extract_fields_local(case["notice_text"], pack)
        for key in ("gstin", "notice_type"):
            if result["fields"].get(key):
                assert key in result["snippets"], \
                    f"{name}: {key} has no source snippet for the reviewer"
