"""The practice-management surface: deadlines, cost, computations, calendar.

These are API-level tests because the behaviour that matters is not the
arithmetic — that is covered in `test_deadlines.py`, `test_pricing.py` and
`test_calculators.py` — but the wiring. A deadline computed correctly and not
surfaced is exactly as useful as one computed wrongly, and a route that a
sibling route swallows is invisible until a user reports it.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import config, storage

TOKEN = "test-practice-token"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
GOLDEN = Path(__file__).resolve().parent.parent / "evals" / "golden"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_ACCESS_TOKEN", TOKEN)
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "conversations"))
    monkeypatch.setattr(config, "STATE_DIR", str(tmp_path))
    from backend.main import app
    return TestClient(app)


def _matter(client, matter_id, **intake):
    base = {
        "client_name": "Test Client Private Limited",
        "notice_type": "ASMT-10",
        "state": "Tamil Nadu",
        "tax_period": "FY 2019-20",
        "section_invoked": "73",
        "notice_date": "2026-01-10",
        "amount_disputed": 100000,
        "defects": [{
            "index": 1, "type": "outward_short_payment", "heading": "Short payment",
            "amount_by_head": {"igst": 0, "cgst": 50000, "sgst": 50000, "cess": 0},
            "posture": "undecided",
        }],
    }
    base.update(intake)
    return storage.create_matter(matter_id, base, "gst", "pro", None)


class TestDeadlineSurfacing:
    def test_matters_carry_their_deadline_state(self, client):
        _matter(client, "m1", due_date="2020-01-01")
        matters = client.get("/api/matters", headers=HEADERS).json()
        assert matters[0]["urgency"] == "overdue"
        assert "OVERDUE" in matters[0]["deadline_label"]

    def test_the_worst_deadline_sorts_first(self, client):
        _matter(client, "far", due_date="2099-01-01")
        _matter(client, "overdue", due_date="2020-01-01")
        matters = client.get("/api/matters", headers=HEADERS).json()
        assert matters[0]["id"] == "overdue"

    def test_a_matter_with_no_deadline_is_still_listed(self, client):
        _matter(client, "nodate", due_date=None)
        matters = client.get("/api/matters", headers=HEADERS).json()
        assert [m["id"] for m in matters] == ["nodate"]
        assert matters[0]["urgency"] == "none"

    def test_the_dashboard_leads_with_what_needs_attention(self, client):
        _matter(client, "m1", due_date="2020-01-01")
        dashboard = client.get("/api/dashboard", headers=HEADERS).json()
        assert dashboard["deadlines"]["attention"] == 1
        assert dashboard["deadlines"]["counts"]["overdue"] == 1
        assert dashboard["deadlines"]["upcoming"][0]["id"] == "m1"


class TestCalendarRoute:
    def test_the_calendar_is_not_swallowed_by_the_matter_route(self, client):
        """
        `/matters/calendar.ics` is declared before `/matters/{matter_id}`.

        Declared the other way round, FastAPI matches the parameterised route
        first and looks for a matter whose id is "calendar.ics" — a 404 that
        looks like a missing feature.
        """
        _matter(client, "m1", due_date="2026-02-10")
        response = client.get("/api/matters/calendar.ics", headers=HEADERS)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/calendar")

    def test_it_carries_the_matters_as_events(self, client):
        _matter(client, "m1", due_date="2026-02-10")
        body = client.get("/api/matters/calendar.ics", headers=HEADERS).text
        assert "BEGIN:VEVENT" in body
        assert "Test Client Private Limited" in body

    def test_it_downloads_rather_than_rendering(self, client):
        _matter(client, "m1", due_date="2026-02-10")
        response = client.get("/api/matters/calendar.ics", headers=HEADERS)
        assert "attachment" in response.headers["content-disposition"]

    def test_it_requires_authentication(self, client):
        assert client.get("/api/matters/calendar.ics").status_code == 401


class TestCostEstimate:
    def _estimate(self, client, defects, tier="pro"):
        return client.post(
            "/api/panel/estimate",
            json={"intake": {"defects": defects}, "domain": "gst", "tier": tier},
            headers=HEADERS,
        ).json()

    def _limb(self, index, posture):
        return {"index": index, "type": "other", "heading": f"Limb {index}",
                "posture": posture,
                "amount_by_head": {"igst": 0, "cgst": 100, "sgst": 100, "cess": 0}}

    def test_estimates_on_the_limbs_that_convene_counsel(self, client):
        # Triage is the cost control. Six of these are answered by documents
        # or a payment and must not be priced as though they were argued.
        limbs = [self._limb(1, "contested"), self._limb(2, "undecided")] + [
            self._limb(i, "explained") for i in range(3, 9)
        ]
        estimate = self._estimate(client, limbs)
        assert estimate["triage"]["total"] == 8
        assert estimate["triage"]["convening_counsel"] == 2
        assert estimate["triage"]["answered_without_panel"] == 6

    def test_the_figure_is_in_rupees(self, client):
        estimate = self._estimate(client, [self._limb(1, "contested")])
        assert estimate["label"].startswith("Rs. ")
        assert estimate["inr"]["low"] < estimate["inr"]["high"]

    def test_more_argued_limbs_cost_more(self, client):
        one = self._estimate(client, [self._limb(1, "contested")])
        many = self._estimate(client, [self._limb(i, "contested")
                                       for i in range(1, 6)])
        assert many["inr"]["central"] > one["inr"]["central"]

    def test_draft_is_cheaper_than_pro(self, client):
        limbs = [self._limb(1, "contested")]
        assert (self._estimate(client, limbs, "draft")["inr"]["central"]
                < self._estimate(client, limbs, "pro")["inr"]["central"])

    def test_a_notice_with_no_limbs_is_not_estimated_at_zero(self, client):
        estimate = self._estimate(client, [])
        assert estimate["inr"]["central"] > 0

    def test_the_basis_of_the_estimate_is_stated(self, client):
        estimate = self._estimate(client, [self._limb(1, "contested")])
        assert estimate["basis"]
        assert estimate["learned_from_history"] is False


class TestComputations:
    def test_penalty_stages_are_returned_with_their_deadlines(self, client):
        _matter(client, "m1", due_date="2026-02-10")
        result = client.get("/api/matters/m1/computations", headers=HEADERS).json()
        penalty = result["computations"]["penalty"]
        assert penalty["computed"] is True
        assert penalty["concession_deadline"] == "2026-02-09"

    def test_the_tax_base_comes_from_the_limbs(self, client):
        _matter(client, "m1")
        result = client.get("/api/matters/m1/computations", headers=HEADERS).json()
        assert result["tax_base"] == 100000.0

    def test_amnesty_position_is_always_stated(self, client):
        _matter(client, "m1")
        result = client.get("/api/matters/m1/computations", headers=HEADERS).json()
        assert "amnesty_128a" in result["computations"]
        assert result["computations"]["amnesty_128a"]["reasons"]

    def test_unknown_matter_is_a_404(self, client):
        assert client.get("/api/matters/nope/computations",
                          headers=HEADERS).status_code == 404

    def test_it_requires_authentication(self, client):
        _matter(client, "m1")
        assert client.get("/api/matters/m1/computations").status_code == 401


class TestHealthSurfacesCapabilityGaps:
    def test_ocr_availability_is_reported(self, client):
        health = client.get("/api/health", headers=HEADERS).json()
        assert "ocr" in health
        assert isinstance(health["ocr"]["available"], bool)

    def test_an_unavailable_engine_carries_an_actionable_reason(self, client, monkeypatch):
        from backend import ocr
        monkeypatch.setattr(
            ocr, "available",
            lambda: (False, "Install the OCR extra: uv sync --extra ocr"))
        health = client.get("/api/health", headers=HEADERS).json()
        assert health["ocr"]["available"] is False
        assert "uv sync --extra ocr" in health["ocr"]["reason"]

    def test_the_conversion_rate_is_reported_so_figures_can_be_checked(self, client):
        health = client.get("/api/health", headers=HEADERS).json()
        assert health["usd_inr_rate"] > 0


class TestExtractionProvenance:
    """A reviewer must be able to check every extracted field against the notice."""

    def _notice_text(self):
        case = json.loads(
            (GOLDEN / "gst-asmt10-multilimb-fy2324.json").read_text())
        return case["notice_text"]

    def test_extraction_returns_a_snippet_for_each_local_field(self, client):
        response = client.post(
            "/api/panel/extract?tier=pro",
            files=[("files", ("notice.txt", self._notice_text().encode(),
                              "text/plain"))],
            headers=HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["snippets"].get("gstin", {}).get("text")
        assert data["fields"]["gstin"] in data["snippets"]["gstin"]["text"]

    def test_a_text_layer_notice_is_not_reported_as_scanned(self, client):
        data = client.post(
            "/api/panel/extract?tier=pro",
            files=[("files", ("notice.txt", self._notice_text().encode(),
                              "text/plain"))],
            headers=HEADERS,
        ).json()
        assert data["scanned"] is False
        assert not any(str(s).endswith("-ocr") for s in data["sources"].values())

    def test_every_limb_of_the_reference_notice_is_extracted(self, client):
        data = client.post(
            "/api/panel/extract?tier=pro",
            files=[("files", ("notice.txt", self._notice_text().encode(),
                              "text/plain"))],
            headers=HEADERS,
        ).json()
        assert len(data["fields"]["defects"]) == 8
        assert data["fields"]["amount_disputed"] == 317450
