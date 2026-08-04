"""Tests for the Personio ATS connector (scripts/connectors/ats/personio.py)."""
import requests_mock
from connectors.ats import personio

SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<workzag-jobs>
<position>
    <id>2727652</id>
    <subcompany>Centre for Liberal Strategies (CLS) - ECFR Sofia</subcompany>
    <office>Sofia</office>
    <department>Finance &amp; Accounting</department>
    <recruitingCategory>Shared Service Accountant</recruitingCategory>
    <name>Shared Service Accountant (m/f/d) - Maternity Cover (4 months)</name>
    <jobDescriptions>
        <jobDescription>
            <name>Job Purpose</name>
            <value><![CDATA[Working closely with the Finance Director.]]></value>
        </jobDescription>
        <jobDescription>
            <name>Main Responsibilities</name>
            <value><![CDATA[<ul><li>Process invoices</li><li>Manage cash</li></ul>]]></value>
        </jobDescription>
    </jobDescriptions>
    <employmentType>fixed_term</employmentType>
    <seniority>experienced</seniority>
    <schedule>full-time</schedule>
    <yearsOfExperience>2-5</yearsOfExperience>
    <keywords>thinktank,accounts payable,</keywords>
    <occupation>accounts_payable_and_receivable</occupation>
    <occupationCategory>accounting_and_finance</occupationCategory>
    <createdAt>2026-07-24T12:32:13+00:00</createdAt>
</position>
</workzag-jobs>
"""

EMPTY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<workzag-jobs>
</workzag-jobs>
"""


def test_fetch_parses_fields_and_builds_job_url():
    with requests_mock.Mocker() as m:
        m.get("https://ecfr.jobs.personio.com/xml", text=SAMPLE_XML)
        result = personio.fetch("ecfr")

    assert len(result) == 1
    p = result[0]
    assert p["ats_id"] == "2727652"
    assert p["title"] == "Shared Service Accountant (m/f/d) - Maternity Cover (4 months)"
    assert p["location"] == "Sofia"
    assert p["team"] == "Finance & Accounting"
    assert p["commitment"] == "full-time"
    assert p["workplace_type"] is None
    assert p["url"] == "https://ecfr.jobs.personio.com/job/2727652"
    assert p["posted_at"] == "2026-07-24"


def test_fetch_assembles_description_and_strips_html():
    with requests_mock.Mocker() as m:
        m.get("https://ecfr.jobs.personio.com/xml", text=SAMPLE_XML)
        result = personio.fetch("ecfr")

    description = result[0]["description"]
    assert "Job Purpose" in description
    assert "Working closely with the Finance Director." in description
    assert "Main Responsibilities" in description
    assert "Process invoices" in description
    assert "<li>" not in description
    assert "<ul>" not in description


def test_fetch_empty_board_returns_empty_list():
    with requests_mock.Mocker() as m:
        m.get("https://somecompany.jobs.personio.com/xml", text=EMPTY_XML)
        result = personio.fetch("somecompany")
    assert result == []
