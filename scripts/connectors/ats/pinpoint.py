"""Pinpoint ATS connector — public postings.json feed, no auth required.

Like Teamtailor, each org runs its own Pinpoint career subdomain; `slug` is
that domain's host (e.g. "careers.rethinkpriorities.org"). Schema:
https://developers.pinpointhq.com/docs/jobs-json-endpoint — description
already HTML-formatted in the list response, no detail fetch needed.
"""
import re

import requests

FEED_URL = "https://{slug}/postings.json"


def _strip_html(html: str) -> str:
    text = re.sub(r"<li>", "\n- ", html or "")
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def fetch(slug: str) -> list[dict]:
    resp = requests.get(FEED_URL.format(slug=slug), timeout=20)
    resp.raise_for_status()
    postings = []
    for job in resp.json().get("data", []):
        postings.append({
            "ats_id": job["id"],
            "title": job["title"],
            "location": (job.get("location") or {}).get("name"),
            "workplace_type": job.get("workplace_type"),
            "team": (job.get("department") or {}).get("name"),
            "commitment": job.get("employment_type_text"),
            "url": job.get("url"),
            "description": _strip_html(job.get("description", "")),
            "posted_at": None,
        })
    return postings
