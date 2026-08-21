"""Tests for the Recruiterbox/Trakstar Hire ATS connector
(scripts/connectors/ats/recruiterbox.py)."""
import requests_mock
from connectors.ats import recruiterbox

FEED_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
<item>
<title>Policy Fellow &amp; Analyst</title>
<link>http://testco.hire.trakstar.com/jobs/abc123</link>
<description>&lt;h2 id="job_meta"&gt;&lt;p&gt;Location: Washington, DC &lt;/p&gt;&lt;/h2&gt;
&lt;div id="job_description"&gt;&lt;p&gt;Join our team&amp;rsquo;s work.&lt;/p&gt;
&lt;ul&gt;&lt;li&gt;Task one&lt;/li&gt;&lt;/ul&gt;&lt;/div&gt;</description>
</item>
</channel></rss>
"""


def test_fetch_parses_all_fields():
    with requests_mock.Mocker() as m:
        m.get("https://testco.hire.trakstar.com/jobfeeds/testco", text=FEED_XML)
        result = recruiterbox.fetch("testco")

    assert len(result) == 1
    p = result[0]
    assert p["ats_id"] == "abc123"
    assert p["title"] == "Policy Fellow & Analyst"
    assert p["location"] == "Washington, DC"
    assert p["url"] == "http://testco.hire.trakstar.com/jobs/abc123"
    assert "Join our team’s work." in p["description"]
    assert "Task one" in p["description"]
    assert "<li>" not in p["description"]
    assert "&rsquo;" not in p["description"]


def test_fetch_empty_feed_returns_empty_list():
    empty_feed = '<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
    with requests_mock.Mocker() as m:
        m.get("https://emptyco.hire.trakstar.com/jobfeeds/emptyco", text=empty_feed)
        result = recruiterbox.fetch("emptyco")
    assert result == []


def test_fetch_handles_missing_location():
    no_location_xml = """<?xml version="1.0"?><rss version="2.0"><channel>
    <item><title>Some Role</title><link>http://testco.hire.trakstar.com/jobs/x1</link>
    <description>&lt;p&gt;No location header here.&lt;/p&gt;</description></item>
    </channel></rss>
    """
    with requests_mock.Mocker() as m:
        m.get("https://testco.hire.trakstar.com/jobfeeds/testco", text=no_location_xml)
        result = recruiterbox.fetch("testco")
    assert result[0]["location"] is None
