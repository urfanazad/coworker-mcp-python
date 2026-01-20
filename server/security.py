from __future__ import annotations

import secrets
from typing import Optional
from fastapi import HTTPException
from .cp_store import CPStore

TOKEN_HEADER = "X-Coworker-Token"
SESSION_HEADER = "X-Coworker-Session"


def mint_token() -> str:
    return secrets.token_urlsafe(32)


def require_token(store: CPStore, session_id: Optional[str], token: Optional[str]) -> None:
    if not session_id or not token:
        raise HTTPException(status_code=401, detail="Missing session or token")

    expected = store.get_session_token(session_id)
    if expected is None or expected != token:
        raise HTTPException(status_code=403, detail="Invalid token")
