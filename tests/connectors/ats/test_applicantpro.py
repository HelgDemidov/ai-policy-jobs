"""Tests for the ApplicantPro ATS connector (scripts/connectors/ats/applicantpro.py)."""
import requests_mock
from connectors.ats import applicantpro

JOB = {
    "id": 4146995,
    "title": "Communications Intern - Carnegie Middle East Center",
    "city": "Beirut",
    "stateName": None,
    "orgTitle": "CMEC Internship",
    "parentTitle": "Other",
    "workplaceType": "Onsite",
    "employmentType": "Full Time",
    "jobUrl": "https://testco.applicantpro.com/jobs/4146995",
    "startDateRef": "Jul 01, 2026",
}


def test_fetch_parses_all_fields():
    with requests_mock.Mocker() as m:
        m.get("https://testco.applicantpro.com/core/jobs/2306", json={"data": {"jobs": [JOB]}})
        result = applicantpro.fetch("testco:2306")

    assert len(result) == 1
    p = result[0]
    assert p["ats_id"] == "4146995"
    assert p["title"] == "Communications Intern - Carnegie Middle East Center"
    assert p["location"] == "Beirut"
    assert p["workplace_type"] is None
    assert p["team"] == "CMEC Internship"
    assert p["commitment"] == "Full Time"
    assert p["url"] == "https://testco.applicantpro.com/jobs/4146995"


def test_fetch_marks_remote_workplace_type():
    remote_job = {**JOB, "workplaceType": "Remote"}
    with requests_mock.Mocker() as m:
        m.get("https://testco.applicantpro.com/core/jobs/2306", json={"data": {"jobs": [remote_job]}})
        result = applicantpro.fetch("testco:2306")
    assert result[0]["workplace_type"] == "remote"


def test_fetch_empty_board_returns_empty_list():
    with requests_mock.Mocker() as m:
        m.get("https://testco.applicantpro.com/core/jobs/2306", json={"data": {"jobs": []}})
        result = applicantpro.fetch("testco:2306")
    assert result == []


def test_fetch_handles_missing_optional_fields():
    minimal = {"id": 1, "title": "Some Role"}
    with requests_mock.Mocker() as m:
        m.get("https://testco.applicantpro.com/core/jobs/2306", json={"data": {"jobs": [minimal]}})
        result = applicantpro.fetch("testco:2306")

    p = result[0]
    assert p["location"] is None
    assert p["team"] is None
    assert p["commitment"] is None
    assert p["workplace_type"] is None
    assert p["url"] is None
