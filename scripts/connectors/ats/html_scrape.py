"""Generic bespoke HTML-scrape connector — for organizations with no shared
ATS platform (no JSON API, no recognizable HTML template across other
orgs). Two-step: find candidate posting links on the career page, then
clean each detail page's text with `trafilatura` (same tool as G2AI_ME's
`convert/converters.py` — used here only to clean the text of ONE already-
found posting, not to discover the list itself, a different task).

Fields other than title/url/description aren't reliably parseable from
arbitrary markup — left `None` rather than guessed, unlike structured ATS
connectors where the platform's own API/template supplies them.
"""
import re
from urllib.parse import urljoin

import requests
import trafilatura
from bs4 import BeautifulSoup

LINK_PATTERN = re.compile(r"job|career|position|opening|vacanc", re.IGNORECASE)


def _candidate_links(soup: BeautifulSoup, base_url: str, list_selector: str | None) -> list[str]:
    containers = soup.select(list_selector) if list_selector else [soup]
    links: list[str] = []
    seen: set[str] = set()
    for container in containers:
        for a in container.find_all("a", href=True):
            href = str(a["href"])
            # A selector already scopes to the listing — trust every link
            # inside it. Without one, fall back to a href/text keyword match
            # against the whole page (noisier — nav/footer links included).
            if not (list_selector or LINK_PATTERN.search(href) or LINK_PATTERN.search(a.get_text())):
                continue
            full_url = urljoin(base_url, href)
            if not full_url.startswith(("http://", "https://")) or full_url == base_url:
                continue  # mailto:/tel:/javascript: links, or the career page linking to itself
            if full_url not in seen:
                seen.add(full_url)
                links.append(full_url)
    return links


TITLE_SEPARATOR_RE = re.compile(r"\s+[|–—→]\s+|\s+-\s+")


def _title(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    title_tag = soup.find("title")
    if title_tag is not None:
        text = title_tag.get_text(strip=True)
        # <title> usually leads with the posting's own name, then a
        # separator, then the site name ("Job Name | Org", "Job Name -
        # Org", "Job Name → Org") — take the first segment. Live-observed
        # variance across the bespoke-tier sample (2026-08-21): <h1> is
        # NOT a safe fallback-first choice — some sites (CSET) reuse a
        # generic site-wide <h1> on every page, unrelated to the posting.
        first_segment = TITLE_SEPARATOR_RE.split(text, maxsplit=1)[0].strip()
        if first_segment:
            return first_segment
    h1_tag = soup.find("h1")
    return h1_tag.get_text(strip=True) if h1_tag is not None else None


def fetch(url: str, list_selector: str | None = None) -> list[dict]:
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    postings = []
    for link in _candidate_links(soup, url, list_selector):
        try:
            detail = requests.get(link, timeout=20)
        except requests.RequestException:
            continue  # isolate one bad link (dead redirect, DNS failure, ...) from the rest of the batch
        if not detail.ok:
            continue
        description = trafilatura.extract(detail.text, output_format="markdown", favor_recall=True) or ""
        postings.append({
            "ats_id": link,
            "title": _title(detail.text) or link,
            "location": None,
            "workplace_type": None,
            "team": None,
            "commitment": None,
            "url": link,
            "description": description,
            "posted_at": None,
        })
    return postings
