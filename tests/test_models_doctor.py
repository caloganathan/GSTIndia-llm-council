"""The model doctor.

Model IDs on OpenRouter churn, and this codebase has already lost a whole tier
to it — silently, and taking notice reading with it, because the intake reader
borrows the tier's grounding model. Startup validation says WHICH ID is stale;
the doctor says what to put in its place, and can be run before a deploy rather
than after one.

The catalogue is faked here. The point under test is the judgement — that a
slot's requirements are actually applied — not that urllib works.
"""

import pytest

from backend import config, models_doctor


def _model(context=200_000, completion_price=5.0):
    return {
        "context_length": context,
        "pricing": {"completion": completion_price / 1_000_000},
    }


# A catalogue with one of everything the checks care about.
CATALOGUE = {
    "vendor/big-and-able": _model(context=400_000, completion_price=15.0),
    "vendor/cheap-and-able": _model(context=200_000, completion_price=0.40),
    "vendor/cheap-but-tiny": _model(context=8_000, completion_price=0.10),
    # Enough context for a counsel seat, not enough to also hold search
    # results — so it is fine for an opening analysis and wrong for
    # grounding or verification.
    "vendor/thin-for-web": _model(context=40_000, completion_price=1.0),
    "vendor/free": _model(context=200_000, completion_price=0.0),
    "other/big-and-able": _model(context=300_000, completion_price=12.0),
    "other/cheap-and-able": _model(context=128_000, completion_price=0.20),
}


class TestSlotRequirements:
    def test_a_missing_id_is_reported_as_gone(self, monkeypatch):
        monkeypatch.setattr(config, "PRO_ROLE_MODELS",
                            {"revenue": "vendor/deleted-last-quarter"})
        monkeypatch.setattr(config, "DRAFT_ROLE_MODELS", {})
        results = models_doctor.diagnose(CATALOGUE)
        entry = next(r for r in results if r["env"] == "PRO_MODEL_REVENUE")
        assert entry["verdict"] == "MISSING"

    def test_an_id_that_exists_but_is_too_small_for_the_chairman_fails(
            self, monkeypatch):
        """The chairman writes the longest single output in the product against
        a 16,000-token ceiling. A small window there truncates the one output
        that matters most — and it would pass a bare existence check."""
        monkeypatch.setattr(config, "PRO_ROLE_MODELS",
                            {"chairman": "vendor/cheap-but-tiny"})
        monkeypatch.setattr(config, "DRAFT_ROLE_MODELS", {})
        results = models_doctor.diagnose(CATALOGUE)
        entry = next(r for r in results if r["env"] == "PRO_MODEL_CHAIRMAN")
        assert entry["verdict"] == "WRONG SHAPE"
        assert any("chairman writes the longest" in p for p in entry["problems"])

    def test_a_grounding_slot_needs_room_for_the_search_results(self, monkeypatch):
        """
        The web plugin injects search results INTO the prompt, on top of a
        prompt that already carries every authority. A model with enough
        context for a counsel seat can still be too thin here — and it would
        pass a bare existence check.

        (Plugin support itself is not a per-model property on OpenRouter and
        the catalogue exposes no flag for it. An earlier draft pretended to
        check for one, with a fallback that made the check always pass.)
        """
        monkeypatch.setattr(config, "PRO_ROLE_MODELS", {})
        monkeypatch.setattr(config, "DRAFT_ROLE_MODELS", {})
        monkeypatch.setattr(config, "GROUNDING_MODEL", "vendor/thin-for-web")
        results = models_doctor.diagnose(CATALOGUE)
        entry = next(r for r in results if r["env"] == "GROUNDING_MODEL")
        assert entry["verdict"] == "WRONG SHAPE"
        assert any("web search" in p for p in entry["problems"])

    def test_the_same_model_is_fine_in_a_counsel_seat(self, monkeypatch):
        """The floor is per slot, not global — otherwise the doctor condemns
        models that are perfectly good where they actually sit."""
        monkeypatch.setattr(config, "PRO_ROLE_MODELS",
                            {"revenue": "vendor/thin-for-web"})
        monkeypatch.setattr(config, "DRAFT_ROLE_MODELS", {})
        results = models_doctor.diagnose(CATALOGUE)
        entry = next(r for r in results if r["env"] == "PRO_MODEL_REVENUE")
        assert entry["verdict"] == "OK"

    def test_an_expensive_model_in_a_draft_slot_fails(self, monkeypatch):
        """The draft tier exists to cost cents. A frontier model there is not
        a cheap tier, and having two tiers stops meaning anything."""
        monkeypatch.setattr(config, "PRO_ROLE_MODELS", {})
        monkeypatch.setattr(config, "DRAFT_ROLE_MODELS",
                            {"revenue": "vendor/big-and-able"})
        results = models_doctor.diagnose(CATALOGUE)
        entry = next(r for r in results if r["env"] == "DRAFT_MODEL_REVENUE")
        assert entry["verdict"] == "WRONG SHAPE"
        assert any("cheap-tier price" in p for p in entry["problems"])

    def test_a_good_id_passes(self, monkeypatch):
        monkeypatch.setattr(config, "PRO_ROLE_MODELS",
                            {"revenue": "vendor/big-and-able"})
        monkeypatch.setattr(config, "DRAFT_ROLE_MODELS",
                            {"revenue": "vendor/cheap-and-able"})
        results = models_doctor.diagnose(CATALOGUE)
        verdicts = {r["env"]: r["verdict"] for r in results}
        assert verdicts["PRO_MODEL_REVENUE"] == "OK"
        assert verdicts["DRAFT_MODEL_REVENUE"] == "OK"

    def test_the_general_council_is_only_checked_when_it_is_enabled(
            self, monkeypatch):
        """It ships off. Reporting four stale IDs for a mode nobody runs is
        noise that hides the slots that matter."""
        monkeypatch.setattr(config, "ENABLE_GENERAL_COUNCIL", False)
        envs = {r["env"] for r in models_doctor.diagnose(CATALOGUE)}
        assert "COUNCIL_MODELS" not in envs

        monkeypatch.setattr(config, "ENABLE_GENERAL_COUNCIL", True)
        envs = {r["env"] for r in models_doctor.diagnose(CATALOGUE)}
        assert "COUNCIL_MODELS" in envs

    def test_every_slot_that_reaches_a_model_is_covered(self, monkeypatch):
        """The omission that caused the original outage was a slot nobody
        checked. Both grounding slots must be in the list."""
        monkeypatch.setattr(config, "ENABLE_GENERAL_COUNCIL", False)
        envs = {r["env"] for r in models_doctor.diagnose(CATALOGUE)}
        for required in ("GROUNDING_MODEL", "DRAFT_GROUNDING_MODEL",
                         "VERIFIER_MODEL", "DRAFT_VERIFIER_MODEL",
                         "PRO_MODEL_CHAIRMAN", "DRAFT_MODEL_CHAIRMAN"):
            assert required in envs, f"{required} is not checked"


