"""Lever ATS connector — public postings API, no auth required."""
import re
from datetime import datetime, timezone

import requests

API = "https://api.lever.co/v0/postings/{slug}?mode=json"


def _strip_html(html: str) -> str:
    text = re.sub(r"<li>", "\n- ", html or "")
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def fetch(slug: str) -> list[dict]:
    resp = requests.get(API.format(slug=slug), timeout=20)
    resp.raise_for_status()
    postings = []
    for p in resp.json():
        parts = [p.get("descriptionBodyPlain") or p.get("descriptionPlain") or ""]
        for section in p.get("lists", []):
            parts.append(f"\n{section.get('text', '')}\n{_strip_html(section.get('content', ''))}")
        posted_at = None
        if p.get("createdAt"):
            posted_at = datetime.fromtimestamp(p["createdAt"] / 1000, tz=timezone.utc).date().isoformat()
        categories = p.get("categories", {})
        postings.append({
            "ats_id": p["id"],
            "title": p["text"],
            "location": categories.get("location"),
            "workplace_type": p.get("workplaceType"),
            "team": categories.get("team"),
            "commitment": categories.get("commitment"),
            "url": p.get("hostedUrl"),
            "description": "\n".join(parts).strip(),
            "posted_at": posted_at,
        })
    return postings
