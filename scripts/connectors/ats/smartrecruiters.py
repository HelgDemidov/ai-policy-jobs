"""SmartRecruiters ATS connector — public postings API, no auth required.

Unlike Lever, the list endpoint is paginated and doesn't carry full
descriptions or a direct posting URL — each posting needs one extra request
to the detail endpoint (same shape as Greenhouse's ?content=true pattern).
"""
import re

import requests

LIST_API = "https://api.smartrecruiters.com/v1/companies/{slug}/postings"
DETAIL_API = "https://api.smartrecruiters.com/v1/companies/{slug}/postings/{posting_id}"
PAGE_SIZE = 100


def _strip_html(html: str) -> str:
    text = re.sub(r"<li>", "\n- ", html or "")
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def _fetch_list(slug: str) -> list[dict]:
    postings = []
    offset = 0
    while True:
        resp = requests.get(
            LIST_API.format(slug=slug), params={"limit": PAGE_SIZE, "offset": offset}, timeout=20
        )
        resp.raise_for_status()
        data = resp.json()
        postings.extend(data.get("content", []))
        offset += PAGE_SIZE
        if offset >= data.get("totalFound", 0):
            break
    return postings


def _workplace_type(location: dict) -> str | None:
    if location.get("remote"):
        return "remote"
    if location.get("hybrid"):
        return "hybrid"
    return None


def fetch(slug: str) -> list[dict]:
    postings = []
    for job in _fetch_list(slug):
        detail = requests.get(DETAIL_API.format(slug=slug, posting_id=job["id"]), timeout=20)
        detail.raise_for_status()
        detail_data = detail.json()
        sections = (detail_data.get("jobAd") or {}).get("sections") or {}
        parts = [f"{s.get('title', '')}\n{_strip_html(s.get('text', ''))}" for s in sections.values()]
        location = job.get("location") or {}
        postings.append({
            "ats_id": str(job["id"]),
            "title": job["name"],
            "location": location.get("fullLocation"),
            "workplace_type": _workplace_type(location),
            "team": (job.get("department") or {}).get("label"),
            "commitment": (job.get("typeOfEmployment") or {}).get("label"),
            "url": detail_data.get("postingUrl"),
            "description": "\n\n".join(parts).strip(),
            "posted_at": (job.get("releasedDate") or "")[:10] or None,
        })
    return postings
