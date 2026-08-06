"""Authentication hardening.

The user store holds PBKDF2 hashes AND live session tokens, and it sits one
directory above the matters. Each item here is a way that store, or an account
in it, was reachable with less work than it should have taken.
"""

import pytest
from fastapi.testclient import TestClient

from backend import config, users

TOKEN = "test-hardening-token"


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "conversations"))
    return tmp_path


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "APP_ACCESS_TOKEN", TOKEN)
    from backend.main import app
    return TestClient(app)


def _user(email="partner@firm.in", password="a-good-password", role="partner"):
    return users.create_user(email, password, name="Test", role=role)


class TestPasswordHashing:
    def test_new_hashes_use_the_current_round_count(self):
        stored = users.hash_password("a-good-password")
        assert stored.split("$")[1] == str(users._PBKDF2_ROUNDS)
        assert users._PBKDF2_ROUNDS >= 600_000

    def test_a_hash_below_the_floor_is_rejected_not_verified(self):
        """`verify_password` honoured whatever round count the record carried,
        so a record rewritten at one round verified in microseconds and the
        work factor became advisory."""
        import hashlib
        salt, password = "abcd", "a-good-password"
        weak_digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), 1).hex()
        weak = f"pbkdf2$1${salt}${weak_digest}"
        assert users.verify_password(password, weak) is False

    def test_a_legacy_hash_above_the_floor_still_verifies(self):
        """Existing accounts must not be locked out by the uplift."""
        import hashlib
        salt, password = "abcd", "a-good-password"
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), 240_000).hex()
        legacy = f"pbkdf2$240000${salt}${digest}"
        assert users.verify_password(password, legacy) is True

    def test_a_legacy_hash_is_rehashed_on_successful_login(self):
        import hashlib
        password = "a-good-password"
        _user(password=password)
        # Rewrite the stored hash at the old round count.
        data = users._load()
        salt = "abcd"
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), 240_000).hex()
        data["users"][0]["password"] = f"pbkdf2$240000${salt}${digest}"
        users._save(data)

        assert users.authenticate("partner@firm.in", password) is not None
        upgraded = users._load()["users"][0]["password"]
        assert upgraded.split("$")[1] == str(users._PBKDF2_ROUNDS)


class TestSessionTokensAreStoredHashed:
    def test_the_raw_token_never_appears_in_the_store(self, store):
        _user()
        session = users.authenticate("partner@firm.in", "a-good-password")
        raw = session["token"]
        assert raw not in (store / "users.json").read_text(), (
            "a plaintext session token in the store is a live credential the "
            "moment the file is readable — no password, no lockout"
        )

    def test_the_token_still_resolves(self):
        _user()
        session = users.authenticate("partner@firm.in", "a-good-password")
        assert users.resolve_session(session["token"])["email"] == "partner@firm.in"

    def test_revoking_uses_the_hash(self):
        _user()
        session = users.authenticate("partner@firm.in", "a-good-password")
        users.revoke_session(session["token"])
        assert users.resolve_session(session["token"]) is None

    def test_a_stored_hash_is_not_itself_a_usable_token(self):
        _user()
        session = users.authenticate("partner@firm.in", "a-good-password")
        stored_key = next(iter(users._load()["sessions"]))
        assert users.resolve_session(stored_key) is None


class TestPasswordChangeKillsSessions:
    def test_existing_sessions_die_with_the_old_password(self):
        user = _user()
        session = users.authenticate("partner@firm.in", "a-good-password")
        assert users.resolve_session(session["token"]) is not None

        users.update_user(user["id"], password="a-different-password")
        assert users.resolve_session(session["token"]) is None, (
            "a password is changed because it may be known to someone else; "
            "a session that outlives it defeats the reason for the change"
        )

    def test_other_users_sessions_survive(self):
        _user()
        other = _user("manager@firm.in", "another-password", "manager")
        keep = users.authenticate("manager@firm.in", "another-password")
        partner = users.find_by_email("partner@firm.in")
        users.update_user(partner["id"], password="a-different-password")
        assert users.resolve_session(keep["token"]) is not None


