"""Tests for the Workday ATS connector (scripts/connectors/ats/workday.py)."""
import requests_mock
from connectors.ats import workday

LIST_URL = "https://testco.wd3.myworkdayjobs.com/wday/cxs/testco/Careers/jobs"
DETAIL_URL = "https://testco.wd3.myworkdayjobs.com/wday/cxs/testco/Careers/job/Geneva/Policy-Lead_R123"

LIST_PAYLOAD = {
    "total": 1,
    "jobPostings": [
        {"title": "Policy Lead", "externalPath": "/job/Geneva/Policy-Lead_R123", "locationsText": "Geneva"},
    ],
}
DETAIL_PAYLOAD = {
    "jobPostingInfo": {
        "title": "Policy Lead",
        "jobDescription": "<p>Lead our policy work.</p><ul><li>Task one</li></ul>",
        "location": "Geneva",
        "startDate": "2026-08-01",
        "timeType": "Full time",
        "jobReqId": "R123",
        "externalUrl": "https://testco.wd3.myworkdayjobs.com/Careers/job/Geneva/Policy-Lead_R123",
    }
}


def test_fetch_parses_all_fields():
    with requests_mock.Mocker() as m:
        m.post(LIST_URL, json=LIST_PAYLOAD)
        m.get(DETAIL_URL, json=DETAIL_PAYLOAD)
        result = workday.fetch("testco:Careers")

    assert len(result) == 1
    p = result[0]
    assert p["ats_id"] == "R123"
    assert p["title"] == "Policy Lead"
    assert p["location"] == "Geneva"
    assert p["commitment"] == "Full time"
    assert p["url"] == "https://testco.wd3.myworkdayjobs.com/Careers/job/Geneva/Policy-Lead_R123"
    assert p["posted_at"] == "2026-08-01"
    assert "Lead our policy work." in p["description"]
    assert "Task one" in p["description"]
    assert "<li>" not in p["description"]


def test_fetch_paginates_past_first_page():
    page_one = {
        "total": 21,
        "jobPostings": [
            {"title": f"Role {i}", "externalPath": f"/job/Geneva/Role-{i}_R{i}", "locationsText": "Geneva"}
            for i in range(20)
        ],
    }
    page_two = {
        "total": 21,
        "jobPostings": [{"title": "Role 20", "externalPath": "/job/Geneva/Role-20_R20", "locationsText": "Geneva"}],
    }
    with requests_mock.Mocker() as m:
        m.post(LIST_URL, [{"json": page_one}, {"json": page_two}])
        m.get(requests_mock.ANY, json={"jobPostingInfo": {}})
        result = workday.fetch("testco:Careers")
    assert len(result) == 21


def test_fetch_empty_board_returns_empty_list():
    with requests_mock.Mocker() as m:
        m.post(LIST_URL, json={"total": 0, "jobPostings": []})
        result = workday.fetch("testco:Careers")
    assert result == []


def test_fetch_handles_missing_optional_fields():
    with requests_mock.Mocker() as m:
        m.post(LIST_URL, json={"total": 1, "jobPostings": [{"title": "Some Role", "externalPath": "/job/x/R1"}]})
        m.get(requests_mock.ANY, json={"jobPostingInfo": {}})
        result = workday.fetch("testco:Careers")

    p = result[0]
    assert p["ats_id"] == "/job/x/R1"
    assert p["title"] == "Some Role"  # falls back to the list payload's own title
    assert p["location"] is None
    assert p["commitment"] is None
    assert p["url"] is None
    assert p["description"] == ""
    assert p["posted_at"] is None
