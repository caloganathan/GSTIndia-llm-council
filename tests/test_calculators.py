"""Statutory arithmetic.

These assert the RULE, not just the sum. A test that only checks
18% x 100 x 365/365 == 18 would pass on an implementation that applied s.50(1)
to utilised credit, and the rate is not where matters are lost — the choice of
provision is.
"""

from datetime import date, timedelta

from backend import calculators


class TestInterest:
    def test_simple_period(self):
        result = calculators.compute_interest(
            100000, "2024-01-01", "2024-12-31", rate=18.0)
        assert result["computed"] is True
        assert result["days"] == 365
        assert result["amount"] == 18000.0

    def test_day_count_excludes_the_start_and_includes_the_end(self):
        # "from the day succeeding the due date until the date of payment"
        result = calculators.compute_interest(100000, "2024-01-01", "2024-01-31")
        assert result["days"] == 30

    def test_working_is_shown_so_it_can_be_checked(self):
        result = calculators.compute_interest(100000, "2024-01-01", "2024-12-31")
        assert "18.0%" in result["working"] or "18%" in result["working"]
        assert "365" in result["working"]
        assert "01.01.2024" in result["working"]

    def test_missing_dates_refuse_rather_than_return_zero(self):
        result = calculators.compute_interest(100000, None, "2024-12-31")
        assert result["computed"] is False
        assert result["amount"] is None

    def test_end_before_start_is_reported_not_negated(self):
        result = calculators.compute_interest(100000, "2024-12-31", "2024-01-01")
        assert result["computed"] is False
        # Never a negative interest figure — that is a wrong number, not a
        # blank, and this product does not produce wrong numbers quietly.
        assert result["amount"] == 0.0

    def test_unparseable_date_does_not_raise(self):
        result = calculators.compute_interest(1000, "not a date", "2024-01-01")
        assert result["computed"] is False


class TestInterestRateSelection:
    """The choice of provision, which is where the money is."""

    def test_utilised_credit_attracts_24_percent(self):
        result = calculators.interest_on_defect(
            100000, "2024-01-01", "2024-12-31", itc_utilised=True)
        assert result["rate"] == 24.0
        assert "50(3)" in result["basis"]

    def test_credit_not_utilised_is_a_defence_not_a_lower_rate(self):
        result = calculators.interest_on_defect(
            100000, "2024-01-01", "2024-12-31", itc_utilised=False)
        assert result["rate"] == 18.0
        joined = " ".join(result["caveats"]).lower()
        # The point is that s.50(3) does not arise AT ALL, which is a positive
        # submission. A caveat that merely notes a lower rate has missed it.
        assert "does not arise" in joined
        assert "ground of defence" in joined

    def test_unknown_utilisation_says_so_rather_than_assuming(self):
        result = calculators.interest_on_defect(
            100000, "2024-01-01", "2024-12-31", itc_utilised=None)
        assert result["rate"] == 18.0
        assert any("has not been established" in c for c in result["caveats"])

    def test_cash_ledger_proviso_is_always_flagged_on_50_1(self):
        result = calculators.interest_on_defect(
            100000, "2024-01-01", "2024-12-31")
        assert any("electronic cash ledger" in c for c in result["caveats"])


class TestPenalty:
    def test_73_carries_no_penalty_in_both_concession_windows(self):
        result = calculators.penalty_options("73", 500000, "2026-01-10")
        stages = {s["stage"]: s for s in result["stages"]}
        assert stages["before_notice"]["amount"] == 0.0
        assert stages["within_30_days"]["amount"] == 0.0
        assert stages["on_order"]["amount"] == 50000.0

    def test_74_windows_are_15_and_25_percent(self):
        result = calculators.penalty_options("74", 400000, "2026-01-10")
        stages = {s["stage"]: s for s in result["stages"]}
        assert stages["before_notice"]["amount"] == 60000.0
        assert stages["within_30_days"]["amount"] == 100000.0
        assert stages["on_order"]["amount"] == 400000.0

    def test_73_9_applies_the_ten_thousand_rupee_floor(self):
        # 10% of Rs. 40,000 is Rs. 4,000, but s.73(9) is the HIGHER of 10% and
        # Rs. 10,000. Computing the percentage alone understates a small limb.
        result = calculators.penalty_options("73", 40000, "2026-01-10")
        on_order = next(s for s in result["stages"] if s["stage"] == "on_order")
        assert on_order["amount"] == 10000.0

    def test_concession_deadline_is_computed_from_the_notice_date(self):
        result = calculators.penalty_options("73", 100000, "2026-01-10")
        assert result["concession_deadline"] == "2026-02-09"
        window = next(s for s in result["stages"]
                      if s["stage"] == "within_30_days")
        assert window["deadline"] == "2026-02-09"

    def test_missing_notice_date_is_flagged_not_guessed(self):
        result = calculators.penalty_options("73", 100000, None)
        assert result["concession_deadline"] is None
        assert any("not on file" in c for c in result["caveats"])

    def test_sub_sections_resolve_to_the_parent(self):
        assert calculators.penalty_options("73(9)", 100000)["section"] == "73"
        assert calculators.penalty_options("74(1)", 100000)["section"] == "74"

    def test_other_sections_are_declined_not_approximated(self):
        result = calculators.penalty_options("122", 100000)
        assert result["computed"] is False
        assert "122" in result["reason"]


