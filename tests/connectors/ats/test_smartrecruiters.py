"""Tests for the SmartRecruiters ATS connector (scripts/connectors/ats/smartrecruiters.py)."""
import re

import requests_mock
from connectors.ats import smartrecruiters

LIST_ITEM = {
    "id": 999,
    "name": "Policy Researcher",
    "location": {"fullLocation": "Paris, France", "remote": False, "hybrid": False},
    "department": {"label": "Digital Economy"},
    "typeOfEmployment": {"label": "Full-time"},
    "releasedDate": "2026-08-18T11:02:59.030Z",
}
DETAIL = {
    "postingUrl": "https://jobs.smartrecruiters.com/testco/999-policy-researcher",
    "jobAd": {
        "sections": {
            "jobDescription": {"title": "Job Description", "text": "<p>Analyse policy.</p><ul><li>Task one</li></ul>"},
        }
    },
}


def _list_url(slug: str, offset: int = 0) -> str:
    return f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&offset={offset}"


def test_fetch_parses_all_fields():
    with requests_mock.Mocker() as m:
        m.get(_list_url("testco"), json={"totalFound": 1, "content": [LIST_ITEM]})
        m.get("https://api.smartrecruiters.com/v1/companies/testco/postings/999", json=DETAIL)
        result = smartrecruiters.fetch("testco")

    assert len(result) == 1
    p = result[0]
    assert p["ats_id"] == "999"
    assert p["title"] == "Policy Researcher"
    assert p["location"] == "Paris, France"
    assert p["workplace_type"] is None
    assert p["team"] == "Digital Economy"
    assert p["commitment"] == "Full-time"
    assert p["url"] == "https://jobs.smartrecruiters.com/testco/999-policy-researcher"
    assert p["posted_at"] == "2026-08-18"
    assert "Analyse policy." in p["description"]
    assert "Task one" in p["description"]
    assert "<li>" not in p["description"]


def test_fetch_marks_remote_and_hybrid_workplace_type():
    remote_item = {**LIST_ITEM, "id": 1, "location": {"fullLocation": "Remote", "remote": True, "hybrid": False}}
    hybrid_item = {**LIST_ITEM, "id": 2, "location": {"fullLocation": "Paris", "remote": False, "hybrid": True}}
    with requests_mock.Mocker() as m:
        m.get(_list_url("testco"), json={"totalFound": 2, "content": [remote_item, hybrid_item]})
        m.get(
            "https://api.smartrecruiters.com/v1/companies/testco/postings/1",
            json={"postingUrl": "u1", "jobAd": {"sections": {}}},
        )
        m.get(
            "https://api.smartrecruiters.com/v1/companies/testco/postings/2",
            json={"postingUrl": "u2", "jobAd": {"sections": {}}},
        )
        result = smartrecruiters.fetch("testco")

    assert result[0]["workplace_type"] == "remote"
    assert result[1]["workplace_type"] == "hybrid"


def test_fetch_paginates_past_first_page():
    page_one = [{**LIST_ITEM, "id": i} for i in range(100)]
    page_two = [{**LIST_ITEM, "id": 100}]
    with requests_mock.Mocker() as m:
        m.get(_list_url("bigco", 0), json={"totalFound": 101, "content": page_one})
        m.get(_list_url("bigco", 100), json={"totalFound": 101, "content": page_two})
        m.get(
            re.compile(r"https://api\.smartrecruiters\.com/v1/companies/bigco/postings/\d+$"),
            json={"postingUrl": "u", "jobAd": {"sections": {}}},
        )
        result = smartrecruiters.fetch("bigco")
    assert len(result) == 101


def test_fetch_empty_board_returns_empty_list():
    with requests_mock.Mocker() as m:
        m.get(_list_url("emptyco"), json={"totalFound": 0, "content": []})
        result = smartrecruiters.fetch("emptyco")
    assert result == []


def test_fetch_handles_missing_optional_fields():
    minimal = {"id": 1, "name": "Some Role"}
    with requests_mock.Mocker() as m:
        m.get(_list_url("minimalco"), json={"totalFound": 1, "content": [minimal]})
        m.get(
            "https://api.smartrecruiters.com/v1/companies/minimalco/postings/1",
            json={"jobAd": {"sections": {}}},
        )
        result = smartrecruiters.fetch("minimalco")

    p = result[0]
    assert p["location"] is None
    assert p["team"] is None
    assert p["commitment"] is None
    assert p["workplace_type"] is None
    assert p["posted_at"] is None
    assert p["description"] == ""
    assert p["url"] is None
