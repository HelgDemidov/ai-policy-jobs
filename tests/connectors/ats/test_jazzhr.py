"""Tests for the JazzHR ATS connector (scripts/connectors/ats/jazzhr.py)."""
import requests_mock
from connectors.ats import jazzhr

LIST_HTML = """
<html><body>
<h2>Current Openings</h2>
<ul class='list-group'>
  <li class="list-group-item">
    <h3 class='list-group-item-heading'>
      <a href="https://testco.applytojob.com/apply/abc123/Policy-Analyst">
        Policy Analyst
      </a>
    </h3>
    <ul class='list-inline list-group-item-text'>
      <li><i class='fa fa-map-marker'></i>Washington, DC</li>
      <li><i class='fa fa-sitemap'></i>Research</li>
    </ul>
  </li>
</ul>
</body></html>
"""

DETAIL_HTML = """
<html><body>
<div id="job-description">
  <p>Support our policy research.</p>
  <p>Second paragraph.</p>
</div>
</body></html>
"""


def test_fetch_parses_all_fields():
    with requests_mock.Mocker() as m:
        m.get("https://testco.applytojob.com/apply", text=LIST_HTML)
        m.get("https://testco.applytojob.com/apply/abc123/Policy-Analyst", text=DETAIL_HTML)
        result = jazzhr.fetch("testco")

    assert len(result) == 1
    p = result[0]
    assert p["ats_id"] == "abc123"
    assert p["title"] == "Policy Analyst"
    assert p["location"] == "Washington, DC"
    assert p["workplace_type"] is None
    assert p["team"] == "Research"
    assert p["url"] == "https://testco.applytojob.com/apply/abc123/Policy-Analyst"
    assert "Support our policy research." in p["description"]
    assert "Second paragraph." in p["description"]


def test_fetch_empty_board_returns_empty_list():
    with requests_mock.Mocker() as m:
        m.get("https://emptyco.applytojob.com/apply", text="<html><body><h2>Current Openings</h2></body></html>")
        result = jazzhr.fetch("emptyco")
    assert result == []


def test_fetch_handles_missing_meta_and_failed_detail_fetch():
    minimal_list = """
    <html><body><ul class='list-group'>
      <li class="list-group-item">
        <h3 class='list-group-item-heading'>
          <a href="https://testco.applytojob.com/apply/x1/Some-Role">Some Role</a>
        </h3>
        <ul class='list-inline list-group-item-text'></ul>
      </li>
    </ul></body></html>
    """
    with requests_mock.Mocker() as m:
        m.get("https://testco.applytojob.com/apply", text=minimal_list)
        m.get("https://testco.applytojob.com/apply/x1/Some-Role", status_code=404)
        result = jazzhr.fetch("testco")

    p = result[0]
    assert p["location"] is None
    assert p["team"] is None
    assert p["description"] == ""
