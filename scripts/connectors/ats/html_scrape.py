"""Generic bespoke HTML-scrape connector — for organizations with no shared
ATS platform (no JSON API, no recognizable HTML template across other
orgs). Two-step: find candidate posting links on the career page, then
clean each detail page's text with `trafilatura` (same tool as G2AI_ME's
`convert/converters.py` — used here only to clean the text of ONE already-
found posting, not to discover the list itself, a different task).

Fields other than title/url/description aren't reliably parseable from
arbitrary markup — left `None` rather than guessed, unlike structured ATS
connectors where the platform's own API/template supplies them.

Two independent per-org escape hatches, both live-observed necessary
2026-08-21 (donabor wave 2) and both opt-in, not default-on — one site's
fix regresses another (CSER 403s WITH a browser User-Agent, CLTR/ITIF 403
or 504 WITHOUT one — same header cannot suit both):
- `needs_browser=True` — the listing only renders client-side (a JS-SPA
  shell, not just a WAF gate): routes through `scripts/browser_resolver.py`
  (Lightpanda) instead of plain `requests`. Same tool as the platform-tier
  iCIMS connector; here for Clingendael's OutSite/Connexys ATS, WIPO's
  Taleo.
- `use_browser_ua=True` — plain `requests` with no headers gets 403/504
  from a handful of bespoke sites unless it looks like a real browser.
"""
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

import browser_resolver
import requests
import trafilatura
from bs4 import BeautifulSoup

LINK_PATTERN = re.compile(r"job|career|position|opening|vacanc", re.IGNORECASE)
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
MIN_ANCHOR_TITLE_LEN = 3  # shorter than this is almost certainly an icon-only link, not real title text
BROWSER_DETAIL_WORKERS = 5  # same fix as icims.py: sequential Lightpanda calls didn't finish in 5 min on ~20 postings


def _fetch_html(url: str, needs_browser: bool, use_browser_ua: bool) -> str | None:
    if needs_browser:
        result = browser_resolver.resolve(url)
        return result.html if result.ok else None
    headers = {"User-Agent": BROWSER_USER_AGENT} if use_browser_ua else None
    try:
        resp = requests.get(url, headers=headers, timeout=20)
    except requests.RequestException:
        return None
    return resp.text if resp.ok else None


def _anchor_text(a) -> str:
    """The anchor's own label. Some ATS-white-label cards wrap a whole
    multi-line summary (title + description) in one <a> — plain
    get_text() would concatenate all of it. Splitting on block-element
    boundaries and taking the first line isolates the title, since it
    conventionally comes first (live-observed: BPC/Freshteam's
    `<a><div class="job-title">…</div><div class="job-desc">…</div></a>`)
    — general fix, not Freshteam-specific markup."""
    first_line = a.get_text(separator="\n", strip=True).split("\n", 1)[0]
    return first_line.strip()


def _candidate_links(soup: BeautifulSoup, base_url: str, list_selector: str | None) -> list[tuple[str, str]]:
    """Returns (url, anchor_text) pairs — anchor text is the PRIMARY title
    source (see fetch()): it's the site's own label for that specific
    posting, whereas a detail page's <title>/<h1> is sometimes generic and
    site-wide rather than posting-specific (live-observed: GPPi, OSCE,
    Bertelsmann Stiftung's "createyourowncareer" white-label).

    `list_selector` may target either a container (search it for <a> tags)
    or the <a> tags themselves directly (e.g. "td.jobLink a") — both are
    real selectors seen live 2026-08-21, handled the same way here."""
    if list_selector:
        selected = soup.select(list_selector)
        anchors = []
        for el in selected:
            if el.name == "a" and el.has_attr("href"):
                anchors.append(el)
            else:
                anchors.extend(el.find_all("a", href=True))
    else:
        anchors = [
            a for a in soup.find_all("a", href=True)
            if LINK_PATTERN.search(str(a["href"])) or LINK_PATTERN.search(a.get_text())
        ]

    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for a in anchors:
        full_url = urljoin(base_url, str(a["href"]))
        if not full_url.startswith(("http://", "https://")) or full_url == base_url:
            continue  # mailto:/tel:/javascript: links, or the career page linking to itself
        if full_url not in seen:
            seen.add(full_url)
            links.append((full_url, _anchor_text(a)))
    return links


TITLE_SEPARATOR_RE = re.compile(r"\s+[|–—→]\s+|\s+-\s+")


def _title_from_detail_page(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    title_tag = soup.find("title")
    if title_tag is not None:
        text = title_tag.get_text(strip=True)
        first_segment = TITLE_SEPARATOR_RE.split(text, maxsplit=1)[0].strip()
        if first_segment:
            return first_segment
    h1_tag = soup.find("h1")
    return h1_tag.get_text(strip=True) if h1_tag is not None else None


def _posting(link: str, anchor_text: str, detail_html: str) -> dict:
    """`detail_html` is always a real string here — fetch() filters out
    failed detail fetches before this is called."""
    description = trafilatura.extract(detail_html, output_format="markdown", favor_recall=True) or ""
    # Anchor text first (see _candidate_links docstring); detail page's own
    # <title>/<h1> as fallback when the anchor was icon-only/empty.
    title = anchor_text if len(anchor_text) >= MIN_ANCHOR_TITLE_LEN else None
    title = title or _title_from_detail_page(detail_html)
    return {
        "ats_id": link,
        "title": title or link,
        "location": None,
        "workplace_type": None,
        "team": None,
        "commitment": None,
        "url": link,
        "description": description,
        "posted_at": None,
    }


def fetch(
    url: str, list_selector: str | None = None, needs_browser: bool = False, use_browser_ua: bool = False
) -> list[dict]:
    list_html = _fetch_html(url, needs_browser, use_browser_ua)
    if list_html is None:
        return []
    soup = BeautifulSoup(list_html, "lxml")
    candidates = _candidate_links(soup, url, list_selector)

    if needs_browser:
        # Each browser_resolver.resolve() call spawns its own Lightpanda
        # process — same fix as icims.py, sequential calls are too slow
        # once an org has more than a handful of postings (live-observed:
        # WIPO, 14 postings, didn't finish in 2 minutes sequentially).
        with ThreadPoolExecutor(max_workers=BROWSER_DETAIL_WORKERS) as pool:
            detail_htmls = list(pool.map(lambda c: _fetch_html(c[0], needs_browser, use_browser_ua), candidates))
    else:
        detail_htmls = [_fetch_html(link, needs_browser, use_browser_ua) for link, _ in candidates]

    return [
        _posting(link, anchor_text, detail_html)
        for (link, anchor_text), detail_html in zip(candidates, detail_htmls, strict=True)
        if detail_html is not None
    ]
