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
from datetime import datetime, timedelta, timezone

import _schema
from sqlalchemy import func, select

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


def _now_dt(now: float | None) -> datetime:
    if now is not None:
        return datetime.fromtimestamp(now, tz=timezone.utc)
    return datetime.now(timezone.utc)


def _as_aware_utc(value: datetime | None) -> datetime | None:
    """SQLite has no native timezone-aware storage, so a DateTime(timezone=
    True) column round-trips as naive there even though Postgres returns it
    aware — normalize both to aware-UTC before comparing, rather than
    picking a column type that dodges the question."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def is_locked_out(engine, now: float | None = None) -> bool:
    state = _get_or_create_state(engine)
    locked_until = _as_aware_utc(state["locked_until"])
    if locked_until is None:
        return False
    return _now_dt(now) < locked_until


def check_login(engine, password: str, now: float | None = None) -> bool:
    """The rate-limited entry point for POST /api/login (spec §4) — records
    the attempt (success resets the failure counter; failure increments it
    and locks out after _LOCKOUT_THRESHOLD consecutive misses) and reports
    whether the password was correct. Does not itself consult
    is_locked_out — call that first so the caller can return 429 (locked)
    instead of 401 (wrong password) without a second lockout check here.
    Global counter, not per-IP: Vercel Functions don't hand out a
    trustworthy client IP without a dedicated proxy config, and a per-IP
    table would grow unboundedly for no benefit at single-curator scale."""
    if check_password(password):
        _reset_attempts(engine)
        return True
    _record_failed_attempt(engine, now)
    return False


def _reset_attempts(engine) -> None:
    auth_state = _schema.auth_state
    _get_or_create_state(engine)
    with engine.begin() as conn:
        conn.execute(
            auth_state.update()
            .where(auth_state.c.id == 1)
            .values(failed_attempts=0, locked_until=None, updated_at=func.now())
        )


def _record_failed_attempt(engine, now: float | None = None) -> None:
    auth_state = _schema.auth_state
    state = _get_or_create_state(engine)
    attempts = state["failed_attempts"] + 1
    values = {"failed_attempts": attempts, "updated_at": func.now()}
    if attempts >= _LOCKOUT_THRESHOLD:
        values["locked_until"] = _now_dt(now) + timedelta(seconds=_LOCKOUT_SECONDS)
    with engine.begin() as conn:
        conn.execute(auth_state.update().where(auth_state.c.id == 1).values(**values))
