"""Tests for the BambooHR ATS connector (scripts/connectors/ats/bamboohr.py)."""
import requests_mock
from connectors.ats import bamboohr

JOB = {
    "id": "66",
    "jobOpeningName": "Development Director",
    "departmentLabel": "Communications",
    "location": {"city": "Brussels", "state": None},
    "employmentType": "Full-time",
    "isRemote": False,
}


def test_fetch_parses_all_fields():
    with requests_mock.Mocker() as m:
        m.get("https://testco.bamboohr.com/careers/list", json={"result": [JOB]})
        result = bamboohr.fetch("testco")

    assert len(result) == 1
    p = result[0]
    assert p["ats_id"] == "66"
    assert p["title"] == "Development Director"
    assert p["location"] == "Brussels"
    assert p["workplace_type"] is None
    assert p["team"] == "Communications"
    assert p["commitment"] == "Full-time"
    assert p["url"] == "https://testco.bamboohr.com/careers/66"


def test_fetch_marks_remote_workplace_type():
    remote_job = {**JOB, "isRemote": True}
    with requests_mock.Mocker() as m:
        m.get("https://testco.bamboohr.com/careers/list", json={"result": [remote_job]})
        result = bamboohr.fetch("testco")
    assert result[0]["workplace_type"] == "remote"


def test_fetch_empty_board_returns_empty_list():
    with requests_mock.Mocker() as m:
        m.get("https://emptyco.bamboohr.com/careers/list", json={"result": []})
        result = bamboohr.fetch("emptyco")
    assert result == []


def test_fetch_handles_missing_optional_fields():
    minimal = {"id": "1", "jobOpeningName": "Some Role"}
    with requests_mock.Mocker() as m:
        m.get("https://testco.bamboohr.com/careers/list", json={"result": [minimal]})
        result = bamboohr.fetch("testco")

    p = result[0]
    assert p["location"] is None
    assert p["team"] is None
    assert p["commitment"] is None
    assert p["workplace_type"] is None
