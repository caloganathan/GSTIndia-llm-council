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

    def test_utilised_credit_attracts_section_50_3_at_eighteen_percent(self):
        """
        The notified s.50(3) rate is 18%, not 24%. Section 116 of the Finance
        Act 2022, with its Sixth Schedule, amended Notification 13/2017-CT
        retrospectively w.e.f. 01.07.2017. The 24% in the section is a ceiling.
        This test asserted 24.0 until September 2026 and so locked the wrong
        rate in; it overstated every utilised-credit working by a third.
        """
        result = calculators.interest_on_defect(
            100000, "2024-01-01", "2024-12-31", itc_utilised=True)
        assert result["rate"] == 18.0
        assert result["amount"] == 18000.0
        assert "50(3)" in result["basis"]
        joined = " ".join(result["caveats"])
        assert "Sixth Schedule" in joined and "ceiling" in joined
        assert "Rule 88B" in joined

    def test_the_constant_is_the_notified_rate_not_the_statutory_ceiling(self):
        assert calculators.INTEREST_RATE_ITC_UTILISED == 18.0

    def test_credit_not_utilised_is_a_defence_and_computes_nil(self):
        """
        Availed but not utilised: no interest arises under s.50(3), and no tax
        was short paid to engage s.50(1). The branch used to compute 18% under
        s.50(1) while its own caveat said nothing arose — once the s.50(3)
        rate was corrected, utilised and unutilised credit gave the SAME
        figure, which is the defence silently thrown away.
        """
        result = calculators.interest_on_defect(
            100000, "2024-01-01", "2024-12-31", itc_utilised=False)
        assert result["computed"] is True
        assert result["amount"] == 0.0
        assert "not attracted" in result["basis"]
        utilised = calculators.interest_on_defect(
            100000, "2024-01-01", "2024-12-31", itc_utilised=True)
        assert utilised["amount"] != result["amount"]
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

    def test_cash_ledger_proviso_states_its_exception_for_proceedings(self):
        """The relief does not apply to a return filed after s.73/74/74A
        proceedings commenced — the very matters this product handles."""
        result = calculators.interest_on_defect(
            100000, "2024-01-01", "2024-12-31")
        proviso = next(c for c in result["caveats"]
                       if "electronic cash ledger" in c)
        assert "commencement of proceedings" in proviso
        assert "74A" in proviso


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

    def test_74_carries_the_post_order_fifty_percent_stage(self):
        """s.74(11): 50% if paid within 30 days of the order. It was only in a
        note, so the table showed 100% as the only post-order figure."""
        result = calculators.penalty_options("74", 400000, "2026-01-10")
        stages = {s["stage"]: s for s in result["stages"]}
        assert stages["within_30_days_of_order"]["amount"] == 200000.0
        assert "74(11)" in stages["within_30_days_of_order"]["note"]

    def test_self_assessed_tax_exception_is_flagged_on_73(self):
        """s.73(11): the nil-penalty windows do not reach self-assessed tax
        unpaid beyond 30 days of its due date."""
        result = calculators.penalty_options("73", 100000, "2026-01-10")
        assert any("73(11)" in c and "self-assessed" in c
                   for c in result["caveats"])

    def test_self_assessed_tax_exception_is_flagged_on_74a_non_fraud(self):
        result = calculators.penalty_options("74A", 100000, "2026-01-10")
        assert any("74A(11)" in c for c in result["caveats"])

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

    def test_penalty_only_appeal_is_ten_percent_after_finance_act_2025(self):
        """The proviso to s.107(6) was substituted w.e.f. 01.10.2025: every
        penalty-only order, s.129(3) included, now needs 10% — the s.129(3)
        deposit was 25% until then."""
        result = calculators.predeposit(200000, "107", penalty_only=True)
        assert result["amount"] == 20000.0
        assert "129(3)" in result["basis"]
        assert "01.10.2025" in result["basis"]
        assert any("25%" in c for c in result["caveats"])

    def test_penalty_only_tribunal_appeal_is_a_further_ten_percent(self):
        result = calculators.predeposit(200000, "112", penalty_only=True)
        assert result["forum"] == "112"
        assert result["amount"] == 20000.0
        assert "112(8)" in result["basis"]

    def test_igst_is_capped_at_forty_crore(self):
        result = calculators.predeposit(500_00_00_000, "107", head="igst")
        assert result["capped"] is True
        assert result["amount"] == 40_00_00_000.0

    def test_the_cap_applies_per_act_not_to_the_combined_demand(self):
        """Rs. 300 crore each of CGST and SGST: each Act's deposit is capped
        at Rs. 20 crore, so Rs. 40 crore in all — not one Rs. 20 crore cap on
        the combined Rs. 600 crore."""
        result = calculators.predeposit_by_head(
            {"cgst": 300_00_00_000, "sgst": 300_00_00_000}, "107")
        assert result["amount"] == 40_00_00_000.0
        assert len(result["by_head"]) == 2

    def test_head_wise_deposit_below_the_cap_is_ten_percent_of_the_total(self):
        result = calculators.predeposit_by_head(
            {"cgst": 50000, "sgst": 50000, "igst": 0}, "107")
        assert result["amount"] == 10000.0
        # The old caveat said "the same amount again is payable under the
        # SGST Act" on a figure that already included SGST.
        assert not any("same amount again" in c for c in result["caveats"])

    def test_unallocated_heads_are_flagged_not_guessed(self):
        result = calculators.predeposit_by_head({"unallocated": 100000})
        assert result["amount"] == 10000.0
        assert any("not split by head" in c for c in result["caveats"])

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
        # Deliberately NOT asserted as 60. Section 107 runs in calendar
        # months, so the remaining days depend on which months the period
        # spans — asserting a fixed 60 was what encoded the 90-day bug this
        # class now tests against.
        assert 58 <= result["days_remaining"] <= 63

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


