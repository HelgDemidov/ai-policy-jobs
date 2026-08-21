"""Tests for scripts/browser_resolver.py — see
docs/tech_specs/point-source-connectors/spec.md §1 for why it exists."""
import json
import subprocess

import browser_resolver
import pytest


def test_is_available_false_when_node_missing(monkeypatch, tmp_path):
    binary = tmp_path / "lightpanda"
    binary.touch()
    monkeypatch.setattr(browser_resolver, "LIGHTPANDA_BINARY", binary)
    monkeypatch.setattr(browser_resolver.shutil, "which", lambda _: None)
    assert browser_resolver.is_available() is False


def test_is_available_false_when_binary_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(browser_resolver, "LIGHTPANDA_BINARY", tmp_path / "does-not-exist")
    monkeypatch.setattr(browser_resolver.shutil, "which", lambda _: "/usr/bin/node")
    assert browser_resolver.is_available() is False


def test_is_available_true_when_both_present(monkeypatch, tmp_path):
    binary = tmp_path / "lightpanda"
    binary.touch()
    monkeypatch.setattr(browser_resolver, "LIGHTPANDA_BINARY", binary)
    monkeypatch.setattr(browser_resolver.shutil, "which", lambda _: "/usr/bin/node")
    assert browser_resolver.is_available() is True


def _mock_run(stdout: str, returncode: int = 0):
    def _run(*args, **kwargs):
        return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr="")
    return _run


def test_resolve_raises_when_unavailable(monkeypatch):
    monkeypatch.setattr(browser_resolver, "is_available", lambda: False)
    with pytest.raises(browser_resolver.BrowserResolverUnavailable):
        browser_resolver.resolve("https://example.com")


def test_resolve_returns_ok_result(monkeypatch):
    monkeypatch.setattr(browser_resolver, "is_available", lambda: True)
    payload = {"ok": True, "html": "<html>content</html>", "url": "https://example.com/final"}
    monkeypatch.setattr(browser_resolver.subprocess, "run", _mock_run(json.dumps(payload)))

    result = browser_resolver.resolve("https://example.com")
    assert result.ok is True
    assert result.html == "<html>content</html>"
    assert result.final_url == "https://example.com/final"


def test_resolve_returns_page_level_failure_not_exception(monkeypatch):
    monkeypatch.setattr(browser_resolver, "is_available", lambda: True)
    payload = {"ok": False, "error": "navigation timeout"}
    monkeypatch.setattr(browser_resolver.subprocess, "run", _mock_run(json.dumps(payload)))

    result = browser_resolver.resolve("https://example.com")
    assert result.ok is False
    assert result.error == "navigation timeout"
    assert result.html == ""


def test_resolve_raises_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(browser_resolver, "is_available", lambda: True)
    monkeypatch.setattr(browser_resolver.subprocess, "run", _mock_run("", returncode=1))
    with pytest.raises(browser_resolver.BrowserResolverUnavailable):
        browser_resolver.resolve("https://example.com")


def test_resolve_raises_on_invalid_json(monkeypatch):
    monkeypatch.setattr(browser_resolver, "is_available", lambda: True)
    monkeypatch.setattr(browser_resolver.subprocess, "run", _mock_run("not json"))
    with pytest.raises(browser_resolver.BrowserResolverUnavailable):
        browser_resolver.resolve("https://example.com")


def test_resolve_raises_on_timeout(monkeypatch):
    monkeypatch.setattr(browser_resolver, "is_available", lambda: True)

    def _timeout_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="node", timeout=45)

    monkeypatch.setattr(browser_resolver.subprocess, "run", _timeout_run)
    with pytest.raises(browser_resolver.BrowserResolverUnavailable):
        browser_resolver.resolve("https://example.com")


def test_resolve_passes_frame_url_contains_as_extra_arg(monkeypatch):
    monkeypatch.setattr(browser_resolver, "is_available", lambda: True)
    captured = {}

    def _run(args, **kwargs):
        captured["args"] = args
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps({"ok": True, "html": "", "url": ""}), stderr="")

    monkeypatch.setattr(browser_resolver.subprocess, "run", _run)
    browser_resolver.resolve("https://example.com", frame_url_contains="in_iframe=1")
    assert captured["args"][-1] == "in_iframe=1"
