"""Teamtailor ATS connector — public JSON Feed, no auth required.

Unlike SmartRecruiters, there's no central company registry — each org runs
its own Teamtailor career subdomain. `slug` here is that domain's host (e.g.
"careers.chathamhouse.org"), not a lookup key against a shared API.
"""
import re

import requests

FEED_URL = "https://{slug}/jobs.json"


def _strip_html(html: str) -> str:
    text = re.sub(r"<li>", "\n- ", html or "")
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def _location(jobposting: dict) -> str | None:
    locations = jobposting.get("jobLocation") or []
    if not locations:
        return None
    address = locations[0].get("address") or {}
    parts = [address.get("addressLocality"), address.get("addressCountry")]
    return ", ".join(p for p in parts if p) or None


def fetch(slug: str) -> list[dict]:
    resp = requests.get(FEED_URL.format(slug=slug), timeout=20)
    resp.raise_for_status()
    postings = []
    for item in resp.json().get("items", []):
        jobposting = item.get("_jobposting") or {}
        postings.append({
            "ats_id": item["id"],
            "title": item["title"],
            "location": _location(jobposting),
            "workplace_type": None,
            "team": None,
            "commitment": None,
            "url": item.get("url"),
            "description": _strip_html(item.get("content_html", "")),
            "posted_at": (item.get("date_published") or "")[:10] or None,
        })
    return postings
