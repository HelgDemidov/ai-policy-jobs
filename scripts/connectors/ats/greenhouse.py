"""Greenhouse ATS connector — public boards API, no auth required.

Unlike Lever, the list endpoint doesn't carry full descriptions, so each
posting needs one extra request (?content=true) to fetch the body.
"""
import re

import requests

LIST_API = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
DETAIL_API = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}?content=true"


def _strip_html(html: str) -> str:
    text = re.sub(r"<li>", "\n- ", html or "")
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def fetch(slug: str) -> list[dict]:
    resp = requests.get(LIST_API.format(slug=slug), timeout=20)
    resp.raise_for_status()
    postings = []
    for job in resp.json().get("jobs", []):
        detail = requests.get(DETAIL_API.format(slug=slug, job_id=job["id"]), timeout=20)
        detail.raise_for_status()
        content = detail.json().get("content", "")
        postings.append({
            "ats_id": str(job["id"]),
            "title": job["title"],
            "location": (job.get("location") or {}).get("name"),
            "workplace_type": None,
            "team": None,
            "commitment": None,
            "url": job.get("absolute_url"),
            "description": _strip_html(content),
            "posted_at": (job.get("updated_at") or "")[:10] or None,
        })
    return postings
