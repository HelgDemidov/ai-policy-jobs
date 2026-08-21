"""Tests for the UNU query-centric connector (scripts/connectors/query/recruitee.py)."""
import requests_mock
from connectors.query import recruitee

OFFER = {
    "id": 2714737,
    "title": "Senior Researcher - Team Lead (P3)",
    "department": "UNU-Macau",
    "location": "Macau, Macau",
    "remote": False,
    "employment_type_code": "fulltime_fixed_term",
    "careers_url": "https://careers.unu.edu/o/senior-researcher-team-lead",
    "description": "<p>Lead our research team.</p><ul><li>Task one</li></ul>",
    "created_at": "2026-08-19 05:48:30 UTC",
}
OTHER_DEPT_OFFER = {**OFFER, "id": 1, "department": "Human Resources"}


def test_fetch_filters_by_department_allowlist():
    with requests_mock.Mocker() as m:
        m.get(recruitee.API, json={"offers": [OFFER, OTHER_DEPT_OFFER]})
        result = recruitee.fetch({"department_allowlist": ["UNU-Macau"]})

    assert len(result) == 1
    p = result[0]
    assert p["ats_id"] == "2714737"
    assert p["org"] == "UNU-Macau"
    assert p["title"] == "Senior Researcher - Team Lead (P3)"
    assert p["location"] == "Macau, Macau"
    assert p["workplace_type"] is None
    assert p["commitment"] == "fulltime_fixed_term"
    assert p["url"] == "https://careers.unu.edu/o/senior-researcher-team-lead"
    assert p["posted_at"] == "2026-08-19"
    assert "Lead our research team." in p["description"]
    assert "Task one" in p["description"]
    assert "<li>" not in p["description"]


def test_fetch_marks_remote_workplace_type():
    remote_offer = {**OFFER, "remote": True}
    with requests_mock.Mocker() as m:
        m.get(recruitee.API, json={"offers": [remote_offer]})
        result = recruitee.fetch({"department_allowlist": ["UNU-Macau"]})
    assert result[0]["workplace_type"] == "remote"


def test_fetch_empty_allowlist_matches_nothing():
    with requests_mock.Mocker() as m:
        m.get(recruitee.API, json={"offers": [OFFER]})
        result = recruitee.fetch({})
    assert result == []


def test_fetch_no_matching_department_returns_empty_list():
    with requests_mock.Mocker() as m:
        m.get(recruitee.API, json={"offers": [OTHER_DEPT_OFFER]})
        result = recruitee.fetch({"department_allowlist": ["UNU-Macau"]})
    assert result == []
