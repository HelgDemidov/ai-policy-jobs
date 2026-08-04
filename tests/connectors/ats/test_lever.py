"""Tests for the Lever ATS connector (scripts/connectors/ats/lever.py)."""
from datetime import datetime, timezone

import requests_mock
from connectors.ats import lever

CREATED_AT = int(datetime(2024, 3, 15, 12, 0, tzinfo=timezone.utc).timestamp() * 1000)

FULL_POSTING = {
    "id": "abc-123",
    "text": "Research Analyst",
    "categories": {"location": "Remote", "team": "Policy", "commitment": "Full-time"},
    "workplaceType": "remote",
    "country": "US",
    "createdAt": CREATED_AT,
    "hostedUrl": "https://jobs.lever.co/testco/abc-123",
    "descriptionBodyPlain": "Join our policy team.",
    "lists": [
        {"text": "Responsibilities", "content": "<li>Do research</li><li>Write memos</li>"},
    ],
}


def test_fetch_parses_all_fields():
    with requests_mock.Mocker() as m:
        m.get("https://api.lever.co/v0/postings/testco?mode=json", json=[FULL_POSTING])
        result = lever.fetch("testco")

    assert len(result) == 1
    p = result[0]
    assert p["ats_id"] == "abc-123"
    assert p["title"] == "Research Analyst"
    assert p["location"] == "Remote"
    assert p["workplace_type"] == "remote"
    assert p["team"] == "Policy"
    assert p["commitment"] == "Full-time"
    assert p["url"] == "https://jobs.lever.co/testco/abc-123"
    assert p["posted_at"] == "2024-03-15"


def test_fetch_assembles_description_and_strips_html():
    with requests_mock.Mocker() as m:
        m.get("https://api.lever.co/v0/postings/testco?mode=json", json=[FULL_POSTING])
        result = lever.fetch("testco")

    description = result[0]["description"]
    assert "Join our policy team." in description
    assert "Responsibilities" in description
    assert "Do research" in description
    assert "Write memos" in description
    assert "<li>" not in description
    assert "</li>" not in description


def test_fetch_empty_board_returns_empty_list():
    with requests_mock.Mocker() as m:
        m.get("https://api.lever.co/v0/postings/emptyco?mode=json", json=[])
        result = lever.fetch("emptyco")
    assert result == []


def test_fetch_handles_missing_optional_fields():
    minimal = {"id": "x1", "text": "Some Role", "hostedUrl": "https://jobs.lever.co/x/x1"}
    with requests_mock.Mocker() as m:
        m.get("https://api.lever.co/v0/postings/minimalco?mode=json", json=[minimal])
        result = lever.fetch("minimalco")

    p = result[0]
    assert p["location"] is None
    assert p["team"] is None
    assert p["commitment"] is None
    assert p["workplace_type"] is None
    assert p["posted_at"] is None
    assert p["description"] == ""
