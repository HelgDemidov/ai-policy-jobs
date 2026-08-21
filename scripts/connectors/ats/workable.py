"""Workable ATS connector — public widget API, no auth required.

The account-level widget (`?full=true`) doesn't carry description text; each
posting has its own dedicated Markdown export
(`{slug}/jobs/view/{shortcode}.md`) — cleaner than scraping the HTML job
page, and doesn't need an HTML stripper like the other connectors.
"""
import requests

LIST_API = "https://apply.workable.com/api/v1/widget/accounts/{slug}"
DETAIL_MD_URL = "https://apply.workable.com/{slug}/jobs/view/{shortcode}.md"


def _location(job: dict) -> str | None:
    parts = [job.get("city"), job.get("state"), job.get("country")]
    return ", ".join(p for p in parts if p) or None


def fetch(slug: str) -> list[dict]:
    resp = requests.get(LIST_API.format(slug=slug), params={"full": "true"}, timeout=20)
    resp.raise_for_status()
    postings = []
    for job in resp.json().get("jobs", []):
        detail = requests.get(DETAIL_MD_URL.format(slug=slug, shortcode=job["shortcode"]), timeout=20)
        description = detail.text.strip() if detail.status_code == 200 else ""
        postings.append({
            "ats_id": job["shortcode"],
            "title": job["title"],
            "location": _location(job),
            "workplace_type": "remote" if job.get("telecommuting") else None,
            "team": job.get("department"),
            "commitment": job.get("employment_type"),
            "url": job.get("url"),
            "description": description,
            "posted_at": job.get("published_on") or None,
        })
    return postings
