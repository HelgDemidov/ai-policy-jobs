"""Tests for the UN Secretariat query-centric connector
(scripts/connectors/query/un_secretariat.py)."""
import requests_mock
from connectors.query import un_secretariat

UNODA_JOB = {
    "jobId": 282683,
    "jobTitle": "PARTNERSHIPS OFFICER",
    "postingTitle": "PARTNERSHIPS OFFICER, NOC",
    "jobDescription": "<p>Support disarmament work.</p><ul><li>Task one</li></ul>",
    "dutyStation": [{"code": "2910", "description": "GENEVA"}],
    "startDate": "2026-08-14T04:00:00.000Z",
    "jf": {"Code": "SUS", "Name": "Sustainable Development"},
    "recrType": {"code": "P", "name": "Position Specific Job Openings"},
    "dept": {"code": "88888891", "name": "Office for Disarmament Affairs"},
}
OTHER_DEPT_JOB = {**UNODA_JOB, "jobId": 999999, "dept": {"code": "1", "name": "Department of Peace Operations"}}


def test_fetch_filters_by_dept_allowlist():
    with requests_mock.Mocker() as m:
        m.get(un_secretariat.API, json={"status": 1, "data": [UNODA_JOB, OTHER_DEPT_JOB]})
        result = un_secretariat.fetch({"dept_allowlist": ["Office for Disarmament Affairs"]})

    assert len(result) == 1
    p = result[0]
    assert p["ats_id"] == "282683"
    assert p["org"] == "Office for Disarmament Affairs"
    assert p["title"] == "PARTNERSHIPS OFFICER, NOC"
    assert p["location"] == "GENEVA"
    assert p["team"] == "Sustainable Development"
    assert p["commitment"] == "Position Specific Job Openings"
    assert p["url"] == "https://careers.un.org/jobSearchDescription/282683"
    assert p["posted_at"] == "2026-08-14"
    assert "Support disarmament work." in p["description"]
    assert "Task one" in p["description"]
    assert "<li>" not in p["description"]


def test_fetch_sends_referer_header():
    with requests_mock.Mocker() as m:
        m.get(un_secretariat.API, json={"status": 1, "data": []})
        un_secretariat.fetch({"dept_allowlist": ["Office for Disarmament Affairs"]})
    assert m.last_request.headers["Referer"] == "https://careers.un.org/jobfeed?isPage=true"


def test_fetch_empty_allowlist_matches_nothing():
    with requests_mock.Mocker() as m:
        m.get(un_secretariat.API, json={"status": 1, "data": [UNODA_JOB]})
        result = un_secretariat.fetch({})
    assert result == []


def test_fetch_no_matching_dept_returns_empty_list():
    with requests_mock.Mocker() as m:
        m.get(un_secretariat.API, json={"status": 1, "data": [OTHER_DEPT_JOB]})
        result = un_secretariat.fetch({"dept_allowlist": ["Office for Disarmament Affairs"]})
    assert result == []


def test_fetch_handles_missing_duty_station():
    minimal = {
        "jobId": 1,
        "jobTitle": "Some Role",
        "jobDescription": "",
        "dutyStation": [],
        "dept": {"name": "Office for Disarmament Affairs"},
    }
    with requests_mock.Mocker() as m:
        m.get(un_secretariat.API, json={"status": 1, "data": [minimal]})
        result = un_secretariat.fetch({"dept_allowlist": ["Office for Disarmament Affairs"]})

    p = result[0]
    assert p["location"] is None
    assert p["team"] is None
    assert p["commitment"] is None
    assert p["posted_at"] is None
    assert p["description"] == ""
    assert p["title"] == "Some Role"