class TestTribunalLimitation:
    """Section 112: three months plus three, or the notified Tribunal date
    (31.07.2026 for orders communicated before 01.05.2026, S.O. 3502(E)) if
    later."""

    def test_an_order_after_the_cutoff_runs_three_months(self):
        result = calculators.appeal_limitation("2026-05-10", as_on="2026-06-01",
                                               forum="112")
        assert result["forum"] == "112"
        assert result["ordinary_deadline"] == "2026-08-10"
        assert result["condonable_deadline"] == "2026-11-10"

    def test_a_backlog_order_takes_the_notified_date(self):
        result = calculators.appeal_limitation("2025-01-15", as_on="2026-07-01",
                                               forum="112")
        assert result["ordinary_deadline"] == "2026-07-31"
        assert result["status"] == "in_time"
        assert any("01.05.2026" in c for c in result["caveats"])

    def test_an_april_2026_order_is_in_the_backlog_cohort(self):
        """S.O. 3502(E) moved the cohort to orders before 01.05.2026. With the
        old 01.04.2026 cut-off this order read condonable from 16.07.2026."""
        result = calculators.appeal_limitation("2026-04-15", as_on="2026-07-20",
                                               forum="112")
        assert result["status"] == "in_time"
        assert result["ordinary_deadline"] == "2026-07-31"
        assert result["condonable_deadline"] == "2026-10-31"

    def test_a_may_2026_order_runs_its_own_three_months(self):
        result = calculators.appeal_limitation("2026-05-01", as_on="2026-06-01",
                                               forum="112")
        assert result["ordinary_deadline"] == "2026-08-01"

    def test_a_backlog_order_after_the_notified_date_is_flagged_arguable(self):
        result = calculators.appeal_limitation("2025-01-15", as_on="2026-09-23",
                                               forum="112")
        assert result["status"] == "condonable"
        assert any("not settled" in c for c in result["caveats"])

    def test_the_later_of_three_months_and_the_notified_date_governs(self):
        # 3 months from 30.04.2026 is 30.07.2026, a day before 31.07.2026.
        result = calculators.appeal_limitation("2026-04-30", as_on="2026-05-01",
                                               forum="112")
        assert result["ordinary_deadline"] == "2026-07-31"

    def test_first_appeal_is_unchanged_by_the_tribunal_dates(self):
        result = calculators.appeal_limitation("2025-01-15", as_on="2025-02-01")
        assert result["forum"] == "107"
        assert result["ordinary_deadline"] == "2025-04-15"


