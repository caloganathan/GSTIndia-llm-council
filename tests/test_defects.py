"""Defect decomposition, triage and validation.

The fixtures in this file are reconstructed from a real Tamil Nadu ASMT-10
attachment for a GSTR-9C filer — the same layout, the same headings, the same
arithmetic — with the taxpayer's identifiers removed. That layout is the one
the product has to read correctly, and several of the tests below exist because
the first implementation read it wrongly.
"""

import pytest

from backend import defects, notice_tables
from backend.domains import gst

# A faithful reproduction of the departmental layout, including the two things
# that make it awkward: the first limb's table is emitted ABOVE its own bullet
# heading, and the detailed annexures follow the operative part.
NOTICE = """\
COMMERCIAL TAXES DEPARTMENT
GOVERNMENT OF TAMIL NADU
Attachment to ASMT-10 GSTR-9C Filers
Designation of the Proper Officer
Circle : RAM NAGAR
Financial Year 2023-24

S.No Return/ Statement Table SGST CGST IGST CESS Total
1 2 3 4 5 6
1 GSTR-9C 9P 4910302 4910302 2683829 0 12504433
2 GSTR-9 5N 4910302 4910302 2593830 0 12414434
6 Difference[(Highest of 1 to 4) - 5]
2
2
89999
0 90003

• Short payment of tax on outward supplies:
You are requested to pay the difference in the tax due paid through GSTR-3B.

• Difference in turnover:
S.No Return/Statement Table Turnover Reported
1 GSTR-9C 5P 69469079
3 GSTR-1 Total Aggregate turnover 68987531
5 Difference (Highest of 1 to 3)-4 481548
You are requested to reconcile the turnover.

• Excess claim of ITC availed w.r.t GSTR-2B:
S.No Description Table No. SGST CGST IGST CESS Total
8 Excess claim of ITC w.r.t GSTR-2A ((6+7)-3)
58366
58366
0
0 116732

• Claim of Ineligible ITC-Sec 17(5):
Scrutiny of your inward supplies reveals that you had claimed ITC under
section 17(5) which is ineligible.
3 Excess ITC claimed (1-2)
185446
185446
329
0 371221

• GSTR-1 late fee:
S.No No of GSTR-1 filed belatedly SGST late fee CGST late fee
1 2 3 4
1 2 1150 1150
Hence you are liable to payment of late fee as per section 47(1).

• Non-Compliance of E-invoicing:
As per Rule 48(4) of the TNGST/CGST Rules, 2017, every registered person
whose aggregate turnover exceeded the prescribed limit is required to
prepare tax invoices through the Invoice Registration Portal (IRP).
Hence it is proposed to levy penalty under section 125 of TNGST/CGST
Act, 2017 of Rs. 25000/- each under CGST and SGST.

For the above discrepancies, kindly substantiate the reasons in the reply.

GSTIN : 33AAAAA0000A1Z0 Name : SOME TAXPAYER PRIVATE LIMITED FY : 2023-24
Details of GSTR-01 Vs GSTR-3B
Total 4911335 4911335 2593830 0 12416500
"""


@pytest.fixture(scope="module")
def parsed():
    return defects.segment(NOTICE, gst.DEFECT_TYPES)


class TestSegmentation:
    def test_finds_every_limb(self, parsed):
        assert len(parsed) == 6

    def test_classifies_each_limb(self, parsed):
        assert [d["type"] for d in parsed] == [
            "outward_short_payment",
            "turnover_difference",
            "itc_excess_2b",
            "itc_blocked_17_5",
            "late_fee",
            "einvoice",
        ]

    def test_annexures_do_not_become_a_defect(self, parsed):
        """
        Without a boundary the last limb absorbs every annexure in the
        document, and its amount comes out orders of magnitude wrong — a
        Rs. 44 interest limb once reported Rs. 1.24 crore.
        """
        last = parsed[-1]["notice_extract"]
        assert "Details of GSTR-01 Vs GSTR-3B" not in last
        assert "12416500" not in last

    def test_department_numbering_is_authoritative_when_present(self):
        order = "Defect -1:\nOutput turnover discrepancies\n" \
                "• Short payment of tax on outward supplies:\nbody one\n" \
                "Defect -2:\n• Difference in turnover:\nbody two\n"
        found = defects.segment(order, gst.DEFECT_TYPES)
        assert [d["index"] for d in found] == [1, 2]

    def test_section_banners_are_not_counted_as_defects(self):
        """
        An adjudication order carries both "Defect -N" and the bulleted
        heading beneath it. Treating each as a boundary split every limb in
        two and inserted the department's own banners as phantom defects.
        """
        order = "Defect -1:\nOutput turnover discrepancies\n" \
                "• Short payment of tax on outward supplies:\nbody\n"
        found = defects.segment(order, gst.DEFECT_TYPES)
        assert len(found) == 1
        assert found[0]["heading"] == "Short payment of tax on outward supplies"

    def test_no_headings_returns_nothing_rather_than_a_guess(self):
        assert defects.segment("A letter with no defect headings at all.",
                               gst.DEFECT_TYPES) == []


