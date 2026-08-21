"""JazzHR ATS connector — server-rendered career page, no auth required.

Both the list and detail pages are plain HTML (no JS, no API needed) — same
template across every JazzHR-hosted board (`{slug}.applytojob.com`), so one
parser works for all of them. Live-verified 2026-08-21 against Heritage
Foundation; see docs/tech_specs/point-source-connectors/spec.md §1.
"""
import requests
from bs4 import BeautifulSoup

LIST_URL = "https://{slug}.applytojob.com/apply"


def _meta(item) -> tuple[str | None, str | None]:
    location = None
    team = None
    for li in item.select("ul.list-group-item-text li"):
        icon = li.select_one("i")
        classes = icon.get("class", []) if icon else []
        text = li.get_text(strip=True)
        if "fa-map-marker" in classes:
            location = text
        elif "fa-sitemap" in classes:
            team = text
    return location, team


def _description(url: str) -> str:
    resp = requests.get(url, timeout=20)
    if not resp.ok:
        return ""
    box = BeautifulSoup(resp.text, "lxml").select_one("#job-description")
    return box.get_text("\n", strip=True) if box is not None else ""


def fetch(slug: str) -> list[dict]:
    resp = requests.get(LIST_URL.format(slug=slug), timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    postings = []
    for item in soup.select("li.list-group-item"):
        link = item.select_one("h3.list-group-item-heading a")
        if link is None or not link.get("href"):
            continue
        url = link["href"]
        location, team = _meta(item)
        postings.append({
            "ats_id": url.rstrip("/").split("/")[-2],
            "title": link.get_text(strip=True),
            "location": location,
            "workplace_type": None,
            "team": team,
            "commitment": None,
            "url": url,
            "description": _description(url),
            "posted_at": None,
        })
    return postings
