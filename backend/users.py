"""Users, roles and sessions.

Deliberately small: a JSON store, PBKDF2 password hashing from the standard
library, and opaque session tokens. No database, no external dependency. When
the product outgrows this it should move to Postgres — but a weekend build
that needs a migration tool is not a weekend build.

Roles map to how a firm actually works:
    partner  full deliberation, export, admin panel, user management
    manager  full deliberation and export, no admin
    staff    chairman determination and verification only — not the raw
             counsel arguments, which are the firm's internal reasoning
"""

import hashlib
import json
import os
import secrets
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from . import config

ROLES = ("partner", "manager", "staff")

ROLE_PERMISSIONS = {
    "partner": {
        "view_deliberation": True,
        "export": True,
        "admin": True,
        "manage_users": True,
        "view_costs": True,
        "delete_matters": True,
    },
    "manager": {
        "view_deliberation": True,
        "export": True,
        "admin": False,
        "manage_users": False,
        "view_costs": True,
        "delete_matters": True,
    },
    "staff": {
        "view_deliberation": False,
        "export": False,
        "admin": False,
        "manage_users": False,
        "view_costs": False,
        "delete_matters": False,
    },
}

SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "72"))

# OWASP's current floor for PBKDF2-HMAC-SHA256 is 600,000. The store held
# hashes at 240,000, and `verify_password` accepted whatever round count was
# embedded in the record — so a hash written at a weaker setting kept
# verifying indefinitely. Rounds below the floor are now rejected outright and
# the record is rehashed on the next successful login.
_PBKDF2_ROUNDS = 600_000
_PBKDF2_MINIMUM_ROUNDS = 200_000

# Failed-login backoff. The store holds PBKDF2 hashes and live session tokens,
# the bootstrap account has a predictable address, and each attempt costs a
# 600k-round hash — so an unthrottled login is both a credential oracle and a
# CPU amplifier. Counted per email AND per client address: per-email alone
# lets one attacker lock a partner out of their own account, per-address alone
# misses a distributed spray at one mailbox.
LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_LOCKOUT_SECONDS = int(os.getenv("LOGIN_LOCKOUT_SECONDS", "900"))


class LockedOut(Exception):
    """Raised when the failed-attempt budget for an email or client is spent."""

    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = max(int(retry_after_seconds), 1)
        super().__init__(
            f"Too many failed sign-in attempts. Try again in "
            f"{max(self.retry_after_seconds // 60, 1)} minute(s)."
        )


def _store_path() -> str:
    return os.path.join(config.STATE_DIR, "users.json")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _write_atomic(path: str, payload: Dict[str, Any]):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-users-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load() -> Dict[str, Any]:
    path = _store_path()
    if not os.path.exists(path):
        return {"users": [], "sessions": {}, "login_attempts": {}}
    try:
        with open(path) as f:
            data = json.load(f)
        data.setdefault("users", [])
        data.setdefault("sessions", {})
        data.setdefault("login_attempts", {})
        return data
    except (json.JSONDecodeError, OSError) as e:
        print(f"users.json unreadable ({e}); starting from empty store")
        return {"users": [], "sessions": {}, "login_attempts": {}}


def _save(data: Dict[str, Any]):
    _write_atomic(_store_path(), data)