class TestLoginLockout:
    def test_the_attempt_budget_locks_the_account(self):
        _user()
        for _ in range(users.LOGIN_MAX_ATTEMPTS):
            assert users.authenticate("partner@firm.in", "wrong") is None
        with pytest.raises(users.LockedOut):
            users.authenticate("partner@firm.in", "a-good-password")

    def test_a_successful_login_clears_the_counter(self):
        _user()
        for _ in range(users.LOGIN_MAX_ATTEMPTS - 1):
            users.authenticate("partner@firm.in", "wrong")
        assert users.authenticate("partner@firm.in", "a-good-password")
        for _ in range(users.LOGIN_MAX_ATTEMPTS - 1):
            users.authenticate("partner@firm.in", "wrong")
        # Still under budget because the counter was reset.
        assert users.authenticate("partner@firm.in", "a-good-password")

    def test_an_unknown_email_is_also_throttled(self):
        """Otherwise the endpoint is an unlimited oracle for which addresses
        exist, and an unlimited 600k-round CPU sink."""
        for _ in range(users.LOGIN_MAX_ATTEMPTS):
            users.authenticate("nobody@firm.in", "wrong")
        with pytest.raises(users.LockedOut):
            users.authenticate("nobody@firm.in", "wrong")

    def test_a_password_reset_clears_a_lockout(self):
        user = _user()
        for _ in range(users.LOGIN_MAX_ATTEMPTS):
            users.authenticate("partner@firm.in", "wrong")
        users.update_user(user["id"], password="a-different-password")
        assert users.authenticate("partner@firm.in", "a-different-password")

    def test_the_api_answers_429_with_retry_after(self, client):
        _user()
        body = {"email": "partner@firm.in", "password": "wrong"}
        for _ in range(users.LOGIN_MAX_ATTEMPTS):
            assert client.post("/api/auth/login", json=body).status_code == 401
        locked = client.post("/api/auth/login", json=body)
        assert locked.status_code == 429
        assert "Retry-After" in locked.headers

    def test_a_correct_password_is_still_refused_while_locked(self, client):
        _user()
        for _ in range(users.LOGIN_MAX_ATTEMPTS):
            client.post("/api/auth/login",
                        json={"email": "partner@firm.in", "password": "wrong"})
        good = client.post("/api/auth/login",
                           json={"email": "partner@firm.in",
                                 "password": "a-good-password"})
        assert good.status_code == 429


class TestUnauthenticatedEndpointsDoNotDiscloseLayout:
    def test_readyz_does_not_leak_the_filesystem_or_auth_posture(self, client):
        body = client.get("/readyz").json()
        assert "state_dir" not in body
        assert "data_dir" not in body
        assert "auth_enabled" not in body.get("checks", {})
        # It must still say WHICH thing is degraded, or it is useless.
        assert "api_key_configured" in body["checks"]
        assert body["status"] in ("ready", "degraded")

    def test_the_detail_is_still_available_on_the_authenticated_health(self, client):
        body = client.get(
            "/api/health", headers={"Authorization": f"Bearer {TOKEN}"}).json()
        assert "state_dir" in body
        assert "auth_enabled" in body


class TestInternalComputationsAreGated:
    def _matter(self):
        from backend import storage
        return storage.create_matter(
            "m1", {"notice_type": "ASMT-10", "section_invoked": "73",
                   "tax_period": "FY 2019-20", "amount_disputed": 100000},
            "gst", "pro", None)

    def _login(self, client, role):
        users.create_user(f"{role}@firm.in", "a-good-password", role=role)
        r = client.post("/api/auth/login",
                        json={"email": f"{role}@firm.in",
                              "password": "a-good-password"})
        return {"Authorization": f"Bearer {r.json()['token']}"}

    def test_staff_cannot_read_the_exposure_arithmetic(self, client):
        self._matter()
        headers = self._login(client, "staff")
        assert client.get("/api/matters/m1/computations",
                          headers=headers).status_code == 403

    def test_a_manager_can(self, client):
        self._matter()
        headers = self._login(client, "manager")
        assert client.get("/api/matters/m1/computations",
                          headers=headers).status_code == 200
