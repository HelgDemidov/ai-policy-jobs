"""BambooHR ATS connector — public careers/list JSON API, no auth required."""
import requests

LIST_API = "https://{slug}.bamboohr.com/careers/list"


def _location(job: dict) -> str | None:
    location = job.get("location") or {}
    parts = [location.get("city"), location.get("state")]
    return ", ".join(p for p in parts if p) or None


def fetch(slug: str) -> list[dict]:
    resp = requests.get(LIST_API.format(slug=slug), timeout=20)
    resp.raise_for_status()
    postings = []
    for job in resp.json().get("result", []):
        postings.append({
            "ats_id": str(job["id"]),
            "title": job["jobOpeningName"],
            "location": _location(job),
            "workplace_type": "remote" if job.get("isRemote") else None,
            "team": job.get("departmentLabel"),
            "commitment": job.get("employmentType"),
            "url": f"https://{slug}.bamboohr.com/careers/{job['id']}",
            "description": "",  # not in the list response; not worth a second request for this volume
            "posted_at": None,
        })
    return postings
