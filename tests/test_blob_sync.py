"""Tests for scripts/blob_sync.py. subprocess.run is monkeypatched everywhere
— no real `vercel` CLI invocation, no network."""
import subprocess

import blob_sync
import pytest


class _FakeResult:
    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr


def test_download_calls_correct_cli_flags(monkeypatch, tmp_path):
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "test-token")
    calls = {}

    def fake_run(args, **kwargs):
        calls["args"] = args
        calls["env"] = kwargs["env"]
        return _FakeResult()

    monkeypatch.setattr(subprocess, "run", fake_run)
    dest = tmp_path / "jobs.db"

    blob_sync.download(dest)

    assert calls["args"] == ["vercel", "blob", "get", "jobs.db", "--access", "private", "-o", str(dest)]


def test_upload_calls_correct_cli_flags(monkeypatch, tmp_path):
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "test-token")
    calls = {}

    def fake_run(args, **kwargs):
        calls["args"] = args
        return _FakeResult()

    monkeypatch.setattr(subprocess, "run", fake_run)
    src = tmp_path / "jobs.db"
    src.write_text("fake db")

    blob_sync.upload(src)

    assert calls["args"] == [
        "vercel", "blob", "put", str(src),
        "--access", "private",
        "--pathname", "jobs.db",
        "--allow-overwrite",
    ]


def test_cli_error_is_not_silenced(monkeypatch, tmp_path):
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "test-token")
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _FakeResult(returncode=1, stderr="store not found"))

    with pytest.raises(RuntimeError, match="store not found"):
        blob_sync.download(tmp_path / "jobs.db")


def test_blob_store_id_stripped_from_subprocess_env(monkeypatch, tmp_path):
    """Live-verified 2026-08-04: the CLI treats BLOB_STORE_ID being set
    (without a matching VERCEL_OIDC_TOKEN) as a request to authenticate via
    OIDC instead of the read-write token, and errors out. .env in this repo
    sets both — the subprocess env must not inherit BLOB_STORE_ID."""
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "test-token")
    monkeypatch.setenv("BLOB_STORE_ID", "store_should_not_reach_subprocess")
    captured_env = {}

    def fake_run(args, **kwargs):
        captured_env.update(kwargs["env"])
        return _FakeResult()

    monkeypatch.setattr(subprocess, "run", fake_run)

    blob_sync.download(tmp_path / "jobs.db")

    assert "BLOB_STORE_ID" not in captured_env
    assert captured_env["BLOB_READ_WRITE_TOKEN"] == "test-token"


def test_token_from_env_file_fallback(monkeypatch, tmp_path):
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("BLOB_READ_WRITE_TOKEN=file-token\n")
    monkeypatch.setattr(blob_sync, "ENV_PATH", env_file)
    captured_env = {}

    def fake_run(args, **kwargs):
        captured_env.update(kwargs["env"])
        return _FakeResult()

    monkeypatch.setattr(subprocess, "run", fake_run)

    blob_sync.download(tmp_path / "jobs.db")

    assert captured_env["BLOB_READ_WRITE_TOKEN"] == "file-token"


def test_real_env_var_takes_priority_over_env_file(monkeypatch, tmp_path):
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "real-env-token")
    env_file = tmp_path / ".env"
    env_file.write_text("BLOB_READ_WRITE_TOKEN=file-token\n")
    monkeypatch.setattr(blob_sync, "ENV_PATH", env_file)
    captured_env = {}

    def fake_run(args, **kwargs):
        captured_env.update(kwargs["env"])
        return _FakeResult()

    monkeypatch.setattr(subprocess, "run", fake_run)

    blob_sync.download(tmp_path / "jobs.db")

    assert captured_env["BLOB_READ_WRITE_TOKEN"] == "real-env-token"


def test_missing_token_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.setattr(blob_sync, "ENV_PATH", tmp_path / "nonexistent.env")

    with pytest.raises(RuntimeError, match="BLOB_READ_WRITE_TOKEN"):
        blob_sync.download(tmp_path / "jobs.db")