class TestAmounts:
    """
    Amounts are read off the department's own annexure using the checksum the
    table carries for free: four head amounts that sum to their own total.
    """

    EXPECTED = {
        "outward_short_payment": (90003, {"sgst": 2, "cgst": 2, "igst": 89999}),
        "turnover_difference": (481548, {"unallocated": 481548}),
        "itc_excess_2b": (116732, {"sgst": 58366, "cgst": 58366}),
        "itc_blocked_17_5": (371221, {"sgst": 185446, "cgst": 185446, "igst": 329}),
        "late_fee": (2300, {"sgst": 1150, "cgst": 1150}),
        "einvoice": (50000, {"cgst": 25000, "sgst": 25000}),
    }

    def _read(self, defect):
        return notice_tables.read_defect_amount(
            defect["notice_extract"],
            notice_tables.detect_head_order(NOTICE),
            defect.get("preamble", ""),
        )

    @pytest.mark.parametrize("key", list(EXPECTED))
    def test_amount_matches_the_notice(self, parsed, key):
        defect = next(d for d in parsed if d["type"] == key)
        row = self._read(defect)
        assert row is not None, f"no amount read for {key}"
        assert row["total"] == pytest.approx(self.EXPECTED[key][0], abs=1)

    @pytest.mark.parametrize("key", list(EXPECTED))
    def test_head_split_matches_the_notice(self, parsed, key):
        defect = next(d for d in parsed if d["type"] == key)
        row = self._read(defect)
        for head, amount in self.EXPECTED[key][1].items():
            assert row["amounts"].get(head) == pytest.approx(amount, abs=1)

    def test_first_limb_reads_a_table_printed_above_its_own_heading(self, parsed):
        """
        Departmental PDFs do not reliably emit in reading order. The first
        limb's table lands before its bullet heading, so it is offered the
        preamble — and only the first limb, so no later limb can be given a
        figure belonging to its neighbour.
        """
        first = parsed[0]
        assert "preamble" in first
        assert self._read(first)["total"] == 90003

    def test_only_the_first_limb_gets_a_preamble(self, parsed):
        assert not any("preamble" in d for d in parsed[1:])

    def test_a_run_that_fails_its_own_arithmetic_is_discarded(self):
        assert notice_tables.find_head_rows("10 20 30 40 999") == []

    def test_unreadable_amount_returns_nothing_rather_than_a_guess(self):
        """A blank a reviewer can see beats a wrong figure they cannot."""
        assert notice_tables.read_defect_amount(
            "• Interest on amendments:\nS.No Description\n1 B2B Regular 1 0\n0\n"
        ) is None

    def test_four_digit_paired_heads_are_matched(self):
        """
        The paired pattern once used a three-digit-max alternative that matched
        the first three digits of "1150" and then never fired on any four-digit
        figure — which is most of them.
        """
        row = notice_tables.paired_head_row("1 2 1150 1150",
                                            ["sgst", "cgst", "igst", "cess"])
        assert row["total"] == 2300

    def test_a_zero_pair_does_not_abort_the_scan(self):
        row = notice_tables.paired_head_row("0 0 then 1150 1150",
                                            ["sgst", "cgst", "igst", "cess"])
        assert row["total"] == 2300

    def test_per_head_penalty_is_doubled_not_halved(self):
        """"Rs. 25000 each under CGST and SGST" is a Rs. 50,000 exposure."""
        row = notice_tables.each_head_penalty(
            "penalty under section 125 of Rs. 25000/- each under CGST and SGST")
        assert row["total"] == 50000
        assert row["amounts"] == {"cgst": 25000.0, "sgst": 25000.0}


