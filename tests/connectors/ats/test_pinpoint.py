"""Tests for the Pinpoint ATS connector (scripts/connectors/ats/pinpoint.py)."""
import requests_mock
from connectors.ats import pinpoint

JOB = {
    "id": "job-1",
    "title": "Research Associate",
    "description": "<p>Support our research team.</p><ul><li>Task one</li></ul>",
    "url": "https://careers.testco.org/jobs/job-1",
    "location": {"id": "loc-1", "name": "Remote"},
    "department": {"id": "dept-1", "name": "Research"},
    "employment_type_text": "Full-time",
    "workplace_type": "remote",
}


def test_fetch_parses_all_fields():
    with requests_mock.Mocker() as m:
        m.get("https://careers.testco.org/postings.json", json={"data": [JOB]})
        result = pinpoint.fetch("careers.testco.org")

    assert len(result) == 1
    p = result[0]
    assert p["ats_id"] == "job-1"
    assert p["title"] == "Research Associate"
    assert p["location"] == "Remote"
    assert p["workplace_type"] == "remote"
    assert p["team"] == "Research"
    assert p["commitment"] == "Full-time"
    assert p["url"] == "https://careers.testco.org/jobs/job-1"
    assert p["posted_at"] is None
    assert "Support our research team." in p["description"]
    assert "Task one" in p["description"]
    assert "<li>" not in p["description"]


def test_fetch_empty_board_returns_empty_list():
    with requests_mock.Mocker() as m:
        m.get("https://careers.emptyco.org/postings.json", json={"data": []})
        result = pinpoint.fetch("careers.emptyco.org")
    assert result == []


def test_fetch_handles_missing_optional_fields():
    minimal = {"id": "x1", "title": "Some Role", "description": ""}
    with requests_mock.Mocker() as m:
        m.get("https://careers.testco.org/postings.json", json={"data": [minimal]})
        result = pinpoint.fetch("careers.testco.org")

    p = result[0]
    assert p["location"] is None
    assert p["team"] is None
    assert p["commitment"] is None
    assert p["workplace_type"] is None
    assert p["url"] is None
    assert p["description"] == ""
