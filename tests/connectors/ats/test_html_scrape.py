"""Tests for the generic bespoke HTML-scrape connector
(scripts/connectors/ats/html_scrape.py)."""
import browser_resolver
import requests_mock
from connectors.ats import html_scrape

LIST_HTML = """
<html><body>
<nav><a href="/about">About</a></nav>
<div id="listing">
  <a href="/job/policy-analyst">Policy Analyst</a>
  <a href="mailto:jobs@testco.org">Email us</a>
</div>
<a href="https://testco.org/careers">Careers</a>
</body></html>
"""

DETAIL_HTML = """
<html><head><title>Policy Analyst - TestCo</title></head>
<body><h1>Policy Analyst</h1><p>Join our research team.</p><p>Second paragraph here.</p></body></html>
"""


def test_fetch_finds_links_by_keyword_heuristic_without_selector():
    with requests_mock.Mocker() as m:
        m.get("https://testco.org/careers", text=LIST_HTML)
        m.get("https://testco.org/job/policy-analyst", text=DETAIL_HTML)
        result = html_scrape.fetch("https://testco.org/careers")

    assert len(result) == 1
    p = result[0]
    assert p["url"] == "https://testco.org/job/policy-analyst"
    assert p["ats_id"] == "https://testco.org/job/policy-analyst"
    assert p["title"] == "Policy Analyst"
    assert "Join our research team." in p["description"]
    assert "Second paragraph here." in p["description"]
    assert p["location"] is None
    assert p["workplace_type"] is None


def test_fetch_skips_mailto_and_self_links():
    with requests_mock.Mocker() as m:
        m.get("https://testco.org/careers", text=LIST_HTML)
        m.get("https://testco.org/job/policy-analyst", text=DETAIL_HTML)
        result = html_scrape.fetch("https://testco.org/careers")
    urls = [p["url"] for p in result]
    assert "mailto:jobs@testco.org" not in urls
    assert "https://testco.org/careers" not in urls


def test_fetch_uses_list_selector_to_scope_when_given():
    html_with_selector = """
    <html><body>
    <div class="jobs-listing">
      <a href="/opening/analyst">Analyst Role</a>
    </div>
    <div class="footer"><a href="/opening/unrelated-in-footer">Should be excluded</a></div>
    </body></html>
    """
    with requests_mock.Mocker() as m:
        m.get("https://testco.org/careers", text=html_with_selector)
        m.get("https://testco.org/opening/analyst", text=DETAIL_HTML)
        result = html_scrape.fetch("https://testco.org/careers", list_selector=".jobs-listing")

    assert len(result) == 1
    assert result[0]["url"] == "https://testco.org/opening/analyst"


def test_fetch_empty_page_returns_empty_list():
    with requests_mock.Mocker() as m:
        m.get("https://emptyco.org/careers", text="<html><body>No openings.</body></html>")
        result = html_scrape.fetch("https://emptyco.org/careers")
    assert result == []


def test_fetch_isolates_one_broken_detail_link():
    with requests_mock.Mocker() as m:
        m.get("https://testco.org/careers", text=LIST_HTML)
        m.get("https://testco.org/job/policy-analyst", status_code=500)
        result = html_scrape.fetch("https://testco.org/careers")
    assert result == []


def test_fetch_uses_anchor_text_as_primary_title_source():
    # A generic/misleading <title> on the detail page must NOT win over the
    # listing's own label for this specific posting — live-observed
    # 2026-08-21 (GPPi, OSCE, Bertelsmann Stiftung all have this shape).
    misleading_title_html = "<html><head><title>Apply now! Jobs</title></head><body></body></html>"
    with requests_mock.Mocker() as m:
        m.get("https://testco.org/careers", text=LIST_HTML)
        m.get("https://testco.org/job/policy-analyst", text=misleading_title_html)
        result = html_scrape.fetch("https://testco.org/careers")
    assert result[0]["title"] == "Policy Analyst"  # the link's own anchor text, not "Apply now! Jobs"


def test_fetch_falls_back_to_detail_page_title_when_anchor_text_too_short():
    icon_only_list = """
    <html><body><a href="/job/policy-analyst">JD</a></body></html>
    """
    with requests_mock.Mocker() as m:
        m.get("https://testco.org/careers", text=icon_only_list)
        m.get("https://testco.org/job/policy-analyst", text=DETAIL_HTML)
        result = html_scrape.fetch("https://testco.org/careers")
    assert result[0]["title"] == "Policy Analyst"  # from the detail page's <title>, anchor text "JD" too short


def test_fetch_falls_back_to_url_when_neither_title_nor_anchor_text_found():
    no_title_html = "<html><body><p>No heading here.</p></body></html>"
    empty_anchor_list = """
    <html><body><a href="/job/policy-analyst"><img src="icon.png"></a></body></html>
    """
    with requests_mock.Mocker() as m:
        m.get("https://testco.org/careers", text=empty_anchor_list)
        m.get("https://testco.org/job/policy-analyst", text=no_title_html)
        result = html_scrape.fetch("https://testco.org/careers")
    assert result[0]["title"] == "https://testco.org/job/policy-analyst"


def test_fetch_sends_no_custom_user_agent_by_default():
    # Some bespoke sites 403 A REAL browser UA specifically (CSER,
    # live-observed 2026-08-21) — the default must stay requests' own UA.
    with requests_mock.Mocker() as m:
        m.get("https://testco.org/careers", text=LIST_HTML)
        m.get("https://testco.org/job/policy-analyst", text=DETAIL_HTML)
        html_scrape.fetch("https://testco.org/careers")
    assert "python-requests" in m.request_history[0].headers["User-Agent"]


def test_fetch_sends_browser_user_agent_when_use_browser_ua_is_set():
    with requests_mock.Mocker() as m:
        m.get("https://testco.org/careers", text=LIST_HTML)
        m.get("https://testco.org/job/policy-analyst", text=DETAIL_HTML)
        html_scrape.fetch("https://testco.org/careers", use_browser_ua=True)
    assert "Mozilla" in m.request_history[0].headers["User-Agent"]


def test_fetch_uses_browser_resolver_when_needs_browser_is_set(monkeypatch):
    calls = []

    def _fake_resolve(url, **kwargs):
        calls.append(url)
        html = LIST_HTML if url == "https://testco.org/careers" else DETAIL_HTML
        return browser_resolver.BrowserResult(ok=True, html=html, final_url=url, error="")

    monkeypatch.setattr(browser_resolver, "resolve", _fake_resolve)
    result = html_scrape.fetch("https://testco.org/careers", needs_browser=True)

    assert calls == ["https://testco.org/careers", "https://testco.org/job/policy-analyst"]
    assert len(result) == 1
    assert result[0]["title"] == "Policy Analyst"


def test_fetch_returns_empty_list_when_browser_resolve_fails(monkeypatch):
    def _fake_resolve(url, **kwargs):
        return browser_resolver.BrowserResult(ok=False, html="", final_url=url, error="timeout")

    monkeypatch.setattr(browser_resolver, "resolve", _fake_resolve)
    result = html_scrape.fetch("https://testco.org/careers", needs_browser=True)
    assert result == []
