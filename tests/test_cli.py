"""Admin CLI tests.

This is the escape hatch for exactly the situation that motivated it: the
first-run partner account was created with an email or password the operator
never captured, and they need a way back in without redeploying or wiping
state.
"""

import importlib

import pytest

from backend import cli, users


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(users.config, "STATE_DIR", str(tmp_path))
    yield


class TestCreateAdmin:
    def test_creates_a_partner_by_default(self, capsys):
        code = cli.main(["create-admin", "--email", "partner@firm.in",
                         "--password", "adequatelength"])
        assert code == 0
        assert "Created partner account" in capsys.readouterr().out

        user = users.find_by_email("partner@firm.in")
        assert user["role"] == "partner"

    def test_can_create_other_roles(self):
        cli.main(["create-admin", "--email", "staff@firm.in",
                 "--password", "adequatelength", "--role", "staff"])
        assert users.find_by_email("staff@firm.in")["role"] == "staff"

    def test_duplicate_email_errors_cleanly(self, capsys):
        cli.main(["create-admin", "--email", "dup@firm.in",
                 "--password", "adequatelength"])
        code = cli.main(["create-admin", "--email", "dup@firm.in",
                        "--password", "adequatelength"])
        assert code == 1
        assert "already exists" in capsys.readouterr().err

    def test_short_password_rejected(self, capsys):
        code = cli.main(["create-admin", "--email", "x@firm.in",
                        "--password", "short"])
        assert code == 1
        assert "at least 8 characters" in capsys.readouterr().err
        assert users.find_by_email("x@firm.in") is None


class TestResetPassword:
    def test_resets_and_new_password_works(self):
        cli.main(["create-admin", "--email", "p@firm.in",
                 "--password", "originalpassword"])
        code = cli.main(["reset-password", "--email", "p@firm.in",
                        "--password", "brandnewpassword"])
        assert code == 0

        session = users.authenticate("p@firm.in", "brandnewpassword")
        assert session is not None
        assert users.authenticate("p@firm.in", "originalpassword") is None

    def test_unknown_email_errors_cleanly(self, capsys):
        code = cli.main(["reset-password", "--email", "nobody@firm.in",
                        "--password", "adequatelength"])
        assert code == 1
        assert "no user with email" in capsys.readouterr().err


class TestSetRole:
    def test_promotes_and_demotes(self):
        cli.main(["create-admin", "--email", "a@firm.in",
                 "--password", "adequatelength"])
        cli.main(["create-admin", "--email", "b@firm.in",
                 "--password", "adequatelength", "--role", "staff"])
        code = cli.main(["set-role", "--email", "b@firm.in", "--role", "manager"])
        assert code == 0
        assert users.find_by_email("b@firm.in")["role"] == "manager"

    def test_cannot_demote_the_last_partner(self, capsys):
        cli.main(["create-admin", "--email", "only@firm.in",
                 "--password", "adequatelength"])
        code = cli.main(["set-role", "--email", "only@firm.in", "--role", "staff"])
        assert code == 1
        assert "last active partner" in capsys.readouterr().err


class TestListUsers:
    def test_empty_store(self, capsys):
        code = cli.main(["list-users"])
        assert code == 0
        assert "No users" in capsys.readouterr().out

    def test_lists_created_users(self, capsys):
        cli.main(["create-admin", "--email", "one@firm.in",
                 "--password", "adequatelength"])
        cli.main(["create-admin", "--email", "two@firm.in",
                 "--password", "adequatelength", "--role", "staff"])
        code = cli.main(["list-users"])
        out = capsys.readouterr().out
        assert code == 0
        assert "one@firm.in" in out
        assert "two@firm.in" in out


class TestOperatesOnTheRealStore:
    """The whole point: this must touch the same store the running app reads."""

    def test_created_user_can_log_in_through_the_app(self):
        cli.main(["create-admin", "--email", "live@firm.in",
                 "--password", "adequatelength"])

        from backend.main import app
        from fastapi.testclient import TestClient

        with TestClient(app) as client:
            response = client.post("/api/auth/login", json={
                "email": "live@firm.in", "password": "adequatelength",
            })
        assert response.status_code == 200
        assert response.json()["user"]["role"] == "partner"
