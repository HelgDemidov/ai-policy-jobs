"""Shared-secret gate (spec: docs/tech_specs/web-auth-hardening/spec.md) —
the cookie carries a revocable HMAC session token, not SITE_PASSWORD
itself, so a leaked cookie no longer equals a leaked master credential.
Login-attempt lockout lives in the same module (see check_login).

Session state is one global row (auth_state, id=1) in Postgres rather
than a per-session table: at single-curator scale there's no meaningful
"log out just this device," so an O(1) `epoch` counter fully covers the
"revoke every outstanding token without rotating SITE_PASSWORD" goal —
bumping it (see bump_epoch) invalidates every token issued before it.
"""
import hashlib
import hmac
import os
import time

from sqlalchemy import func, select

import _schema

COOKIE_NAME = "site_auth"
# 30 days — a personal single-curator tool, not worth re-prompting often.
# Single source of truth for both the cookie's own Max-Age (login.py) and
# the server-side issued_at check below — two independently-declared
# constants of the same meaning is exactly the drift bug already caught
# once on this project (MAX_SIZE/FACET_SIZE, web-postgres-migration spec).
MAX_AGE_SECONDS = 60 * 60 * 24 * 30

_LOCKOUT_THRESHOLD = 10
_LOCKOUT_SECONDS = 60 * 15


def _secret() -> str:
    secret = os.environ.get("SITE_PASSWORD")
    if not secret:
        raise RuntimeError("SITE_PASSWORD not set in the function's environment")
    return secret


def check_password(password: str) -> bool:
    return hmac.compare_digest(password, _secret())


def _get_or_create_state(engine) -> dict:
    """The single auth_state row (id=1), inserted with defaults on first
    read. No upsert/on-conflict — a portable Core insert keeps this
    working identically against SQLite (tests) and Postgres (prod); a
    concurrent first-ever insert racing here is not a realistic scenario
    at single-curator request volume."""
    auth_state = _schema.auth_state
    with engine.begin() as conn:
        row = conn.execute(select(auth_state).where(auth_state.c.id == 1)).mappings().first()
        if row is None:
            conn.execute(auth_state.insert().values(id=1))
            row = conn.execute(select(auth_state).where(auth_state.c.id == 1)).mappings().first()
        return dict(row)


def _sign(epoch: int, issued_at: int) -> str:
    payload = f"{epoch}.{issued_at}".encode()
    return hmac.new(_secret().encode(), payload, hashlib.sha256).hexdigest()


def issue_token(engine, now: float | None = None) -> str:
    state = _get_or_create_state(engine)
    issued_at = int(now if now is not None else time.time())
    epoch = state["epoch"]
    return f"{epoch}.{issued_at}.{_sign(epoch, issued_at)}"


def _extract_cookie(cookie_header: str | None) -> str | None:
    if not cookie_header:
        return None
    for part in cookie_header.split(";"):
        name, _, value = part.strip().partition("=")
        if name == COOKIE_NAME:
            return value
    return None


def is_authenticated(cookie_header: str | None, engine, now: float | None = None) -> bool:
    token = _extract_cookie(cookie_header)
    if not token:
        return False
    parts = token.split(".")
    if len(parts) != 3:
        return False
    epoch_str, issued_at_str, signature = parts
    try:
        epoch, issued_at = int(epoch_str), int(issued_at_str)
    except ValueError:
        return False
    if not hmac.compare_digest(signature, _sign(epoch, issued_at)):
        return False
    state = _get_or_create_state(engine)
    if epoch != state["epoch"]:
        return False
    now = now if now is not None else time.time()
    return now - issued_at <= MAX_AGE_SECONDS


def bump_epoch(engine) -> None:
    auth_state = _schema.auth_state
    _get_or_create_state(engine)
    with engine.begin() as conn:
        conn.execute(
            auth_state.update()
            .where(auth_state.c.id == 1)
            .values(epoch=auth_state.c.epoch + 1, updated_at=func.now())
        )
