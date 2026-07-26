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
_PBKDF2_ROUNDS = 240_000


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
        return {"users": [], "sessions": {}}
    try:
        with open(path) as f:
            data = json.load(f)
        data.setdefault("users", [])
        data.setdefault("sessions", {})
        return data
    except (json.JSONDecodeError, OSError) as e:
        print(f"users.json unreadable ({e}); starting from empty store")
        return {"users": [], "sessions": {}}


def _save(data: Dict[str, Any]):
    _write_atomic(_store_path(), data)


def hash_password(password: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), _PBKDF2_ROUNDS
    ).hex()
    return f"pbkdf2${_PBKDF2_ROUNDS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, rounds, salt, digest = stored.split("$")
        if scheme != "pbkdf2":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), int(rounds)
        ).hex()
        return secrets.compare_digest(candidate, digest)
    except (ValueError, AttributeError):
        return False


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


def authenticate(email: str, password: str) -> Optional[Dict[str, Any]]:
    """Verify credentials and issue a session token."""
    data = _load()
    email = (email or "").strip().lower()
    user = next((u for u in data["users"] if u["email"].lower() == email), None)

    if user is None or not user.get("active", True):
        # Constant-ish work whether or not the user exists
        hash_password(password or "x")
        return None
    if not verify_password(password or "", user["password"]):
        return None

    token = secrets.token_urlsafe(32)
    data["sessions"][token] = {
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
    session = data["sessions"].get(token)
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
    if token in data["sessions"]:
        del data["sessions"][token]
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
