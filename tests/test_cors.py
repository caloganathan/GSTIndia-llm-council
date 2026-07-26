"""Split-deployment CORS.

Only relevant when the UI is served from a different host to the API. In the
single-service deployment the bundle is same-origin and CORS never applies —
which is why the default list stays limited to localhost, and opening it up is
something a deployment does deliberately.
"""

import importlib

import pytest
from fastapi.testclient import TestClient


def _client(monkeypatch, origins, previews=False):
    monkeypatch.setenv("CORS_ORIGINS", ",".join(origins))
    monkeypatch.setenv("CORS_ALLOW_VERCEL_PREVIEWS", "true" if previews else "false")
    import backend.config as config
    import backend.main as main
    importlib.reload(config)
    importlib.reload(main)
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def _restore():
    yield
    import backend.config as config
    import backend.main as main
    importlib.reload(config)
    importlib.reload(main)


def _preflight(client, origin):
    return client.options(
        "/api/matters",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )


class TestConfiguredOrigins:
    def test_listed_origin_allowed(self, monkeypatch):
        client = _client(monkeypatch, ["https://council.vercel.app"])
        response = _preflight(client, "https://council.vercel.app")
        assert response.headers.get("access-control-allow-origin") == \
            "https://council.vercel.app"

    def test_unlisted_origin_refused(self, monkeypatch):
        client = _client(monkeypatch, ["https://council.vercel.app"])
        response = _preflight(client, "https://evil.example.com")
        assert "access-control-allow-origin" not in response.headers

    def test_multiple_origins(self, monkeypatch):
        origins = ["https://a.vercel.app", "https://council.yourfirm.in"]
        client = _client(monkeypatch, origins)
        for origin in origins:
            assert _preflight(client, origin).headers.get(
                "access-control-allow-origin") == origin

    def test_credentials_permitted_for_bearer_tokens(self, monkeypatch):
        client = _client(monkeypatch, ["https://council.vercel.app"])
        response = _preflight(client, "https://council.vercel.app")
        assert response.headers.get("access-control-allow-credentials") == "true"


class TestVercelPreviews:
    """Vercel mints a hostname per deployment; listing them is not workable."""

    def test_preview_allowed_when_enabled(self, monkeypatch):
        client = _client(monkeypatch, ["https://council.vercel.app"], previews=True)
        origin = "https://council-git-feature-abc123.vercel.app"
        assert _preflight(client, origin).headers.get(
            "access-control-allow-origin") == origin

    def test_preview_refused_when_disabled(self, monkeypatch):
        client = _client(monkeypatch, ["https://council.vercel.app"], previews=False)
        response = _preflight(client, "https://council-git-feature.vercel.app")
        assert "access-control-allow-origin" not in response.headers

    def test_lookalike_domain_refused(self, monkeypatch):
        """The regex must not admit vercel.app.attacker.com."""
        client = _client(monkeypatch, [], previews=True)
        response = _preflight(client, "https://vercel.app.attacker.com")
        assert "access-control-allow-origin" not in response.headers


class TestDefaults:
    def test_localhost_allowed_out_of_the_box(self, monkeypatch):
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
        import backend.config as config
        importlib.reload(config)
        assert "http://localhost:5173" in config.CORS_ORIGINS

    def test_no_wildcard_by_default(self, monkeypatch):
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
        import backend.config as config
        importlib.reload(config)
        assert "*" not in config.CORS_ORIGINS
