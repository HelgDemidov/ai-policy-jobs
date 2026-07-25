"""Tests for the Himalayas query-centric connector (scripts/himalayas.py)."""
import himalayas
import requests_mock

FULL_JOB = {
    "guid": "https://himalayas.app/companies/aptive/jobs/policy-analyst",
    "applicationLink": "https://himalayas.app/companies/aptive/jobs/policy-analyst",
    "title": "Policy Analyst",
    "companyName": "Aptive",
    "employmentType": "Full Time",
    "excerpt": "Aptive is seeking a Policy Analyst.",
    "description": "<h3>Summary</h3><p>Support governance.</p><ul><li>Draft policy</li></ul>",
    "locationRestrictions": ["United States"],
    "pubDate": 1783493557,
}

EMPTY_PAGE = {"offset": 20, "limit": 20, "totalCount": 1, "jobs": []}


def _page(jobs):
    return {"offset": 0, "limit": 20, "totalCount": len(jobs), "jobs": jobs}


def _mock_one_page_then_empty(m, job):
    """Real API returns an empty jobs list once results are exhausted —
    mock the same shape so the connector's stop-on-empty-page logic actually
    gets exercised (a single always-repeating mock response would otherwise
    make requests_mock replay page 1's job on every subsequent page)."""
    m.get(
        "https://himalayas.app/jobs/api/search",
        [{"json": _page([job])}, {"json": EMPTY_PAGE}],
    )


def test_fetch_parses_all_fields(requests_mock, monkeypatch):
    monkeypatch.setattr(himalayas.time, "sleep", lambda _seconds: None)
    _mock_one_page_then_empty(requests_mock, FULL_JOB)

    result = himalayas.fetch({"query": "policy"})

    assert len(result) == 1
    p = result[0]
    assert p["ats_id"] == "https://himalayas.app/companies/aptive/jobs/policy-analyst"
    assert p["org"] == "Aptive"
    assert p["title"] == "Policy Analyst"
    assert p["location"] == "United States"
    assert p["workplace_type"] == "remote"  # hardcoded — Himalayas is remote-only
    assert p["commitment"] == "Full Time"
    assert p["url"] == "https://himalayas.app/companies/aptive/jobs/policy-analyst"
    assert p["posted_at"] is not None


def test_fetch_strips_html_from_description(requests_mock, monkeypatch):
    monkeypatch.setattr(himalayas.time, "sleep", lambda _seconds: None)
    _mock_one_page_then_empty(requests_mock, FULL_JOB)

    result = himalayas.fetch({"query": "policy"})

    description = result[0]["description"]
    assert "Support governance." in description
    assert "Draft policy" in description
    assert "<li>" not in description
    assert "<h3>" not in description


def test_fetch_falls_back_to_excerpt_when_description_missing(requests_mock, monkeypatch):
    monkeypatch.setattr(himalayas.time, "sleep", lambda _seconds: None)
    job = dict(FULL_JOB)
    del job["description"]
    _mock_one_page_then_empty(requests_mock, job)

    result = himalayas.fetch({"query": "policy"})

    assert result[0]["description"] == "Aptive is seeking a Policy Analyst."


def test_fetch_stops_pagination_on_empty_page(requests_mock, monkeypatch):
    monkeypatch.setattr(himalayas.time, "sleep", lambda _seconds: None)
    _mock_one_page_then_empty(requests_mock, FULL_JOB)

    result = himalayas.fetch({"query": "policy"})

    assert len(result) == 1
    assert requests_mock.call_count == 2  # page 1 (job) + page 2 (empty) — never reaches page 3


def test_fetch_handles_missing_location_restrictions(requests_mock, monkeypatch):
    monkeypatch.setattr(himalayas.time, "sleep", lambda _seconds: None)
    job = dict(FULL_JOB)
    job["locationRestrictions"] = []
    _mock_one_page_then_empty(requests_mock, job)

    result = himalayas.fetch({"query": "policy"})

    assert result[0]["location"] is None


def test_fetch_empty_first_page_returns_empty_list(requests_mock, monkeypatch):
    monkeypatch.setattr(himalayas.time, "sleep", lambda _seconds: None)
    requests_mock.get("https://himalayas.app/jobs/api/search", json=EMPTY_PAGE)

    result = himalayas.fetch({"query": "nonexistent-query-xyz"})

    assert result == []
