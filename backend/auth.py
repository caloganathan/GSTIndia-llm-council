"""Bearer-token auth for the API.

A single shared secret (APP_ACCESS_TOKEN) protects every /api route. When the
variable is unset, auth is disabled — intended only for localhost use.
"""

import secrets

from fastapi import Header, HTTPException

from . import config


async def require_auth(authorization: str = Header(default="")) -> None:
    if not config.APP_ACCESS_TOKEN:
        return

    expected = f"Bearer {config.APP_ACCESS_TOKEN}"
    if not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing access token")
