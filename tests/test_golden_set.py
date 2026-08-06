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
import re
from pathlib import Path

import pytest

from backend import defects, intake
from backend.domains import get_pack


def _normalise(text: str) -> str:
    """Same normalisation the scorers use, so a fragment asserted here is a
    fragment that will match there."""
    return re.sub(r"\s+", " ", (text or "").lower())

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
    def test_every_expected_defect_carries_a_heading_fragment(self, name, case):
        """
        `heading_contains` is what lets the scorers find a limb the chairman
        renumbered. Every entry was `null` once, which left `defect_coverage`
        and `evidence_gap_catch` wholly dependent on the panel preserving the
        department's numbering, and printed bare integers instead of limb
        names in the scorecard's MISSED line.
        """
        for expected in case["expected_defects"]:
            fragment = expected.get("heading_contains")
            assert fragment and str(fragment).strip(), (
                f"{name}: expected defect {expected.get('index')} has no "
                "heading_contains fragment"
            )

    @pytest.mark.parametrize("name,case", WITH_TEXT, ids=[n for n, _ in WITH_TEXT])
    def test_heading_fragments_resolve_to_exactly_one_limb(self, name, case):
        """A fragment that matches nothing is dead; one that matches two limbs
        would silently score the wrong limb."""
        pack = get_pack("gst")
        found = intake.extract_defects(case["notice_text"], pack)
        headings = {d["index"]: d.get("heading", "") for d in found}
        for expected in case["expected_defects"]:
            fragment = _normalise(expected["heading_contains"])
            hits = [i for i, h in headings.items() if fragment in _normalise(h)]
            assert len(hits) == 1, (
                f"{name}: heading_contains {expected['heading_contains']!r} "
                f"matched {len(hits)} limbs ({hits}), expected exactly one"
            )
            assert hits[0] == expected["index"], (
                f"{name}: heading_contains {expected['heading_contains']!r} "
                f"matched limb {hits[0]}, but the entry is indexed "
                f"{expected['index']}"
            )

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
            assert case.get("no_notice_total") is True, (
                f"{name}: no amount_disputed to reconcile against. If that is "
                "deliberate, mark the case \"no_notice_total\": true so the "
                "skip is a recorded decision rather than a silent gap."
            )
            pytest.skip("case is flagged as carrying no notice-level total")

        pack = get_pack("gst")
        found = intake.extract_defects(case["notice_text"], pack)

        # This test used to SKIP whenever any limb came back unread, which
        # meant an extraction regression removed the guard instead of tripping
        # it — the one check that needs no ground truth, disabled by exactly
        # the failure it exists to catch. Now each case declares how many
        # limbs are legitimately unread, and the limbs that WERE read must
        # still reconcile to the notice total net of them.
        unread = [d for d in found if d.get("amount_unread")]
        expected_unread = case.get("expected_unread_limbs", 0)
        assert len(unread) == expected_unread, (
            f"{name}: {len(unread)} limb(s) came back unread "
            f"(indices {[d.get('index') for d in unread]}), but the case "
            f"declares expected_unread_limbs={expected_unread}. Either "
            "extraction regressed, or update the case if this is intended."
        )

        total = sum(
            sum((d.get("amount_by_head") or {}).values()) for d in found
        )
        if unread:
            # With a limb unread the printed total cannot be met exactly. The
            # read limbs must still not EXCEED it — overshoot is the signature
            # of a limb absorbing a neighbour's figure, which is the failure
            # this checksum exists to catch.
            assert total <= declared + 2.0, (
                f"{name}: limbs read total {total:,.2f}, which exceeds the "
                f"notice total of {declared:,.2f} while "
                f"{len(unread)} limb(s) were unread — a limb has absorbed a "
                "figure belonging to another."
            )
            return

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


class TestEntityNameDoesNotSpanLines:
    """
    A notice prints the taxpayer and its address on consecutive lines. An
    entity pattern using `\\s+` crosses that newline and glues the first words
    of the address onto the client name.

    This is not cosmetic. The client name is printed on the letterhead of the
    filing document, and it is the string handed to the sanitiser to scrub on
    the anonymising tier — so a wrong name means the scrub is aimed at the
    wrong text. It also produced exactly the embedded control character that
    once broke the export download.
    """

    @pytest.mark.parametrize("name,case", WITH_TEXT,
                             ids=[n for n, _ in WITH_TEXT])
    def test_no_newline_survives_into_the_client_name(self, name, case):
        extracted = intake.find_entity_name(case["notice_text"])
        assert extracted, f"{name}: no client name found at all"
        assert "\n" not in extracted, f"{name}: name spans a line break: {extracted!r}"
        assert "\r" not in extracted

    @pytest.mark.parametrize("name,case", WITH_TEXT,
                             ids=[n for n, _ in WITH_TEXT])
    def test_the_name_matches_the_expected_client(self, name, case):
        extracted = intake.find_entity_name(case["notice_text"])
        expected = case["intake"]["client_name"]
        assert extracted.upper() == expected.upper(), (
            f"{name}: read {extracted!r}, expected {expected!r}"
        )

    def test_an_address_line_beginning_with_a_capital_is_not_absorbed(self):
        # The failing shape: every word of the address line is capitalised, so
        # a newline-crossing pattern reads straight on into it.
        text = ("M/s. KAVERI AUTOCOMP PRIVATE LIMITED\n"
                "PLOT 42, PEENYA INDUSTRIAL AREA, BENGALURU - 560058\n")
        assert intake.find_entity_name(text) == "KAVERI AUTOCOMP PRIVATE LIMITED"

    def test_a_prefix_at_the_end_of_its_own_line_still_resolves(self):
        # The converse case: the form wraps after "M/s." and the name follows
        # on the next line. One newline between prefix and name is allowed.
        text = "M/s.\nPRAGATI POLYFABS PRIVATE LIMITED\nGIDC ESTATE, VATVA\n"
        assert intake.find_entity_name(text) == "PRAGATI POLYFABS PRIVATE LIMITED"

    def test_an_unprefixed_name_is_still_found_without_its_address(self):
        text = ("SHAKTI ENGINEERING WORKS PRIVATE LIMITED\n"
                "SITE IV INDUSTRIAL AREA, SAHIBABAD\n")
        assert intake.find_entity_name(text) == "SHAKTI ENGINEERING WORKS PRIVATE LIMITED"
