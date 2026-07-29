"""Cost in rupees, and the estimate that learns from the firm's own runs."""

import pytest

from backend import pricing


class TestIndianFormatting:
    def test_lakh_grouping_not_thousand_grouping(self):
        # 12,34,567 — not 1,234,567. A figure grouped the wrong way reads as a
        # foreign number to the person checking it.
        assert pricing.format_inr(1234567, paise=False) == "Rs. 12,34,567"

    def test_crore_grouping(self):
        assert pricing.format_inr(12345678, paise=False) == "Rs. 1,23,45,678"

    def test_small_amounts_are_not_grouped(self):
        assert pricing.format_inr(999, paise=False) == "Rs. 999"

    def test_thousands_boundary(self):
        assert pricing.format_inr(1000, paise=False) == "Rs. 1,000"
        assert pricing.format_inr(100000, paise=False) == "Rs. 1,00,000"

    def test_paise_are_shown_by_default(self):
        assert pricing.format_inr(1234.5) == "Rs. 1,234.50"

    def test_negative_amounts_keep_the_sign_outside(self):
        assert pricing.format_inr(-1234, paise=False) == "-Rs. 1,234"

    def test_none_is_a_dash_not_a_zero(self):
        assert pricing.format_inr(None) == "—"

    def test_junk_does_not_raise(self):
        assert pricing.format_inr("not a number") == "—"


class TestConversion:
    def test_uses_the_configured_rate(self, monkeypatch):
        monkeypatch.setattr(pricing, "USD_INR", 90.0)
        assert pricing.to_inr(1.0) == 90.0

    def test_none_passes_through(self):
        assert pricing.to_inr(None) is None


class TestObservedRates:
    def _matter(self, tier, cost, limbs, status="complete"):
        return {"tier": tier, "status": status,
                "usage": {"total_cost": cost},
                "panel_defect_count": limbs}

    def test_learns_a_per_limb_rate_from_completed_matters(self):
        rates = pricing.observed_rates([
            self._matter("pro", 1.0, 5),
            self._matter("pro", 2.0, 5),
            self._matter("pro", 1.5, 5),
        ])
        assert rates["pro"]["samples"] == 3
        assert rates["pro"]["per_limb"] == pytest.approx(0.3)

    def test_median_not_mean_so_one_runaway_does_not_move_it(self):
        rates = pricing.observed_rates([
            self._matter("pro", 1.0, 1),
            self._matter("pro", 1.0, 1),
            self._matter("pro", 50.0, 1),
        ])
        assert rates["pro"]["per_limb"] == 1.0

    def test_incomplete_matters_are_excluded(self):
        rates = pricing.observed_rates([
            self._matter("pro", 5.0, 1, status="draft"),
        ])
        assert "pro" not in rates

    def test_matters_without_a_limb_count_are_excluded(self):
        rates = pricing.observed_rates([
            {"tier": "pro", "status": "complete",
             "usage": {"total_cost": 1.0}},
        ])
        assert "pro" not in rates

    def test_retired_free_tier_history_counts_towards_draft(self):
        # Those matters were run on the draft models; their costs belong to
        # that tier's history rather than being discarded.
        rates = pricing.observed_rates([
            self._matter("free", 0.1, 1),
            self._matter("free", 0.1, 1),
        ])
        assert "draft" in rates and "free" not in rates


class TestEstimate:
    def test_falls_back_to_stated_defaults_with_no_history(self):
        estimate = pricing.estimate_run(8, 2, "pro", history=[])
        assert estimate["learned_from_history"] is False
        assert "not yet completed enough" in estimate["basis"]
        assert estimate["inr"]["low"] < estimate["inr"]["high"]

    def test_learns_once_there_is_enough_history(self):
        history = [
            {"tier": "pro", "status": "complete",
             "usage": {"total_cost": 1.0}, "panel_defect_count": 2}
            for _ in range(4)
        ]
        estimate = pricing.estimate_run(8, 2, "pro", history=history)
        assert estimate["learned_from_history"] is True
        assert "your firm's last 4" in estimate["basis"]
        assert estimate["usd"]["central"] == pytest.approx(1.0)

    def test_one_or_two_runs_are_not_enough_to_learn_from(self):
        history = [
            {"tier": "pro", "status": "complete",
             "usage": {"total_cost": 1.0}, "panel_defect_count": 2}
            for _ in range(2)
        ]
        estimate = pricing.estimate_run(8, 2, "pro", history=history)
        assert estimate["learned_from_history"] is False

    def test_estimate_scales_with_convened_limbs_not_total_limbs(self):
        # Triage means most limbs never convene counsel. Estimating on the
        # total would overstate a typical eight-limb notice fourfold.
        few = pricing.estimate_run(8, 2, "pro", history=[])
        many = pricing.estimate_run(8, 8, "pro", history=[])
        assert many["usd"]["central"] > few["usd"]["central"]

    def test_draft_tier_is_materially_cheaper_than_pro(self):
        draft = pricing.estimate_run(8, 2, "draft", history=[])
        pro = pricing.estimate_run(8, 2, "pro", history=[])
        assert draft["usd"]["central"] < pro["usd"]["central"]

    def test_label_is_a_rupee_range_a_partner_can_read(self):
        estimate = pricing.estimate_run(8, 2, "pro", history=[])
        assert estimate["label"].startswith("Rs. ")
        assert " to Rs. " in estimate["label"]

    def test_legacy_free_tier_estimates_as_draft(self):
        assert pricing.estimate_run(1, 1, "free", history=[])["tier"] == "draft"

    def test_zero_convened_limbs_still_returns_a_figure(self):
        estimate = pricing.estimate_run(8, 0, "pro", history=[])
        assert estimate["usd"]["central"] >= 0


class TestDescribeUsage:
    def test_reports_both_currencies(self, monkeypatch):
        monkeypatch.setattr(pricing, "USD_INR", 88.0)
        described = pricing.describe_usage({"total_cost": 1.0,
                                            "total_tokens": 5000})
        assert described["usd"] == 1.0
        assert described["inr"] == 88.0
        assert described["label"] == "Rs. 88.00"
        assert described["tokens"] == 5000

    def test_absent_usage_is_a_dash(self):
        assert pricing.describe_usage({})["label"] == "—"
        assert pricing.describe_usage(None)["label"] == "—"
