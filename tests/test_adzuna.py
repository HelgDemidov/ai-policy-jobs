"""Tests for the Adzuna query-centric connector (scripts/adzuna.py)."""
import pytest
import requests_mock

import adzuna

FULL_JOB = {
    "id": "5810920346",
    "title": "Analyst, Climate Change Think Tank, UK-based",
    "company": {"display_name": "InfluenceMap"},
    "location": {"display_name": "London, UK"},
    "contract_time": "full_time",
    "created": "2026-07-22T15:42:54Z",
    "redirect_url": "https://www.adzuna.co.uk/jobs/details/5810920346?utm_medium=api",
    "description": "Do you have a desire to make a positive impact...",
}


@pytest.fixture(autouse=True)
def _env_credentials(monkeypatch):
    """Every test gets credentials via real env vars unless it explicitly
    tests the .env-file fallback path."""
    monkeypatch.setenv("ADZUNA_APP_ID", "test-id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "test-key")


def test_fetch_parses_all_fields_with_phrase():
    with requests_mock.Mocker() as m:
        m.get(
            "https://api.adzuna.com/v1/api/jobs/gb/search/1",
            json={"results": [FULL_JOB], "count": 1},
        )
        result = adzuna.fetch({"phrase": "think tank", "country": "gb"})

    assert len(result) == 1
    p = result[0]
    assert p["ats_id"] == "5810920346"
    assert p["org"] == "InfluenceMap"
    assert p["title"] == "Analyst, Climate Change Think Tank, UK-based"
    assert p["location"] == "London, UK"
    assert p["commitment"] == "full_time"
    assert p["url"] == "https://www.adzuna.co.uk/jobs/details/5810920346?utm_medium=api"
    assert p["posted_at"] == "2026-07-22"
    assert p["workplace_type"] is None


def test_fetch_sends_what_phrase_not_what_for_phrase_spec():
    with requests_mock.Mocker() as m:
        m.get("https://api.adzuna.com/v1/api/jobs/gb/search/1", json={"results": []})
        adzuna.fetch({"phrase": "think tank", "country": "gb"})

    qs = m.request_history[0].qs
    assert qs.get("what_phrase") == ["think tank"]
    assert "what" not in qs


def test_fetch_sends_what_for_query_spec():
    with requests_mock.Mocker() as m:
        m.get("https://api.adzuna.com/v1/api/jobs/gb/search/1", json={"results": []})
        adzuna.fetch({"query": "policy", "country": "gb"})

    qs = m.request_history[0].qs
    assert qs.get("what") == ["policy"]
    assert "what_phrase" not in qs


def test_fetch_uses_country_in_url_path():
    with requests_mock.Mocker() as m:
        m.get("https://api.adzuna.com/v1/api/jobs/be/search/1", json={"results": []})
        adzuna.fetch({"phrase": "think tank", "country": "be"})

    assert m.called


def test_fetch_empty_results():
    with requests_mock.Mocker() as m:
        m.get("https://api.adzuna.com/v1/api/jobs/gb/search/1", json={"results": []})
        result = adzuna.fetch({"phrase": "think tank", "country": "gb"})
    assert result == []


def test_fetch_handles_missing_company_and_location():
    job = dict(FULL_JOB)
    del job["company"]
    del job["location"]
    with requests_mock.Mocker() as m:
        m.get("https://api.adzuna.com/v1/api/jobs/gb/search/1", json={"results": [job]})
        result = adzuna.fetch({"phrase": "think tank", "country": "gb"})

    assert result[0]["org"] is None
    assert result[0]["location"] is None


def test_missing_credentials_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    # Neutralize the fallback .env file too — the real repo-root .env (with
    # real credentials) would otherwise satisfy _load_env_credentials().
    monkeypatch.setattr(adzuna, "ENV_PATH", tmp_path / "nonexistent.env")
    with pytest.raises(RuntimeError, match="ADZUNA_APP_ID"):
        adzuna.fetch({"phrase": "think tank", "country": "gb"})


def test_env_file_used_when_no_real_env_vars(tmp_path, monkeypatch):
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("ADZUNA_APP_ID=file-id\nADZUNA_APP_KEY=file-key\n")
    monkeypatch.setattr(adzuna, "ENV_PATH", env_file)

    with requests_mock.Mocker() as m:
        m.get("https://api.adzuna.com/v1/api/jobs/gb/search/1", json={"results": []})
        adzuna.fetch({"phrase": "think tank", "country": "gb"})

    qs = m.request_history[0].qs
    assert qs.get("app_id") == ["file-id"]
    assert qs.get("app_key") == ["file-key"]


def test_real_env_vars_take_priority_over_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("ADZUNA_APP_ID=file-id\nADZUNA_APP_KEY=file-key\n")
    monkeypatch.setattr(adzuna, "ENV_PATH", env_file)
    # autouse fixture already set real env vars to test-id/test-key

    with requests_mock.Mocker() as m:
        m.get("https://api.adzuna.com/v1/api/jobs/gb/search/1", json={"results": []})
        adzuna.fetch({"phrase": "think tank", "country": "gb"})

    qs = m.request_history[0].qs
    assert qs.get("app_id") == ["test-id"]
