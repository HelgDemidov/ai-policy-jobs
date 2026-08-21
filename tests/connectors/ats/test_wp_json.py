"""Tests for the WordPress REST API connector (scripts/connectors/ats/wp_json.py)."""
import requests_mock
from connectors.ats import wp_json

POST = {
    "id": 42,
    "title": {"rendered": "Policy Analyst"},
    "content": {"rendered": "<p>Join our team.</p><ul><li>Task one</li></ul>"},
    "link": "https://testco.org/job-opportunity/policy-analyst/",
    "date": "2026-08-14T10:00:00",
}


def test_fetch_parses_all_fields():
    with requests_mock.Mocker() as m:
        m.get(
            "https://testco.org/wp-json/wp/v2/job-opportunity",
            [{"json": [POST]}, {"json": []}],
        )
        result = wp_json.fetch("https://testco.org", "job-opportunity")

    assert len(result) == 1
    p = result[0]
    assert p["ats_id"] == "42"
    assert p["title"] == "Policy Analyst"
    assert p["url"] == "https://testco.org/job-opportunity/policy-analyst/"
    assert p["posted_at"] == "2026-08-14"
    assert "Join our team." in p["description"]
    assert "Task one" in p["description"]
    assert "<li>" not in p["description"]


def test_fetch_strips_trailing_slash_from_site_url():
    with requests_mock.Mocker() as m:
        m.get("https://testco.org/wp-json/wp/v2/job-listings", json=[])
        result = wp_json.fetch("https://testco.org/", "job-listings")
    assert result == []
    assert m.last_request.url.startswith("https://testco.org/wp-json/wp/v2/job-listings")


def test_fetch_empty_site_returns_empty_list():
    with requests_mock.Mocker() as m:
        m.get("https://emptyco.org/wp-json/wp/v2/job-listings", json=[])
        result = wp_json.fetch("https://emptyco.org", "job-listings")
    assert result == []


def test_fetch_stops_at_400_past_last_page():
    with requests_mock.Mocker() as m:
        m.get(
            "https://testco.org/wp-json/wp/v2/job-listings",
            [{"json": [POST]}, {"status_code": 400}],
        )
        result = wp_json.fetch("https://testco.org", "job-listings")
    assert len(result) == 1
