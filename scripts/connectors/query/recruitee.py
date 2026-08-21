"""UNU (United Nations University) query-centric connector — one shared
Recruitee-hosted feed for every UNU institute, filtered by department.
Same shape as query/un_secretariat.py — a single portal covering several
tracked "organizations" at once, each posting carrying its own `org`.

Live-verified 2026-08-21 (donabor wave 2): the standard Recruitee JSON API
is reachable directly on UNU's own custom domain (no need for the usual
`<slug>.recruitee.com` subdomain).
"""
import re

import requests

API = "https://careers.unu.edu/api/offers/"


def _strip_html(html: str) -> str:
    text = re.sub(r"<li>", "\n- ", html or "")
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def fetch(spec: dict) -> list[dict]:
    allowlist = set(spec.get("department_allowlist") or [])
    resp = requests.get(API, timeout=20)
    resp.raise_for_status()

    postings = []
    for job in resp.json().get("offers", []):
        department = job.get("department")
        if department not in allowlist:
            continue
        location = (job.get("location") or "").strip()
        postings.append({
            "ats_id": str(job["id"]),
            "org": department,
            "title": job.get("title"),
            "location": location or None,
            "workplace_type": "remote" if job.get("remote") else None,
            "team": None,
            "commitment": job.get("employment_type_code"),
            "url": job.get("careers_url"),
            "description": _strip_html(job.get("description", "")),
            "posted_at": (job.get("created_at") or "")[:10] or None,
        })
    return postings
