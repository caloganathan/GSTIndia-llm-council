"""The live panel stream is redacted per reader, exactly as the stored matter is.

`GET /api/matters/{id}` strips the counsel deliberation for staff. Before this
suite existed, `POST /api/panel/run` did not: a staff user who RAN the matter
received the full privileged deliberation over SSE, and the only thing hiding
it was the browser UI. Redaction is a property of the reader, not of the
matter — the full record is still persisted for the roles entitled to it.
"""

import json

import pytest
from fastapi.testclient import TestClient

from backend import config, storage, users

TOKEN = "test-stream-token"
PARTNER_HEADERS = {"Authorization": f"Bearer {TOKEN}"}

PRIVILEGED = "PRIVILEGED-COUNSEL-ARGUMENT"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_ACCESS_TOKEN", TOKEN)
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "conversations"))
    monkeypatch.setattr(config, "STATE_DIR", str(tmp_path))
    from backend.main import app
    return TestClient(app)


@pytest.fixture
def staff_headers(client):
    users.create_user("staff@firm.in", "a-password", name="Staff", role="staff")
    response = client.post(
        "/api/auth/login",
        json={"email": "staff@firm.in", "password": "a-password"},
    )
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _fake_stream(monkeypatch):
    """A panel run reduced to the three events that carry deliberation."""
    async def fake(*args, **kwargs):
        yield {"type": "stage1_complete",
               "data": [{"key": "revenue", "analysis": PRIVILEGED}],
               "failures": []}
        yield {"type": "stage2_complete",
               "data": [{"key": "revenue", "analysis": PRIVILEGED}],
               "failures": []}
        yield {"type": "summary",
               "data": {
                   "analyses": [{"key": "revenue", "analysis": PRIVILEGED}],
                   "cross_exams": [{"key": "risk", "analysis": PRIVILEGED}],
                   "determination": {"recommended_position": "Contest.",
                                     "defects": []},
                   "verification": {"checked": False, "authorities": []},
               },
               "metadata": {"tier": "pro"}}

    from backend import main as main_module
    monkeypatch.setattr(main_module, "run_panel_stream", fake)


def _run(client, headers):
    response = client.post(
        "/api/panel/run",
        json={"intake": {"notice_type": "ASMT-10"}, "domain": "gst"},
        headers=headers,
    )
    assert response.status_code == 200
    return response.text


def _matter_id(stream_text):
    for line in stream_text.splitlines():
        if line.startswith("data: "):
            event = json.loads(line[6:])
            if event.get("type") == "matter_created":
                return event["matter_id"]
    raise AssertionError("no matter_created event in stream")


class TestStreamRedaction:
    def test_staff_stream_carries_no_deliberation(
            self, client, staff_headers, monkeypatch):
        _fake_stream(monkeypatch)
        text = _run(client, staff_headers)
        assert PRIVILEGED not in text

    def test_staff_stream_still_carries_the_determination(
            self, client, staff_headers, monkeypatch):
        """Staff get what they need to act — the determination and the
        verification trail — just not the firm's internal argument."""
        _fake_stream(monkeypatch)
        text = _run(client, staff_headers)
        assert "recommended_position" in text
        assert '"_redacted": true' in text

    def test_partner_stream_is_not_redacted(self, client, monkeypatch):
        _fake_stream(monkeypatch)
        text = _run(client, PARTNER_HEADERS)
        assert PRIVILEGED in text

    def test_the_stored_matter_keeps_the_full_record(
            self, client, staff_headers, monkeypatch):
        """Redaction is per reader, never per matter: the matter a staff user
        ran must still hold the deliberation for the partner who reviews it."""
        _fake_stream(monkeypatch)
        matter_id = _matter_id(_run(client, staff_headers))
        matter = storage.get_matter(matter_id)
        assert matter["result"]["analyses"][0]["analysis"] == PRIVILEGED

    def test_stage_failures_still_reach_staff(
            self, client, staff_headers, monkeypatch):
        """Operational signal is not privilege: a staff user watching the run
        must still see that a counsel seat failed."""
        async def fake(*args, **kwargs):
            yield {"type": "stage1_complete",
                   "data": [{"key": "revenue", "analysis": PRIVILEGED}],
                   "failures": [{"role": "Assessee's Advocate",
                                 "error": "model unavailable"}]}

        from backend import main as main_module
        monkeypatch.setattr(main_module, "run_panel_stream", fake)
        text = _run(client, staff_headers)
        assert "model unavailable" in text
        assert PRIVILEGED not in text
