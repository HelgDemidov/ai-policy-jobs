"""UN Secretariat query-centric connector — one public JSON feed for the
whole Secretariat's active postings (~400+ at a time, every department,
every duty station), filtered by `dept.name`. Live-verified 2026-08-21
against `careers.un.org` — see docs/tech_specs/point-source-connectors/spec.md §1.

Query-centric, not org-centric: unlike Lever/Greenhouse/one-org-per-slug,
this single endpoint returns many organizations at once and each posting
carries its own `org` (`dept.name`) — same shape as adzuna.py/jobspy_search.py.

Needs a `Referer` header — CloudFront's WAF returns 403 without it (a plain
`requests.get()` with no headers gets blocked; this isn't the AWS WAF *JS
challenge* that blocks iCIMS, just a header check, so no headless browser
needed here).
"""
import re

import requests

API = "https://careers.un.org/api/public/opening/jo/activeJo?language=en"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://careers.un.org/jobfeed?isPage=true",
}


def _strip_html(html: str) -> str:
    text = re.sub(r"<li>", "\n- ", html or "")
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def fetch(spec: dict) -> list[dict]:
    allowlist = set(spec.get("dept_allowlist") or [])
    resp = requests.get(API, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    postings = []
    for job in resp.json().get("data", []):
        dept_name = (job.get("dept") or {}).get("name")
        if dept_name not in allowlist:
            continue
        duty_stations = job.get("dutyStation") or []
        location = duty_stations[0].get("description") if duty_stations else None
        postings.append({
            "ats_id": str(job["jobId"]),
            "org": dept_name,
            "title": job.get("postingTitle") or job.get("jobTitle"),
            "location": location,
            "workplace_type": None,
            "team": (job.get("jf") or {}).get("Name") or (job.get("jf") or {}).get("name"),
            "commitment": (job.get("recrType") or {}).get("name"),
            "url": f"https://careers.un.org/jobSearchDescription/{job['jobId']}",
            "description": _strip_html(job.get("jobDescription", "")),
            "posted_at": (job.get("startDate") or "")[:10] or None,
        })
    return postings