class TestAmnesty128A:
    # Inside the window, for tests of the section/year/payment logic.
    OPEN = "2025-03-01"

    def test_eligible_year_and_section(self):
        result = calculators.amnesty_128a("73", "FY 2018-19", tax_paid=True,
                                          as_on=self.OPEN)
        assert result["eligible"] is True
        assert result["window_open"] is True

    def test_the_window_closed_on_30_june_2025(self):
        """Tax by 31.03.2025, application by 30.06.2025 (Rule 164). The module
        used to report the waiver AVAILABLE on any s.73 demand for the three
        years, long after it could be claimed."""
        result = calculators.amnesty_128a("73", "FY 2018-19", tax_paid=True,
                                          as_on="2025-07-01")
        assert result["eligible"] is False
        assert result["window_open"] is False
        joined = " ".join(result["reasons"])
        assert "CLOSED" in joined and "30.06.2025" in joined

    def test_the_last_day_of_the_window_is_still_open(self):
        result = calculators.amnesty_128a("73", "FY 2018-19", tax_paid=True,
                                          as_on="2025-06-30")
        assert result["eligible"] is True

    def test_a_redetermined_section_74_demand_gets_six_months(self):
        """Proviso to s.128A(1): the one route still open after 30.06.2025."""
        result = calculators.amnesty_128a(
            "74", "FY 2019-20", tax_paid=True, as_on="2026-09-01",
            redetermination_date="2026-06-15")
        assert result["eligible"] is True
        assert any("15.12.2026" in r for r in result["reasons"])

    def test_a_redetermination_window_also_expires(self):
        result = calculators.amnesty_128a(
            "74", "FY 2019-20", tax_paid=True, as_on="2027-01-01",
            redetermination_date="2026-06-15")
        assert result["eligible"] is False

    def test_the_forms_are_described_correctly(self):
        result = calculators.amnesty_128a("73", "FY 2018-19")
        assert "no order" in result["form"] and "order has been passed" in result["form"]

    def test_erroneous_refund_exclusion_is_stated(self):
        result = calculators.amnesty_128a("73", "FY 2018-19")
        assert any("erroneous refund" in c for c in result["caveats"])

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
        result = calculators.amnesty_128a("73", "FY 2019-20", tax_paid=False,
                                          as_on=self.OPEN)
        assert result["eligible"] is True
        assert any("not yet earned" in r for r in result["reasons"])

    def test_appeal_withdrawal_condition_is_always_stated(self):
        result = calculators.amnesty_128a("73", "FY 2018-19", tax_paid=True)
        assert any("withdrawal" in c for c in result["caveats"])

    def test_the_dates_applied_are_stated_and_flagged_for_confirmation(self):
        result = calculators.amnesty_128a("73", "FY 2018-19")
        assert any("currently in force" in c and "31.03.2025" in c
                   for c in result["caveats"])

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


