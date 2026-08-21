"""iCIMS ATS connector — sits behind an AWS WAF JS challenge, needs a
headless browser to get past it (scripts/browser_resolver.py, Lightpanda).
Plain `requests` gets a "Human Verification" CAPTCHA page on every iCIMS
board tested (CFR/Brookings/AEI, live-verified 2026-08-21) — see
docs/tech_specs/point-source-connectors/spec.md §1.

The actual listing lives inside a child iframe (`&in_iframe=1`), not the
top-level document — `browser_resolver.resolve(..., frame_url_contains=...)`
targets it directly. iCIMS embeds its own analytics payload,
`var jobImpressions = [...]`, with clean structured per-posting data — used
instead of parsing table markup; only the detail-page description still
needs HTML parsing.

Each detail-page description is its own headless-browser call — live-timed
at 2026-08-21 CFR (~23 postings): sequential fetches did not finish inside
5 minutes, so detail fetches run concurrently (bounded pool — Lightpanda
process-per-call, not a shared browser, so parallel calls don't collide)
with a shorter wait than the list page needs (detail pages don't carry the
listing table's own render/filter-widget work).
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor

import browser_resolver
from bs4 import BeautifulSoup

LIST_URL = "https://{slug}.icims.com/jobs/search?ss=1"
IMPRESSIONS_RE = re.compile(r"var jobImpressions\s*=\s*(\[.*?\]);", re.DOTALL)
DETAIL_HREF_RE = re.compile(r'href="(https://[^"]*?/jobs/(\d+)/[^"]*?/job)(?:\?[^"]*)?"')
DETAIL_WAIT_MS = 4000
DETAIL_WORKERS = 5


def _location(entry: dict) -> str | None:
    loc = entry.get("location") or {}
    parts = [loc.get("city"), loc.get("state")]
    return ", ".join(p for p in parts if p) or None


def _description(url: str) -> str:
    result = browser_resolver.resolve(url, wait_ms=DETAIL_WAIT_MS, frame_url_contains="in_iframe=1")
    if not result.ok:
        return ""
    box = BeautifulSoup(result.html, "lxml").select_one(".iCIMS_JobContent")
    return box.get_text("\n", strip=True) if box is not None else ""


def fetch(slug: str) -> list[dict]:
    result = browser_resolver.resolve(LIST_URL.format(slug=slug), frame_url_contains="in_iframe=1")
    if not result.ok:
        raise RuntimeError(f"icims: browser resolve failed for {slug!r}: {result.error}")

    match = IMPRESSIONS_RE.search(result.html)
    if not match:
        return []
    entries = json.loads(match.group(1))
    urls_by_id = {job_id: url for url, job_id in DETAIL_HREF_RE.findall(result.html)}
    urls = [urls_by_id.get(str(entry["idRaw"])) for entry in entries]

    with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as pool:
        descriptions = list(pool.map(lambda u: _description(u) if u else "", urls))

    postings = []
    for entry, url, description in zip(entries, urls, descriptions, strict=True):
        postings.append({
            "ats_id": str(entry["idRaw"]),
            "title": entry["title"],
            "location": _location(entry),
            "workplace_type": None,
            "team": entry.get("category"),
            "commitment": entry.get("positionType"),
            "url": url,
            "description": description,
            "posted_at": entry.get("postedDate"),
        })
    return postings
