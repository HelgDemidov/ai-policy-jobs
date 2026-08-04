"""Himalayas query-centric connector — public search API, no auth required.

Himalayas is a remote-only job board, so every posting is remote by
definition — workplace_type is hardcoded rather than inferred per-posting.
Unlike the ATS connectors, fetch() takes a search spec (not an org slug) and
each returned posting carries its own `org` — the caller doesn't know the
organization in advance.
"""
import re
import time
from datetime import datetime, timezone

import requests

API = "https://himalayas.app/jobs/api/search"
PAGES = 3


def _strip_html(html: str) -> str:
    text = re.sub(r"<li>", "\n- ", html or "")
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def fetch(spec: dict) -> list[dict]:
    query = spec["query"]
    postings = []
    for page in range(1, PAGES + 1):
        resp = requests.get(API, params={"q": query, "page": page}, timeout=20)
        resp.raise_for_status()
        jobs = resp.json().get("jobs", [])
        if not jobs:
            break
        for j in jobs:
            org = j.get("companyName")
            title = j.get("title")
            if not org or not title:
                continue  # вакансии без работодателя/названия — нетриажируемы
            posted_at = None
            if j.get("pubDate"):
                posted_at = datetime.fromtimestamp(j["pubDate"], tz=timezone.utc).date().isoformat()
            location_restrictions = j.get("locationRestrictions") or []
            postings.append({
                "ats_id": j["guid"],
                "org": org,
                "title": title,
                "location": ", ".join(location_restrictions) or None,
                "workplace_type": "remote",
                "team": None,
                "commitment": j.get("employmentType"),
                "url": j.get("applicationLink") or j["guid"],
                "description": _strip_html(j.get("description")) or j.get("excerpt"),
                "posted_at": posted_at,
            })
        if page < PAGES:
            time.sleep(1)
    return postings