class TestLimitationRunsInCalendarMonths:
    """
    Section 107 speaks in months, and a month is a calendar month under
    section 3(35) of the General Clauses Act — not thirty days. The module
    computed 90 + 30 days, which moved the deadline by up to two days at the
    margins in BOTH directions. Reporting an in-time appeal as condonable
    invites an unnecessary condonation application; reporting a condonable one
    as time-barred tells a client to abandon a live remedy. Each case below is
    a date pair where the two methods disagree.
    """

    def test_three_months_lands_on_the_same_day_of_the_month(self):
        result = calculators.appeal_limitation("2026-05-30", as_on="2026-06-01")
        # 90 days from 30 May is 28 August. Three calendar months is 30 August.
        assert result["ordinary_deadline"] == "2026-08-30"
        assert result["condonable_deadline"] == "2026-09-30"

    def test_a_short_target_month_clamps_to_its_last_day(self):
        """31 November does not exist: three months from 31 August is 30
        November, and inventing 1 December would lengthen limitation."""
        result = calculators.appeal_limitation("2026-08-31", as_on="2026-09-01")
        assert result["ordinary_deadline"] == "2026-11-30"

    def test_february_clamps_in_a_non_leap_year(self):
        result = calculators.appeal_limitation("2026-11-30", as_on="2026-12-01")
        assert result["ordinary_deadline"] == "2027-02-28"

    def test_february_clamps_in_a_leap_year(self):
        result = calculators.appeal_limitation("2027-11-30", as_on="2027-12-01")
        assert result["ordinary_deadline"] == "2028-02-29"

    def test_a_period_spanning_a_year_end(self):
        result = calculators.appeal_limitation("2026-11-15", as_on="2026-12-01")
        assert result["ordinary_deadline"] == "2027-02-15"
        assert result["condonable_deadline"] == "2027-03-15"

    def test_an_appeal_the_day_count_would_have_called_late_is_in_time(self):
        """The failure that matters: on the old arithmetic 29 August was past
        the 90-day deadline of 28 August and reported as condonable. It is in
        fact the last day but one of the three-month period."""
        result = calculators.appeal_limitation("2026-05-30", as_on="2026-08-29")
        assert result["status"] == "in_time"
        assert result["days_remaining"] == 1

    def test_the_last_day_of_the_period_is_still_in_time(self):
        result = calculators.appeal_limitation("2026-05-30", as_on="2026-08-30")
        assert result["status"] == "in_time"
        assert result["days_remaining"] == 0

    def test_the_day_after_is_condonable(self):
        result = calculators.appeal_limitation("2026-05-30", as_on="2026-08-31")
        assert result["status"] == "condonable"

    def test_the_basis_records_the_general_clauses_act(self):
        result = calculators.appeal_limitation("2026-01-01", as_on="2026-02-01")
        assert "General Clauses Act" in result["basis"]


class TestSection74A:
    """
    Section 74A governs FY 2024-25 onwards and these notices are arriving now.
    `startswith("74")` matched "74A" and routed them through the Section 74
    table — which gets the fraud-track rates right by coincidence and the
    deadline wrong by thirty days, on the one number the taxpayer acts on.
    """

    def test_74a_is_not_routed_through_the_section_74_table(self):
        result = calculators.penalty_options("74A", 100000,
                                             notice_date="2026-01-10")
        assert result["computed"] is True
        assert result["scheme"] == "74A"
        assert result["concession_days"] == 60

    def test_the_concession_deadline_is_sixty_days_not_thirty(self):
        result = calculators.penalty_options("74A", 100000,
                                             notice_date="2026-01-10")
        assert result["concession_deadline"] == "2026-03-11"

    def test_section_74_keeps_its_thirty_day_window(self):
        result = calculators.penalty_options("74", 100000,
                                             notice_date="2026-01-10")
        assert result["concession_days"] == 30
        assert result["concession_deadline"] == "2026-02-09"

    def test_the_non_fraud_track_is_the_default_where_fraud_is_not_established(self):
        result = calculators.penalty_options("74A", 100000)
        assert result["track"] == "non_fraud"
        assert any("NON-FRAUD track" in c for c in result["caveats"])

    def test_the_non_fraud_track_carries_no_penalty_inside_the_window(self):
        result = calculators.penalty_options("74A", 100000)
        stages = {s["stage"]: s for s in result["stages"]}
        assert stages["before_notice"]["amount"] == 0.0
        assert stages["within_60_days"]["amount"] == 0.0

    def test_the_non_fraud_order_penalty_respects_the_ten_thousand_floor(self):
        """10% of a small limb is less than the statutory minimum."""
        result = calculators.penalty_options("74A", 20000)
        stages = {s["stage"]: s for s in result["stages"]}
        assert stages["on_order"]["amount"] == 10000.0

    def test_the_fraud_track_carries_the_fifteen_and_twenty_five_stages(self):
        result = calculators.penalty_options("74A", 100000, fraud=True)
        stages = {s["stage"]: s for s in result["stages"]}
        assert result["track"] == "fraud"
        assert stages["before_notice"]["amount"] == 15000.0
        assert stages["within_60_days"]["amount"] == 25000.0

    def test_the_fraud_track_carries_the_post_order_concession(self):
        """50% within sixty days of the ORDER has no Section 73 equivalent and
        is the stage most often missed once an order has issued."""
        result = calculators.penalty_options("74A", 100000, fraud=True)
        stages = {s["stage"]: s for s in result["stages"]}
        assert stages["within_60_days_of_order"]["amount"] == 50000.0
        assert stages["on_order"]["amount"] == 100000.0

    def test_the_caveats_name_the_years_each_scheme_governs(self):
        result = calculators.penalty_options("74A", 100000)
        assert any("FY 2024-25 onwards" in c for c in result["caveats"])

    def test_amnesty_gives_74a_its_own_reason_not_the_section_74_one(self):
        result = calculators.amnesty_128a("74A", "FY 2024-25")
        assert result["eligible"] is False
        reasons = " ".join(result["reasons"])
        assert "74A" in reasons
        # The s.74 reason offers re-characterisation to s.73 as a route back
        # into the waiver. That route does not exist under s.74A — the year
        # alone puts the matter outside 128A — so the reason must say the
        # route is unavailable rather than hold it out.
        assert "no re-characterisation argument is available" in reasons
        assert "FY 2024-25" in reasons

    def test_section_74_keeps_its_recharacterisation_reason(self):
        result = calculators.amnesty_128a("74", "FY 2018-19")
        assert result["eligible"] is False
        assert any("re-characterisation" in r for r in result["reasons"])


