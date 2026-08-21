"""Tests for the iCIMS ATS connector (scripts/connectors/ats/icims.py)."""
import browser_resolver
from connectors.ats import icims

LIST_HTML = """
<html><body>
<a href="https://testco.icims.com/jobs/3005/library-assistant/job?in_iframe=1">Library Assistant</a>
<script type="text/javascript">
var jobImpressions = [{"positionType":"Regular Full-Time","location":{"city":"Washington","state":"DC"},
"idRaw":3005,"position":1,"title":"Library Assistant","category":"Education/Training","postedDate":"2026-08-19"}];
</script>
</body></html>
"""

DETAIL_HTML = """
<html><body>
<div class="iCIMS_JobContent"><p>Support the library.</p><p>Second paragraph.</p></div>
</body></html>
"""


def _fake_resolve_factory(responses: dict):
    def _resolve(url, *, wait_ms=9000, timeout=45, frame_url_contains=None):
        for key, html in responses.items():
            if key in url:
                return browser_resolver.BrowserResult(ok=True, html=html, final_url=url, error="")
        return browser_resolver.BrowserResult(ok=False, html="", final_url=url, error="not mocked")
    return _resolve


def test_fetch_parses_all_fields(monkeypatch):
    monkeypatch.setattr(
        browser_resolver,
        "resolve",
        _fake_resolve_factory({"jobs/search": LIST_HTML, "jobs/3005": DETAIL_HTML}),
    )
    result = icims.fetch("testco")

    assert len(result) == 1
    p = result[0]
    assert p["ats_id"] == "3005"
    assert p["title"] == "Library Assistant"
    assert p["location"] == "Washington, DC"
    assert p["workplace_type"] is None
    assert p["team"] == "Education/Training"
    assert p["commitment"] == "Regular Full-Time"
    assert p["url"] == "https://testco.icims.com/jobs/3005/library-assistant/job"
    assert p["posted_at"] == "2026-08-19"
    assert "Support the library." in p["description"]
    assert "Second paragraph." in p["description"]


def test_fetch_raises_when_list_page_resolve_fails(monkeypatch):
    def _resolve(url, *, wait_ms=9000, timeout=45, frame_url_contains=None):
        return browser_resolver.BrowserResult(ok=False, html="", final_url=url, error="WAF blocked")

    monkeypatch.setattr(browser_resolver, "resolve", _resolve)
    try:
        icims.fetch("testco")
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "WAF blocked" in str(exc)


def test_fetch_empty_board_returns_empty_list(monkeypatch):
    empty_html = "<html><body><script>var jobImpressions = [];</script></body></html>"
    monkeypatch.setattr(browser_resolver, "resolve", _fake_resolve_factory({"jobs/search": empty_html}))
    result = icims.fetch("emptyco")
    assert result == []


def test_fetch_handles_missing_impressions_variable(monkeypatch):
    monkeypatch.setattr(
        browser_resolver, "resolve", _fake_resolve_factory({"jobs/search": "<html><body>no jobs here</body></html>"})
    )
    result = icims.fetch("weirdco")
    assert result == []


def test_fetch_handles_missing_detail_url(monkeypatch):
    list_html = """
    <html><body>
    <script type="text/javascript">
    var jobImpressions = [{"positionType":"Full-Time","location":{},
    "idRaw":9999,"position":1,"title":"Untitled Role","category":null,"postedDate":null}];
    </script>
    </body></html>
    """
    monkeypatch.setattr(browser_resolver, "resolve", _fake_resolve_factory({"jobs/search": list_html}))
    result = icims.fetch("testco")

    p = result[0]
    assert p["url"] is None
    assert p["description"] == ""
    assert p["location"] is None
