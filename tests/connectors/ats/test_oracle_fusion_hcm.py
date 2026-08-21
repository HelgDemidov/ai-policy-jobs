"""Tests for the Oracle Fusion Cloud HCM ATS connector
(scripts/connectors/ats/oracle_fusion_hcm.py)."""
import requests_mock
from connectors.ats import oracle_fusion_hcm

JOB = {
    "Id": "34443",
    "Title": "Technical Programme Support Specialist",
    "PostedDate": "2026-08-19",
    "PrimaryLocation": "New York, United States",
    "WorkplaceType": "Remote",
    "Organization": "Chief Digital Office",
    "WorkerType": "Employee",
    "ShortDescriptionStr": "Duties and Responsibilities",
}


def _payload(jobs, total):
    return {"items": [{"TotalJobsCount": total, "requisitionList": jobs}]}


def test_fetch_parses_all_fields():
    with requests_mock.Mocker() as m:
        m.get("https://testco.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
              json=_payload([JOB], 1))
        result = oracle_fusion_hcm.fetch("testco.oraclecloud.com:CX_1")

    assert len(result) == 1
    p = result[0]
    assert p["ats_id"] == "34443"
    assert p["title"] == "Technical Programme Support Specialist"
    assert p["location"] == "New York, United States"
    assert p["workplace_type"] == "Remote"
    assert p["team"] == "Chief Digital Office"
    assert p["commitment"] == "Employee"
    assert p["url"] == "https://testco.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/34443"
    assert p["posted_at"] == "2026-08-19"
    assert p["description"] == "Duties and Responsibilities"


def test_fetch_paginates_past_first_page():
    page_one = _payload([{**JOB, "Id": str(i)} for i in range(25)], 30)
    page_two = _payload([{**JOB, "Id": str(i)} for i in range(25, 30)], 30)
    with requests_mock.Mocker() as m:
        m.get(
            "https://testco.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
            [{"json": page_one}, {"json": page_two}],
        )
        result = oracle_fusion_hcm.fetch("testco.oraclecloud.com:CX_1")
    assert len(result) == 30


def test_fetch_empty_board_returns_empty_list():
    with requests_mock.Mocker() as m:
        m.get("https://testco.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
              json=_payload([], 0))
        result = oracle_fusion_hcm.fetch("testco.oraclecloud.com:CX_1")
    assert result == []


def test_fetch_handles_missing_optional_fields():
    minimal = {"Id": "1", "Title": "Some Role"}
    with requests_mock.Mocker() as m:
        m.get("https://testco.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
              json=_payload([minimal], 1))
        result = oracle_fusion_hcm.fetch("testco.oraclecloud.com:CX_1")

    p = result[0]
    assert p["location"] is None
    assert p["workplace_type"] is None
    assert p["team"] is None
    assert p["commitment"] is None
    assert p["description"] == ""
    assert p["posted_at"] is None