def hash_password(password: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), _PBKDF2_ROUNDS
    ).hex()
    return f"pbkdf2${_PBKDF2_ROUNDS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    """
    Check a password against a stored hash.

    A record whose embedded round count is below the floor is REJECTED rather
    than verified. Without that check the round count in the record is
    attacker-controlled the moment the store is writable: a hash rewritten at
    one round verifies in microseconds, and the work factor becomes advisory.
    """
    try:
        scheme, rounds, salt, digest = stored.split("$")
        if scheme != "pbkdf2":
            return False
        if int(rounds) < _PBKDF2_MINIMUM_ROUNDS:
            print("Rejected a password hash stored below the PBKDF2 floor "
                  f"({rounds} rounds). Reset this account's password.")
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), int(rounds)
        ).hex()
        return secrets.compare_digest(candidate, digest)
    except (ValueError, AttributeError):
        return False


def _needs_rehash(stored: str) -> bool:
    """True when a verified hash was written at fewer rounds than we now use."""
    try:
        _, rounds, _, _ = str(stored).split("$")
        return int(rounds) < _PBKDF2_ROUNDS
    except (ValueError, AttributeError):
        return False


def hash_token(token: str) -> str:
    """
    Session tokens are stored hashed, never in clear.

    The store sat one directory traversal away from being readable, and a
    plaintext token is a live credential the moment the file is: no password
    needed, no lockout to trip, valid until it expires. A SHA-256 of a 256-bit
    random token needs no salt or stretching — there is nothing to guess.
    """
    return hashlib.sha256((token or "").encode()).hexdigest()


def _public(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user.get("name", ""),
        "role": user.get("role", "staff"),
        "active": user.get("active", True),
        "created_at": user.get("created_at"),
        "last_login": user.get("last_login"),
        "permissions": ROLE_PERMISSIONS.get(user.get("role", "staff"), {}),
    }


def list_users() -> List[Dict[str, Any]]:
    return [_public(u) for u in _load()["users"]]


def user_count() -> int:
    return len(_load()["users"])


def find_by_email(email: str) -> Optional[Dict[str, Any]]:
    email = (email or "").strip().lower()
    for user in _load()["users"]:
        if user["email"].lower() == email:
            return user
    return None


def create_user(email: str, password: str, name: str = "",
                role: str = "staff") -> Dict[str, Any]:
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("A valid email address is required")
    if len(password or "") < 8:
        raise ValueError("Password must be at least 8 characters")
    if role not in ROLES:
        raise ValueError(f"Role must be one of: {', '.join(ROLES)}")

    data = _load()
    if any(u["email"].lower() == email for u in data["users"]):
        raise ValueError("A user with that email already exists")

    user = {
        "id": secrets.token_urlsafe(9),
        "email": email,
        "name": name.strip(),
        "role": role,
        "password": hash_password(password),
        "active": True,
        "created_at": _now().isoformat(),
        "last_login": None,
    }
    data["users"].append(user)
    _save(data)
    return _public(user)


def update_user(user_id: str, *, role: str = None, active: bool = None,
                name: str = None, password: str = None) -> Dict[str, Any]:
    data = _load()
    for user in data["users"]:
        if user["id"] != user_id:
            continue
        if role is not None:
            if role not in ROLES:
                raise ValueError(f"Role must be one of: {', '.join(ROLES)}")
            # Never allow the last active partner to be demoted out of existence
            if user.get("role") == "partner" and role != "partner":
                partners = [u for u in data["users"]
                            if u.get("role") == "partner" and u.get("active", True)]
                if len(partners) <= 1:
                    raise ValueError("Cannot remove the last active partner")
            user["role"] = role
        if active is not None:
            if not active and user.get("role") == "partner":
                partners = [u for u in data["users"]
                            if u.get("role") == "partner" and u.get("active", True)]
                if len(partners) <= 1:
                    raise ValueError("Cannot deactivate the last active partner")
            user["active"] = bool(active)
        if name is not None:
            user["name"] = name.strip()
        if password:
            if len(password) < 8:
                raise ValueError("Password must be at least 8 characters")
            user["password"] = hash_password(password)
            # Every existing session for this user dies with the old password.
            # A password is changed either because it may be known to someone
            # else or because someone is being removed from a matter, and both
            # reasons are defeated by a session that keeps working. The user
            # signs in again with the new credential.
            data["sessions"] = {
                t: s for t, s in data["sessions"].items()
                if s.get("user_id") != user_id
            }
            # A password reset also clears the failed-attempt record, so an
            # account locked by an attacker is usable again immediately.
            _clear_failures(data, _attempt_keys(user.get("email", "")))
        _save(data)
        return _public(user)
    raise ValueError("User not found")


def delete_user(user_id: str) -> bool:
    data = _load()
    target = next((u for u in data["users"] if u["id"] == user_id), None)
    if target is None:
        return False
    if target.get("role") == "partner":
        partners = [u for u in data["users"] if u.get("role") == "partner"]
        if len(partners) <= 1:
            raise ValueError("Cannot delete the last partner")
    data["users"] = [u for u in data["users"] if u["id"] != user_id]
    data["sessions"] = {
        t: s for t, s in data["sessions"].items() if s.get("user_id") != user_id
    }
    _save(data)
    return True


def _attempt_keys(email: str, client: str = "") -> List[str]:
    keys = [f"email:{(email or '').strip().lower()}"]
    if client:
        keys.append(f"client:{client}")
    return keys


def _lockout_remaining(data: Dict[str, Any], keys: List[str]) -> int:
    """Seconds until the earliest key unlocks, or 0 if none is locked."""
    attempts = data.get("login_attempts") or {}
    now = _now()
    remaining = 0
    for key in keys:
        record = attempts.get(key) or {}
        if record.get("count", 0) < LOGIN_MAX_ATTEMPTS:
            continue
        locked_until = record.get("locked_until")
        if not locked_until:
            continue
        try:
            until = datetime.fromisoformat(locked_until)
        except (TypeError, ValueError):
            continue
        remaining = max(remaining, int((until - now).total_seconds()))
    return max(remaining, 0)


def _record_failure(data: Dict[str, Any], keys: List[str]):
    attempts = data.setdefault("login_attempts", {})
    now = _now()
    for key in keys:
        record = attempts.setdefault(key, {"count": 0, "locked_until": None})
        # A lock that has expired resets the counter, so a legitimate user who
        # mistyped twice last week does not start halfway to locked out.
        locked_until = record.get("locked_until")
        if locked_until:
            try:
                if datetime.fromisoformat(locked_until) <= now:
                    record["count"] = 0
                    record["locked_until"] = None
            except (TypeError, ValueError):
                record["count"] = 0
                record["locked_until"] = None
        record["count"] = record.get("count", 0) + 1
        record["last_failure"] = now.isoformat()
        if record["count"] >= LOGIN_MAX_ATTEMPTS:
            record["locked_until"] = (
                now + timedelta(seconds=LOGIN_LOCKOUT_SECONDS)).isoformat()


def _clear_failures(data: Dict[str, Any], keys: List[str]):
    attempts = data.get("login_attempts") or {}
    for key in keys:
        attempts.pop(key, None)


def authenticate(email: str, password: str,
                 client: str = "") -> Optional[Dict[str, Any]]:
    """
    Verify credentials and issue a session token.

    Returns None on a bad credential and raises `LockedOut` once the attempt
    budget is spent — the caller needs to distinguish them, because "wrong
    password" and "locked for 15 minutes" are different things to tell a
    partner who is trying to get into their own file on a deadline.
    """
    data = _load()
    email = (email or "").strip().lower()
    keys = _attempt_keys(email, client)

    remaining = _lockout_remaining(data, keys)
    if remaining:
        raise LockedOut(remaining)

    user = next((u for u in data["users"] if u["email"].lower() == email), None)

    if user is None or not user.get("active", True):
        # Constant-ish work whether or not the user exists
        hash_password(password or "x")
        _record_failure(data, keys)
        _save(data)
        return None
    if not verify_password(password or "", user["password"]):
        _record_failure(data, keys)
        _save(data)
        return None

    _clear_failures(data, keys)

    # A hash written at an older, lower round count is upgraded here — the one
    # moment the plaintext is available to rehash with.
    if _needs_rehash(user.get("password", "")):
        user["password"] = hash_password(password)

    token = secrets.token_urlsafe(32)
    data["sessions"][hash_token(token)] = {
        "user_id": user["id"],
        "created_at": _now().isoformat(),
        "expires_at": (_now() + timedelta(hours=SESSION_TTL_HOURS)).isoformat(),
    }
    user["last_login"] = _now().isoformat()
    # Prune expired sessions opportunistically
    data["sessions"] = {
        t: s for t, s in data["sessions"].items()
        if s.get("expires_at", "") > _now().isoformat()
    }
    _save(data)
    return {"token": token, "user": _public(user)}


def resolve_session(token: str) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    data = _load()
    session = data["sessions"].get(hash_token(token))
    if not session:
        return None
    if session.get("expires_at", "") <= _now().isoformat():
        return None
    user = next((u for u in data["users"] if u["id"] == session["user_id"]), None)
    if user is None or not user.get("active", True):
        return None
    return _public(user)


def revoke_session(token: str):
    data = _load()
    hashed = hash_token(token)
    if hashed in data["sessions"]:
        del data["sessions"][hashed]
        _save(data)


def bootstrap_admin() -> Optional[Dict[str, str]]:
    """
    Create the first partner account if no users exist.

    Credentials come from ADMIN_EMAIL / ADMIN_PASSWORD when supplied;
    otherwise a password is generated and printed once to the server log.
    """
    if user_count() > 0:
        return None

    email = os.getenv("ADMIN_EMAIL", "admin@firm.local").strip().lower()
    password = os.getenv("ADMIN_PASSWORD", "") or secrets.token_urlsafe(12)
    name = os.getenv("ADMIN_NAME", "Managing Partner")

    create_user(email, password, name=name, role="partner")
    print("=" * 68)
    print("  FIRST-RUN: partner account created")
    print(f"  Email:    {email}")
    print(f"  Password: {password}")
    print("  Change this password after first login (Admin > Users).")
    print("=" * 68)
    return {"email": email, "password": password}


def can(user: Optional[Dict[str, Any]], permission: str) -> bool:
    if not user:
        return False
    return bool(ROLE_PERMISSIONS.get(user.get("role", "staff"), {}).get(permission))
