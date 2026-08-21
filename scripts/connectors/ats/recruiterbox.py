"""Recruiterbox (now rebranded Trakstar Hire) ATS connector — public RSS
feed, no auth required. `slug` is the org's Trakstar subdomain (e.g. "cdt"
for cdt.hire.trakstar.com).
"""
import html
import re
import xml.etree.ElementTree as ET

import requests

FEED_URL = "https://{slug}.hire.trakstar.com/jobfeeds/{slug}"
# The feed's <description> leads with a "job_meta" block giving the
# location as free text ("Location: City,State,Country") before the real
# job description — pulled out separately so it doesn't pollute the text.
LOCATION_RE = re.compile(r"Location:\s*([^<\n]*)", re.IGNORECASE)


def _strip_html(raw: str) -> str:
    text = re.sub(r"<li>", "\n- ", raw or "")
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()  # feed content is double-escaped (XML entity, then HTML entity)


def fetch(slug: str) -> list[dict]:
    resp = requests.get(FEED_URL.format(slug=slug), timeout=20)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    postings = []
    for item in root.findall(".//item"):
        title = html.unescape((item.findtext("title") or "").strip())
        url = (item.findtext("link") or "").strip()
        raw_description = item.findtext("description") or ""
        location_match = LOCATION_RE.search(raw_description)
        location = html.unescape(location_match.group(1).strip().rstrip(",")) if location_match else None

        job_id = url.rstrip("/").rsplit("/", 1)[-1] if url else title
        postings.append({
            "ats_id": job_id,
            "title": title,
            "location": location or None,
            "workplace_type": None,
            "team": None,
            "commitment": None,
            "url": url or None,
            "description": _strip_html(raw_description),
            "posted_at": None,
        })
    return postings