class TestSuggestions:
    def _slot(self, **kwargs):
        base = {"env": "PRO_MODEL_REVENUE", "value": "vendor/gone",
                "label": "test", "needs_web": False, "is_chairman": False,
                "cheap": False}
        return {**base, **kwargs}

    def test_the_same_vendor_is_preferred(self):
        """A firm that chose one vendor for the assessee seat chose
        deliberately. Fixing a typo must not reshuffle the panel."""
        candidates = models_doctor.suggest(self._slot(), CATALOGUE)
        assert candidates[0][0].startswith("vendor/")

    def test_a_cheap_slot_is_offered_cheap_models(self):
        candidates = models_doctor.suggest(
            self._slot(value="vendor/gone", cheap=True), CATALOGUE)
        assert candidates, "no candidate offered for a cheap slot"
        for model_id, price in candidates:
            assert price <= models_doctor.MAX_DRAFT_OUTPUT_PRICE

    def test_a_chairman_slot_is_not_offered_a_small_window(self):
        candidates = models_doctor.suggest(
            self._slot(is_chairman=True), CATALOGUE)
        assert "vendor/cheap-but-tiny" not in [c[0] for c in candidates]

    def test_a_web_slot_is_not_offered_a_model_too_thin_for_it(self):
        candidates = models_doctor.suggest(
            self._slot(needs_web=True), CATALOGUE)
        assert "vendor/thin-for-web" not in [c[0] for c in candidates]

    def test_free_endpoints_are_never_suggested(self):
        """The retired free tier is the reason this file exists. Every ID in it
        went stale and the tier failed silently in production."""
        candidates = models_doctor.suggest(self._slot(cheap=True), CATALOGUE)
        assert "vendor/free" not in [c[0] for c in candidates]


class TestOfflineBehaviour:
    def test_an_unreachable_catalogue_says_so_and_does_not_raise(self):
        catalogue, reason = models_doctor.fetch_catalogue(
            "https://127.0.0.1:1/models", timeout=0.2)
        assert catalogue is None
        assert reason

    def test_the_report_exits_two_when_it_cannot_check(self, capsys):
        code = models_doctor.report(url="https://127.0.0.1:1/models")
        assert code == 2
        out = capsys.readouterr().out
        # It must say where to run it instead, not just fail.
        assert "openrouter.ai" in out
        assert "Shell tab" in out

    def test_an_empty_catalogue_is_a_failure_not_a_clean_bill(self, monkeypatch):
        """A catalogue that comes back empty would otherwise report every
        configured ID as MISSING, which reads as catastrophe rather than as a
        broken request."""
        monkeypatch.setattr(models_doctor, "fetch_catalogue",
                            lambda *a, **k: (None, "the catalogue came back empty"))
        assert models_doctor.report() == 2
