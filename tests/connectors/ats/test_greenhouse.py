"""Tests for the Greenhouse ATS connector (scripts/connectors/ats/greenhouse.py)."""
import requests_mock
from connectors.ats import greenhouse


def test_fetch_combines_list_and_detail_requests():
    list_payload = {
        "jobs": [
            {
                "id": 111,
                "title": "Policy Analyst",
                "location": {"name": "London"},
                "absolute_url": "https://job-boards.greenhouse.io/testco/jobs/111",
                "updated_at": "2024-05-01T10:00:00-04:00",
            }
        ]
    }
    detail_payload = {"content": "<p>Great role.</p><ul><li>Task one</li></ul>"}

    with requests_mock.Mocker() as m:
        m.get("https://boards-api.greenhouse.io/v1/boards/testco/jobs", json=list_payload)
        m.get(
            "https://boards-api.greenhouse.io/v1/boards/testco/jobs/111?content=true",
            json=detail_payload,
        )
        result = greenhouse.fetch("testco")

    assert len(result) == 1
    p = result[0]
    assert p["ats_id"] == "111"
    assert p["title"] == "Policy Analyst"
    assert p["location"] == "London"
    assert p["url"] == "https://job-boards.greenhouse.io/testco/jobs/111"
    assert p["posted_at"] == "2024-05-01"
    assert "Great role." in p["description"]
    assert "Task one" in p["description"]
    assert "<li>" not in p["description"]
    assert p["workplace_type"] is None


def test_fetch_empty_board_returns_empty_list():
    with requests_mock.Mocker() as m:
        m.get("https://boards-api.greenhouse.io/v1/boards/emptyco/jobs", json={"jobs": []})
        result = greenhouse.fetch("emptyco")
    assert result == []


def test_fetch_handles_missing_location_and_date():
    list_payload = {
        "jobs": [
            {
                "id": 5,
                "title": "No Location Role",
                "absolute_url": "https://job-boards.greenhouse.io/co/jobs/5",
                "updated_at": None,
            }
        ]
    }
    with requests_mock.Mocker() as m:
        m.get("https://boards-api.greenhouse.io/v1/boards/co/jobs", json=list_payload)
        m.get(
            "https://boards-api.greenhouse.io/v1/boards/co/jobs/5?content=true",
            json={"content": ""},
        )
        result = greenhouse.fetch("co")

    p = result[0]
    assert p["location"] is None
    assert p["posted_at"] is None
    assert p["description"] == ""


def test_ats_id_is_always_a_string():
    """Greenhouse job ids are JSON integers — stored as text to match Lever's
    UUID-shaped ats_id in the same SQLite column."""
    list_payload = {"jobs": [{"id": 42, "title": "T", "absolute_url": "https://x/42"}]}
    with requests_mock.Mocker() as m:
        m.get("https://boards-api.greenhouse.io/v1/boards/co/jobs", json=list_payload)
        m.get("https://boards-api.greenhouse.io/v1/boards/co/jobs/42?content=true", json={"content": ""})
        result = greenhouse.fetch("co")
    assert result[0]["ats_id"] == "42"
    assert isinstance(result[0]["ats_id"], str)