class TestOrdersAndPresentation:
    """Found by rendering the file note end to end after the rate fix."""

    def _matter(self, **intake):
        base = {"section_invoked": "73", "tax_period": "FY 2021-22",
                "defects": [{"index": 1, "amount_by_head":
                             {"cgst": 2060000.0, "sgst": 2060000.0}}]}
        base.update(intake)
        return {"id": "m1", "intake": base}

    def test_an_order_date_is_not_used_as_the_show_cause_notice_date(self):
        """On a DRC-07 the notice_date IS the order. Counting the s.73(8)
        window from it printed a concession deadline that never existed."""
        result = calculators.matter_computations(
            self._matter(notice_type="DRC-07", notice_date="2026-08-01"))
        penalty = result["computations"]["penalty"]
        assert penalty["concession_deadline"] is None
        assert all(s["deadline"] is None for s in penalty["stages"])
        assert any("order is on file" in c for c in penalty["caveats"])

    def test_the_section_74_post_order_concession_is_dated_from_the_order(self):
        result = calculators.matter_computations(self._matter(
            section_invoked="74", notice_type="DRC-07",
            notice_date="2026-08-01"))
        penalty = result["computations"]["penalty"]
        stage = next(s for s in penalty["stages"]
                     if s["stage"] == "within_30_days_of_order")
        assert stage["deadline"] == "2026-08-31"

    def test_the_74a_fraud_post_order_concession_is_sixty_days(self):
        result = calculators.penalty_options("74A", 100000, fraud=True,
                                             order_date="2026-08-01")
        assert result["order_concession_deadline"] == "2026-09-30"

    def test_windows_run_from_issue_not_service(self):
        result = calculators.penalty_options("73", 100000, "2026-01-10")
        assert any("ISSUE" in c and "not from its service" in c
                   for c in result["caveats"])

    def test_workings_use_indian_digit_grouping(self):
        result = calculators.predeposit_by_head(
            {"cgst": 2060000.0, "sgst": 2060000.0})
        assert "20,60,000.00" in result["working"]
        assert "4,12,000.00" in result["working"]
        interest = calculators.compute_interest(317450, "2024-01-01",
                                                "2025-02-06")
        assert "3,17,450.00" in interest["working"]

    def test_the_head_wise_deposit_reaches_the_matter_computation(self):
        result = calculators.matter_computations(
            self._matter(notice_type="DRC-07", notice_date="2026-08-01"))
        deposit = result["computations"]["predeposit_107"]
        assert deposit["amount"] == 412000.0
        assert len(deposit["by_head"]) == 2

    def test_74_outside_the_amnesty_years_does_not_hold_out_128a(self):
        result = calculators.amnesty_128a("74", "FY 2021-22")
        assert not any("re-characterisation" in r for r in result["reasons"])