class TestPredeposit:
    def test_107_is_ten_percent_of_disputed_tax(self):
        result = calculators.predeposit(1000000, "107")
        assert result["amount"] == 100000.0
        assert result["forum"] == "107"

    def test_cap_applies_on_a_large_demand(self):
        result = calculators.predeposit(500_00_00_000, "107")
        assert result["capped"] is True
        assert result["amount"] == calculators.PREDEPOSIT_107_CAP

    def test_penalty_only_detention_appeal_is_twenty_five_percent(self):
        result = calculators.predeposit(200000, "107", penalty_only=True)
        assert result["amount"] == 50000.0
        assert "129(3)" in result["basis"]

    def test_112_is_a_further_deposit_over_the_107_amount(self):
        result = calculators.predeposit(1000000, "112")
        assert result["forum"] == "112"
        assert "over and above" in result["basis"]

    def test_computed_on_disputed_tax_is_stated(self):
        result = calculators.predeposit(1000000, "107")
        assert any("tax in dispute" in c for c in result["caveats"])


class TestAppealLimitation:
    def test_within_three_months_is_in_time(self):
        order = date.today() - timedelta(days=30)
        result = calculators.appeal_limitation(order.isoformat())
        assert result["status"] == "in_time"
        assert result["days_remaining"] == 60

    def test_between_three_and_four_months_is_condonable_not_barred(self):
        order = date.today() - timedelta(days=100)
        result = calculators.appeal_limitation(order.isoformat())
        assert result["status"] == "condonable"
        assert "condonation of delay" in result["message"]

    def test_beyond_four_months_is_time_barred_and_says_what_remains(self):
        order = date.today() - timedelta(days=200)
        result = calculators.appeal_limitation(order.isoformat())
        assert result["status"] == "time_barred"
        assert "writ" in result["message"]

    def test_time_runs_from_communication_not_the_order_date(self):
        result = calculators.appeal_limitation("2026-01-01")
        assert any("COMMUNICATION" in c for c in result["caveats"])

    def test_as_on_date_can_be_supplied_for_deterministic_testing(self):
        result = calculators.appeal_limitation("2026-01-01", as_on="2026-02-01")
        assert result["status"] == "in_time"
        assert result["ordinary_deadline"] == "2026-04-01"


class TestAmnesty128A:
    def test_eligible_year_and_section(self):
        result = calculators.amnesty_128a("73", "FY 2018-19", tax_paid=True)
        assert result["eligible"] is True

    def test_section_74_is_outside_the_waiver(self):
        result = calculators.amnesty_128a("74", "FY 2018-19")
        assert result["eligible"] is False
        joined = " ".join(result["reasons"])
        # The re-characterisation point is the advice that matters here.
        assert "re-characterisation" in joined or "s.73" in joined

    def test_year_outside_the_window_is_ineligible(self):
        result = calculators.amnesty_128a("73", "FY 2021-22")
        assert result["eligible"] is False
        assert any("2021-22" in r for r in result["reasons"])

    def test_unpaid_tax_keeps_eligibility_but_flags_the_condition(self):
        result = calculators.amnesty_128a("73", "FY 2019-20", tax_paid=False)
        assert result["eligible"] is True
        assert any("not yet earned" in r for r in result["reasons"])

    def test_appeal_withdrawal_condition_is_always_stated(self):
        result = calculators.amnesty_128a("73", "FY 2018-19", tax_paid=True)
        assert any("withdrawal" in c for c in result["caveats"])

    def test_window_dates_are_not_asserted_from_stale_constants(self):
        result = calculators.amnesty_128a("73", "FY 2018-19")
        assert any("currently in force" in c for c in result["caveats"])

    def test_period_formats_all_normalise(self):
        for period in ("FY 2018-19", "2018-19", "2018-2019", "F.Y. 2018-19"):
            assert calculators.amnesty_128a("73", period)["tax_period"] == "2018-19"

    def test_unreadable_period_is_ineligible_rather_than_assumed(self):
        result = calculators.amnesty_128a("73", "")
        assert result["eligible"] is False


class TestMatterComputations:
    def _matter(self, **intake):
        base = {
            "section_invoked": "73",
            "tax_period": "FY 2019-20",
            "notice_date": "2026-01-10",
            "defects": [
                {"index": 1, "amount_by_head":
                    {"igst": 0, "cgst": 50000, "sgst": 50000, "cess": 0}},
            ],
        }
        base.update(intake)
        return {"id": "m1", "intake": base}

    def test_tax_base_is_summed_from_the_limbs(self):
        result = calculators.matter_computations(self._matter())
        assert result["tax_base"] == 100000.0

    def test_penalty_and_amnesty_are_always_produced(self):
        result = calculators.matter_computations(self._matter())
        assert result["computations"]["penalty"]["computed"] is True
        assert "amnesty_128a" in result["computations"]

    def test_an_order_starts_the_appeal_clock(self):
        matter = self._matter(notice_type="DRC-07", notice_date="2026-06-01")
        result = calculators.matter_computations(matter)
        assert "appeal_limitation" in result["computations"]
        assert "predeposit_107" in result["computations"]

    def test_a_notice_does_not_start_the_appeal_clock(self):
        matter = self._matter(notice_type="ASMT-10")
        result = calculators.matter_computations(matter)
        assert "appeal_limitation" not in result["computations"]

    def test_falls_back_to_amount_disputed_when_limbs_carry_no_figures(self):
        matter = self._matter(defects=[], amount_disputed=250000)
        result = calculators.matter_computations(matter)
        assert result["tax_base"] == 250000.0

    def test_an_empty_matter_does_not_raise(self):
        assert calculators.matter_computations({"intake": {}})["tax_base"] == 0.0

    def test_the_output_states_it_was_not_produced_by_a_model(self):
        result = calculators.matter_computations(self._matter())
        assert "not by a model" in result["note"]
