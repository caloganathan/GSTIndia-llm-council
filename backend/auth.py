"""Authentication and authorisation.

Two credentials are accepted on the same header, which keeps the original
single-token deployment working while the firm moves to named users:

    Bearer <APP_ACCESS_TOKEN>   legacy shared secret, treated as partner
    Bearer <session token>      issued by POST /api/auth/login

When neither APP_ACCESS_TOKEN nor any user account exists, auth is disabled
entirely — localhost development only.
"""

import secrets
from typing import Any, Dict, Optional

from fastapi import Header, HTTPException

from . import config, users

LEGACY_USER = {
    "id": "legacy-token",
    "email": "shared-token",
    "name": "Shared Access Token",
    "role": "partner",
    "active": True,
    "permissions": users.ROLE_PERMISSIONS["partner"],
}

ANONYMOUS_USER = {
    "id": "anonymous",
    "email": "local",
    "name": "Local User",
    "role": "partner",
    "active": True,
    "permissions": users.ROLE_PERMISSIONS["partner"],
}


def _extract_token(authorization: str) -> str:
    if not authorization:
        return ""
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return ""


def _auth_disabled() -> bool:
    """Auth is off only when there is no shared secret AND no user accounts."""
    if config.APP_ACCESS_TOKEN:
        return False
    try:
        return users.user_count() == 0
    except Exception:
        return True


def resolve_user(authorization: str = "") -> Optional[Dict[str, Any]]:
    """Return the user for this request, or None if unauthenticated."""
    if _auth_disabled():
        return dict(ANONYMOUS_USER)

    token = _extract_token(authorization)
    if not token:
        return None

    if config.APP_ACCESS_TOKEN and secrets.compare_digest(
        token, config.APP_ACCESS_TOKEN
    ):
        _warn_legacy_token_use()
        return dict(LEGACY_USER)

    return users.resolve_session(token)


_legacy_warned = False


def _warn_legacy_token_use():
    """
    Say, once, that the shared token was used.

    The shared secret grants partner rights to whoever holds it, attributes
    every action to "Shared Access Token", and cannot be revoked for one
    person. It stays supported because deployments depend on it, but a firm
    that has moved to named users should know when something is still using
    it — silence is how a breakglass credential becomes the normal way in.

    Once per process: this runs on every authenticated request, and a line per
    request would bury everything else in the log.
    """
    global _legacy_warned
    if _legacy_warned:
        return
    _legacy_warned = True
    try:
        named_users = users.user_count()
    except Exception:
        named_users = 0
    if named_users:
        print(
            "WARNING: the shared APP_ACCESS_TOKEN was used to authenticate "
            f"while {named_users} named user account(s) exist. Actions taken "
            "with it are attributed to 'Shared Access Token' and cannot be "
            "traced to a person. Prefer named logins and keep the shared "
            "token for recovery only."
        )


async def require_auth(authorization: str = Header(default="")) -> Dict[str, Any]:
    """FastAPI dependency: authenticate, or 401."""
    user = resolve_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or missing credentials")
    return user


def require_permission(permission: str):
    """Dependency factory enforcing a named permission."""

    async def _dependency(authorization: str = Header(default="")) -> Dict[str, Any]:
        user = resolve_user(authorization)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid or missing credentials")
        if not users.can(user, permission):
            raise HTTPException(
                status_code=403,
                detail=f"Your role ({user.get('role')}) does not permit this action",
            )
        return user

    return _dependency


def redact_for_role(payload: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Strip the raw counsel deliberation for roles that shouldn't see it.

    Staff get the determination and the verification trail — what they need to
    act — but not the firm's internal argument, which is privileged working
    material and easy to quote out of context.
    """
    if users.can(user, "view_deliberation"):
        return payload

    redacted = dict(payload)
    result = dict(redacted.get("result") or {})
    if result:
        result["analyses"] = []
        result["cross_exams"] = []
        result["_redacted"] = True
        redacted["result"] = result
    return redacted