class TestTriage:
    def test_only_limbs_that_turn_on_law_convene_counsel(self, parsed):
        summary = defects.triage(parsed)
        argued = {d["type"] for d in summary["argue"]}
        assert argued == {"itc_excess_2b", "itc_blocked_17_5", "einvoice"}

    def test_arithmetic_limbs_are_settled_without_a_panel(self, parsed):
        settled = {d["type"] for d in defects.triage(parsed)["settle"]}
        assert settled == {"outward_short_payment", "turnover_difference",
                           "late_fee"}

    def test_amounts_split_across_the_two_groups(self, parsed):
        for defect in parsed:
            row = notice_tables.read_defect_amount(
                defect["notice_extract"],
                notice_tables.detect_head_order(NOTICE),
                defect.get("preamble", ""))
            if row:
                defect["amount_by_head"] = defects.normalise_heads(row["amounts"])
        summary = defects.triage(parsed)
        assert summary["argued_amount"] + summary["settled_amount"] == \
            pytest.approx(summary["total_amount"])


class TestEvidenceRequirements:
    def test_the_einvoice_limb_demands_the_irp_portal_report(self):
        """
        The one limb lost in the reference matter was lost on this exact
        document. It is named here so the demand survives any prompt change.
        """
        evidence = " ".join(gst.evidence_for("einvoice")).lower()
        assert "irp portal" in evidence
        assert "first month of mandatory applicability" in evidence

    def test_the_2b_limb_demands_the_credit_ledger_for_interest(self):
        evidence = " ".join(gst.evidence_for("itc_excess_2b")).lower()
        assert "electronic credit ledger" in evidence

    def test_the_17_5_limb_demands_the_works_contract_documents(self):
        evidence = " ".join(gst.evidence_for("itc_blocked_17_5")).lower()
        assert "work orders" in evidence or "work order" in evidence

    def test_every_defect_type_names_its_evidence(self):
        bare = [d.key for d in gst.DEFECT_TYPES if not d.evidence_required]
        assert not bare, f"defect types with no evidence list: {bare}"


class TestMoney:
    def test_indian_digit_grouping(self):
        assert defects.indian_number(1765427) == "17,65,427"
        assert defects.indian_number(90003) == "90,003"
        assert defects.indian_number(999) == "999"

    def test_head_formatting_reads_as_a_reply_states_it(self):
        assert defects.format_heads({"cgst": 58366, "sgst": 58366}) == \
            "CGST 58,366 + SGST 58,366"

    def test_a_bare_number_is_held_unallocated_not_guessed_into_a_head(self):
        """Putting an IGST figure in the CGST column survives review."""
        assert defects.normalise_heads(5000)["unallocated"] == 5000
        assert defects.normalise_heads(5000)["cgst"] == 0


class TestValidation:
    def test_an_undecided_limb_blocks_filing(self):
        problems = defects.validate(defects.new_defect(1, "Something"))
        assert any("no position has been settled" in p for p in problems)

    def test_a_conceded_limb_needs_its_payment_reference(self):
        problems = defects.validate(defects.new_defect(
            1, "Late fee", posture=defects.AGREED_PAID, annexures=["challan"]))
        assert any("DRC-03" in p for p in problems)

    def test_a_payment_written_as_prose_reads_as_no_reference(self):
        """
        A payment the panel wrote as a sentence carries no reference this can
        read. Treating it as absent raises the blocker a reviewer can act on;
        indexing it as a mapping raised AttributeError inside the panel run.
        """
        defect = defects.new_defect(1, "Late fee", posture=defects.AGREED_PAID,
                                    annexures=["challan"])
        defect["payment"] = "Rs. 2,300 paid vide DRC-03 dated 26/06/2026"
        assert any("DRC-03" in p for p in defects.validate(defect))

    def test_a_split_that_does_not_reconcile_is_reported(self):
        problems = defects.validate(defects.new_defect(
            1, "Blocked credit", posture=defects.PARTIAL,
            amount_by_head={"cgst": 100000},
            annexures=["invoices"],
            splits=[{"amount_by_head": {"cgst": 40000}}],
        ))
        assert any("must reconcile" in p for p in problems)

    def test_a_contested_limb_needs_an_annexure(self):
        problems = defects.validate(defects.new_defect(
            1, "Blocked credit", posture=defects.CONTESTED))
        assert any("no annexure is listed" in p for p in problems)

    def test_an_open_evidence_gap_blocks_filing(self):
        problems = defects.validate(defects.new_defect(
            1, "E-invoicing", posture=defects.CONTESTED,
            annexures=["IRP report"],
            evidence_gap=["IRP portal report for August 2023"]))
        assert any("evidence gap outstanding" in p for p in problems)

    def test_a_complete_limb_passes(self):
        assert defects.validate(defects.new_defect(
            1, "Blocked credit", posture=defects.CONTESTED,
            annexures=["Purchase invoices"])) == []