class TestSecondReviewFindings:
    """Defects found by an independent review of the first correction pass."""

    def _matter(self, **intake):
        base = {"section_invoked": "74", "tax_period": "FY 2021-22",
                "defects": [{"index": 1, "amount_by_head":
                             {"cgst": 50000.0, "sgst": 50000.0}}]}
        base.update(intake)
        return {"id": "m1", "intake": base}

    def test_a_drc_01a_is_not_treated_as_the_show_cause_notice(self):
        """Paying on a DRC-01A is the BEFORE-notice stage (15% under s.74(5)),
        not the 25% within-30-days stage the table used to date from it."""
        result = calculators.matter_computations(
            self._matter(notice_type="DRC-01A", notice_date="2026-09-01"))
        penalty = result["computations"]["penalty"]
        assert penalty["concession_deadline"] is None
        assert "BEFORE-NOTICE stage is still open" in penalty["caveats"][0]

    def test_an_asmt_10_is_not_treated_as_the_show_cause_notice(self):
        result = calculators.matter_computations(self._matter(
            section_invoked="73", notice_type="ASMT-10",
            notice_date="2026-09-01"))
        assert result["computations"]["penalty"]["concession_deadline"] is None

    def test_a_drc_01_is_the_show_cause_notice(self):
        result = calculators.matter_computations(
            self._matter(notice_type="DRC-01", notice_date="2026-09-01"))
        assert result["computations"]["penalty"]["concession_deadline"] \
            == "2026-10-01"

    def test_an_explicit_scn_date_wins(self):
        result = calculators.matter_computations(self._matter(
            notice_type="DRC-01A", notice_date="2026-09-01",
            scn_date="2026-09-10"))
        assert result["computations"]["penalty"]["concession_deadline"] \
            == "2026-10-10"

    def test_a_section_73_demand_cannot_use_the_redetermination_route(self):
        """The first proviso to s.128A(1) reaches only a s.74 notice
        redetermined under s.73."""
        result = calculators.amnesty_128a(
            "73", "2019-20", True, as_on="2026-09-23",
            redetermination_date="2026-06-15")
        assert result["eligible"] is False
        assert any("CLOSED" in r for r in result["reasons"])

    def test_the_redetermination_route_cites_rule_164_7(self):
        result = calculators.amnesty_128a(
            "74", "FY 2019-20", True, as_on="2026-09-01",
            redetermination_date="2026-06-15")
        assert any("Rule 164(7)" in r and "communication" in r
                   for r in result["reasons"])

    def test_section_strings_with_prefixes_resolve(self):
        for text in ("Section 73", "u/s 73", "Sec. 73(9)", "S. 73"):
            assert calculators.penalty_options(text, 100000)["section"] == "73"
        assert calculators.penalty_options("Section 74A", 100000)["scheme"] == "74A"
        reasons = " ".join(calculators.amnesty_128a("Section 61", "2019-20")["reasons"])
        assert "Section Section" not in reasons

    def test_formatted_and_malformed_amounts_do_not_break_the_computation(self):
        result = calculators.matter_computations({"intake": {
            "section_invoked": "73", "tax_period": "FY 2021-22",
            "defects": [None, {"amount_by_head": {"cgst": "1,23,456",
                                                  "sgst": "Rs. 1,23,456"}},
                        {"amount_by_head": "garbage"}]}})
        assert result["tax_base"] == 246912.0
        result = calculators.matter_computations({"intake": {
            "section_invoked": "73", "amount_disputed": "1,23,456"}})
        assert result["tax_base"] == 123456.0

    def test_penalty_only_caveat_cites_the_delhi_high_court(self):
        result = calculators.predeposit(200000, "107", penalty_only=True)
        joined = " ".join(result["caveats"])
        assert "Gaurav Jain" in joined and "SHOW CAUSE NOTICE" in joined
