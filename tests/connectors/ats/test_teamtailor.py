"""Tests for the Teamtailor ATS connector (scripts/connectors/ats/teamtailor.py)."""
import requests_mock
from connectors.ats import teamtailor

FULL_ITEM = {
    "id": "abc-123",
    "title": "Research Fellow",
    "url": "https://careers.testco.org/jobs/abc-123-research-fellow",
    "date_published": "2026-07-29T00:00:00+01:00",
    "content_html": "<p>Join our team.</p><ul><li>Task one</li></ul>",
    "_jobposting": {
        "jobLocation": [{"address": {"addressLocality": "London", "addressCountry": "GB"}}],
    },
}


def test_fetch_parses_all_fields():
    with requests_mock.Mocker() as m:
        m.get("https://careers.testco.org/jobs.json", json={"items": [FULL_ITEM]})
        result = teamtailor.fetch("careers.testco.org")

    assert len(result) == 1
    p = result[0]
    assert p["ats_id"] == "abc-123"
    assert p["title"] == "Research Fellow"
    assert p["location"] == "London, GB"
    assert p["workplace_type"] is None
    assert p["url"] == "https://careers.testco.org/jobs/abc-123-research-fellow"
    assert p["posted_at"] == "2026-07-29"
    assert "Join our team." in p["description"]
    assert "Task one" in p["description"]
    assert "<li>" not in p["description"]


def test_fetch_empty_board_returns_empty_list():
    with requests_mock.Mocker() as m:
        m.get("https://careers.emptyco.org/jobs.json", json={"items": []})
        result = teamtailor.fetch("careers.emptyco.org")
    assert result == []


def test_fetch_handles_missing_location():
    minimal = {
        "id": "x1",
        "title": "Some Role",
        "url": "https://careers.testco.org/jobs/x1",
        "date_published": None,
        "content_html": "",
        "_jobposting": {},
    }
    with requests_mock.Mocker() as m:
        m.get("https://careers.testco.org/jobs.json", json={"items": [minimal]})
        result = teamtailor.fetch("careers.testco.org")

    p = result[0]
    assert p["location"] is None
    assert p["posted_at"] is None
    assert p["description"] == ""
