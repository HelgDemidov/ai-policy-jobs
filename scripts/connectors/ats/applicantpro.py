"""ApplicantPro ATS connector — public core/jobs JSON API, no auth
required. `slug` encodes both identifiers this pattern needs —
`{subdomain}:{domain_id}` (e.g. "carnegieendowment:2306") — same
compound-string rationale as workday.py. `getParams=%7B%7D` (URL-encoded
`{}`) is required — the endpoint 500s without any `getParams` at all, but
an empty JSON object satisfies it.
"""
import requests

LIST_API = "https://{subdomain}.applicantpro.com/core/jobs/{domain_id}"


def fetch(slug: str) -> list[dict]:
    subdomain, _, domain_id = slug.partition(":")
    url = LIST_API.format(subdomain=subdomain, domain_id=domain_id)
    resp = requests.get(url, params={"getParams": "{}"}, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    postings = []
    for job in data.get("data", {}).get("jobs", []):
        location = ", ".join(p for p in [job.get("city"), job.get("stateName")] if p) or None
        postings.append({
            "ats_id": str(job["id"]),
            "title": job.get("title"),
            "location": location,
            "workplace_type": "remote" if (job.get("workplaceType") or "").lower() == "remote" else None,
            "team": job.get("orgTitle") or job.get("parentTitle"),
            "commitment": job.get("employmentType"),
            "url": job.get("jobUrl"),
            "description": "",  # not in the list response; a per-posting detail call isn't worth it at this volume
            "posted_at": None,  # startDateRef is a human-readable string ("Jul 01, 2026"), not reliably parseable
        })
    return postings
