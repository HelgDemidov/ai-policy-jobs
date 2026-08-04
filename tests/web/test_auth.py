"""Tests for web/api/_auth.py."""
import _auth
import pytest


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("SITE_PASSWORD", "correct-horse")


def test_check_password_accepts_correct_password():
    assert _auth.check_password("correct-horse") is True


def test_check_password_rejects_wrong_password():
    assert _auth.check_password("wrong") is False


def test_is_authenticated_accepts_matching_cookie():
    assert _auth.is_authenticated("site_auth=correct-horse") is True


def test_is_authenticated_rejects_missing_cookie_header():
    assert _auth.is_authenticated(None) is False


def test_is_authenticated_rejects_wrong_cookie_value():
    assert _auth.is_authenticated("site_auth=wrong") is False


def test_is_authenticated_rejects_when_auth_cookie_absent_among_others():
    assert _auth.is_authenticated("other=1; another=2") is False


def test_is_authenticated_finds_cookie_among_multiple():
    assert _auth.is_authenticated("other=1; site_auth=correct-horse; another=2") is True


def test_missing_site_password_env_raises(monkeypatch):
    monkeypatch.delenv("SITE_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="SITE_PASSWORD"):
        _auth.check_password("anything")
