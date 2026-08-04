"""Tests for the JobSpy wrapper (scripts/jobspy_search.py).

scrape_jobs is monkeypatched everywhere — no real network/scraping in tests.
"""
import datetime

import numpy as np
import pandas as pd
import pytest

import jobspy_search


def _df(rows):
    return pd.DataFrame(rows)


FULL_ROW = {
    "id": "li-abc123",
    "job_url": "https://linkedin.com/jobs/view/abc123",
    "title": "Research Analyst",
    "company": "RAND Europe",
    "location": "Cambridge, England, UK",
    "date_posted": datetime.date(2026, 7, 20),
    "job_type": "fulltime",
    "is_remote": False,
    "description": "Join our research team.",
}


def test_fetch_linkedin_maps_fields(monkeypatch):
    calls = {}

    def fake_scrape_jobs(**kwargs):
        calls.update(kwargs)
        return _df([FULL_ROW])

    monkeypatch.setattr(jobspy_search, "scrape_jobs", fake_scrape_jobs)

    result = jobspy_search.fetch_linkedin({"query": "AI policy analyst", "location": "United Kingdom"})

    assert calls["site_name"] == ["linkedin"]
    assert calls["search_term"] == "AI policy analyst"
    assert calls["location"] == "United Kingdom"
    assert calls["linkedin_fetch_description"] is False  # default: fewer requests

    assert len(result) == 1
    p = result[0]
    assert p["ats_id"] == "li-abc123"
    assert p["org"] == "RAND Europe"
    assert p["title"] == "Research Analyst"
    assert p["location"] == "Cambridge, England, UK"
    assert p["commitment"] == "fulltime"
    assert p["workplace_type"] is None  # is_remote=False
    assert p["url"] == "https://linkedin.com/jobs/view/abc123"
    assert p["posted_at"] == "2026-07-20"


def test_fetch_linkedin_respects_fetch_description_override(monkeypatch):
    calls = {}

    def fake_scrape_jobs(**kwargs):
        calls.update(kwargs)
        return _df([])

    monkeypatch.setattr(jobspy_search, "scrape_jobs", fake_scrape_jobs)
    jobspy_search.fetch_linkedin({"query": "x", "fetch_description": True})

    assert calls["linkedin_fetch_description"] is True


def test_fetch_indeed_uses_indeed_site_and_country(monkeypatch):
    calls = {}

    def fake_scrape_jobs(**kwargs):
        calls.update(kwargs)
        return _df([])

    monkeypatch.setattr(jobspy_search, "scrape_jobs", fake_scrape_jobs)
    jobspy_search.fetch_indeed({"query": "policy", "location": "London", "country_indeed": "UK"})

    assert calls["site_name"] == ["indeed"]
    assert calls["country_indeed"] == "UK"


def test_fetch_indeed_defaults_country_to_usa(monkeypatch):
    calls = {}

    def fake_scrape_jobs(**kwargs):
        calls.update(kwargs)
        return _df([])

    monkeypatch.setattr(jobspy_search, "scrape_jobs", fake_scrape_jobs)
    jobspy_search.fetch_indeed({"query": "policy"})

    assert calls["country_indeed"] == "USA"


def test_is_remote_true_sets_workplace_type(monkeypatch):
    row = dict(FULL_ROW)
    row["is_remote"] = True
    monkeypatch.setattr(jobspy_search, "scrape_jobs", lambda **_kw: _df([row]))

    result = jobspy_search.fetch_linkedin({"query": "x"})

    assert result[0]["workplace_type"] == "remote"


def test_nan_optional_fields_become_none(monkeypatch):
    row = dict(FULL_ROW)
    row["description"] = np.nan
    row["date_posted"] = pd.NaT
    monkeypatch.setattr(jobspy_search, "scrape_jobs", lambda **_kw: _df([row]))

    result = jobspy_search.fetch_linkedin({"query": "x"})

    assert result[0]["description"] is None
    assert result[0]["posted_at"] is None


def test_missing_company_skips_record(monkeypatch):
    row = dict(FULL_ROW)
    row["company"] = np.nan
    monkeypatch.setattr(jobspy_search, "scrape_jobs", lambda **_kw: _df([row]))

    result = jobspy_search.fetch_linkedin({"query": "x"})

    assert result == []


def test_missing_id_and_job_url_skips_record(monkeypatch):
    # str(None) == "None" (truthy) — ats_id must be checked before str().
    row = dict(FULL_ROW)
    row["id"] = np.nan
    row["job_url"] = np.nan
    monkeypatch.setattr(jobspy_search, "scrape_jobs", lambda **_kw: _df([row]))

    result = jobspy_search.fetch_linkedin({"query": "x"})

    assert result == []


def test_fetch_linkedin_skips_invalid_rows_but_keeps_valid_ones(monkeypatch):
    bad = dict(FULL_ROW)
    bad["company"] = np.nan
    good = dict(FULL_ROW)
    good["id"] = "li-good"
    monkeypatch.setattr(jobspy_search, "scrape_jobs", lambda **_kw: _df([bad, good]))

    result = jobspy_search.fetch_linkedin({"query": "x"})

    assert len(result) == 1
    assert result[0]["ats_id"] == "li-good"


def test_nan_is_remote_does_not_become_truthy_remote(monkeypatch):
    """Regression guard: NaN is truthy in plain Python (bool(float('nan')) is
    True), so a naive `if row['is_remote']` would wrongly tag a missing
    is_remote value as remote. Must compare `is True` after cleaning."""
    row = dict(FULL_ROW)
    row["is_remote"] = np.nan
    monkeypatch.setattr(jobspy_search, "scrape_jobs", lambda **_kw: _df([row]))

    result = jobspy_search.fetch_linkedin({"query": "x"})

    assert result[0]["workplace_type"] is None


def test_empty_dataframe_returns_empty_list(monkeypatch):
    monkeypatch.setattr(jobspy_search, "scrape_jobs", lambda **_kw: _df([]))

    assert jobspy_search.fetch_linkedin({"query": "x"}) == []
    assert jobspy_search.fetch_indeed({"query": "x"}) == []


def test_ats_id_falls_back_to_job_url_when_id_missing(monkeypatch):
    row = dict(FULL_ROW)
    row["id"] = np.nan
    monkeypatch.setattr(jobspy_search, "scrape_jobs", lambda **_kw: _df([row]))

    result = jobspy_search.fetch_linkedin({"query": "x"})

    assert result[0]["ats_id"] == "https://linkedin.com/jobs/view/abc123"
