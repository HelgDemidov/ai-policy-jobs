"""Tests for the Workable ATS connector (scripts/connectors/ats/workable.py)."""
import requests_mock
from connectors.ats import workable

JOB = {
    "shortcode": "ABC123",
    "title": "Public Affairs Officer",
    "city": "Cambridge",
    "state": "England",
    "country": "United Kingdom",
    "telecommuting": False,
    "department": "Operations",
    "employment_type": "Full-time",
    "url": "https://apply.workable.com/testco/j/ABC123",
    "published_on": "2026-07-31",
}


def test_fetch_parses_all_fields():
    with requests_mock.Mocker() as m:
        m.get("https://apply.workable.com/api/v1/widget/accounts/testco?full=true", json={"jobs": [JOB]})
        m.get(
            "https://apply.workable.com/testco/jobs/view/ABC123.md",
            text="# Public Affairs Officer\n\nFull description here.",
        )
        result = workable.fetch("testco")

    assert len(result) == 1
    p = result[0]
    assert p["ats_id"] == "ABC123"
    assert p["title"] == "Public Affairs Officer"
    assert p["location"] == "Cambridge, England, United Kingdom"
    assert p["workplace_type"] is None
    assert p["team"] == "Operations"
    assert p["commitment"] == "Full-time"
    assert p["url"] == "https://apply.workable.com/testco/j/ABC123"
    assert p["posted_at"] == "2026-07-31"
    assert "Full description here." in p["description"]


def test_fetch_marks_remote_workplace_type():
    remote_job = {**JOB, "telecommuting": True}
    with requests_mock.Mocker() as m:
        m.get("https://apply.workable.com/api/v1/widget/accounts/testco?full=true", json={"jobs": [remote_job]})
        m.get("https://apply.workable.com/testco/jobs/view/ABC123.md", text="desc")
        result = workable.fetch("testco")
    assert result[0]["workplace_type"] == "remote"


def test_fetch_empty_board_returns_empty_list():
    with requests_mock.Mocker() as m:
        m.get("https://apply.workable.com/api/v1/widget/accounts/emptyco?full=true", json={"jobs": []})
        result = workable.fetch("emptyco")
    assert result == []


def test_fetch_handles_missing_markdown_export():
    with requests_mock.Mocker() as m:
        m.get("https://apply.workable.com/api/v1/widget/accounts/testco?full=true", json={"jobs": [JOB]})
        m.get("https://apply.workable.com/testco/jobs/view/ABC123.md", status_code=404)
        result = workable.fetch("testco")
    assert result[0]["description"] == ""
