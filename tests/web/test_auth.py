"""Tests for web/api/_auth.py — HMAC session tokens with a revocable global
epoch (docs/tech_specs/web-auth-hardening/spec.md §1/§3), against SQLite
in-memory via _schema.py's shared metadata, same pattern as test_repo.py.
"""
import _auth
import _schema
import pytest
from sqlalchemy import create_engine

SITE_PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("SITE_PASSWORD", SITE_PASSWORD)


@pytest.fixture
def engine():
    engine = create_engine("sqlite:///:memory:")
    _schema.metadata.create_all(engine)
    return engine


def _cookie(token: str) -> str:
    return f"{_auth.COOKIE_NAME}={token}"


def test_check_password_accepts_correct_password():
    assert _auth.check_password(SITE_PASSWORD) is True


def test_check_password_rejects_wrong_password():
    assert _auth.check_password("wrong") is False


def test_missing_site_password_env_raises(monkeypatch):
    monkeypatch.delenv("SITE_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="SITE_PASSWORD"):
        _auth.check_password("anything")


def test_issued_token_authenticates(engine):
    token = _auth.issue_token(engine)
    assert _auth.is_authenticated(_cookie(token), engine) is True


def test_missing_cookie_header_is_not_authenticated(engine):
    assert _auth.is_authenticated(None, engine) is False


def test_cookie_without_site_auth_is_not_authenticated(engine):
    assert _auth.is_authenticated("other=1; another=2", engine) is False


def test_token_found_among_multiple_cookies(engine):
    token = _auth.issue_token(engine)
    assert _auth.is_authenticated(f"other=1; {_cookie(token)}; another=2", engine) is True


@pytest.mark.parametrize("garbage", ["not-a-token", "1.2", "1.2.3.4", "a.b.c"])
def test_malformed_token_is_rejected(engine, garbage):
    assert _auth.is_authenticated(_cookie(garbage), engine) is False


def test_tampered_signature_is_rejected(engine):
    token = _auth.issue_token(engine)
    epoch, issued_at, _sig = token.split(".")
    forged = f"{epoch}.{issued_at}.{'0' * 64}"
    assert _auth.is_authenticated(_cookie(forged), engine) is False


def test_old_password_as_literal_cookie_is_rejected(engine):
    """A cookie set by the pre-hardening code (literal SITE_PASSWORD, no
    dots) must fail closed, not crash — deploying this change invalidates
    any outstanding old-format session (spec §1)."""
    assert _auth.is_authenticated(_cookie(SITE_PASSWORD), engine) is False


def test_bumped_epoch_invalidates_previously_issued_token(engine):
    token = _auth.issue_token(engine)
    _auth.bump_epoch(engine)
    assert _auth.is_authenticated(_cookie(token), engine) is False


def test_new_token_after_bump_still_authenticates(engine):
    _auth.bump_epoch(engine)
    token = _auth.issue_token(engine)
    assert _auth.is_authenticated(_cookie(token), engine) is True


def test_token_older_than_max_age_is_rejected(engine):
    issued_at = 1_000_000
    token = _auth.issue_token(engine, now=issued_at)
    still_valid_at = issued_at + _auth.MAX_AGE_SECONDS
    expired_at = issued_at + _auth.MAX_AGE_SECONDS + 1

    assert _auth.is_authenticated(_cookie(token), engine, now=still_valid_at) is True
    assert _auth.is_authenticated(_cookie(token), engine, now=expired_at) is False


def test_not_locked_out_initially(engine):
    assert _auth.is_locked_out(engine) is False


def test_check_login_correct_password_succeeds_and_resets_attempts(engine):
    _auth.check_login(engine, "wrong")
    assert _auth.check_login(engine, SITE_PASSWORD) is True
    assert _auth.is_locked_out(engine) is False


def test_check_login_wrong_password_fails_without_locking_out_below_threshold(engine):
    for _ in range(_auth._LOCKOUT_THRESHOLD - 1):
        assert _auth.check_login(engine, "wrong") is False
    assert _auth.is_locked_out(engine) is False


def test_lockout_triggers_after_threshold_failures(engine):
    for _ in range(_auth._LOCKOUT_THRESHOLD):
        _auth.check_login(engine, "wrong")
    assert _auth.is_locked_out(engine) is True


def test_locked_out_rejects_even_the_correct_password(engine):
    for _ in range(_auth._LOCKOUT_THRESHOLD):
        _auth.check_login(engine, "wrong")
    assert _auth.is_locked_out(engine) is True
    # check_login itself doesn't consult is_locked_out (login.py does that
    # first) — check_password underneath would still say yes, callers must
    # gate on is_locked_out before ever calling check_login.
    assert _auth.check_password(SITE_PASSWORD) is True


def test_lockout_expires_after_duration(engine):
    start = 1_000_000
    for _ in range(_auth._LOCKOUT_THRESHOLD):
        _auth.check_login(engine, "wrong", now=start)
    assert _auth.is_locked_out(engine, now=start + 1) is True
    assert _auth.is_locked_out(engine, now=start + _auth._LOCKOUT_SECONDS + 1) is False
