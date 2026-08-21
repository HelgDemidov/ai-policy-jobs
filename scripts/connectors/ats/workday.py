"""Workday ATS connector — public CXS (candidate experience site) JSON
API, no auth required. `slug` encodes both identifiers Workday needs —
`{tenant}:{site}` (e.g. "weforum:Forum_Careers") — kept as one compound
string rather than a second orgs.yaml field since both halves are fixed
per org and never vary independently in practice, unlike html_scrape's
url+list_selector (which really are two independent knobs).

Unlike Lever, the list endpoint doesn't carry full descriptions or a
canonical URL — each posting needs one extra request to the detail
endpoint (same shape as Greenhouse's ?content=true pattern).
"""
import re

import requests

LIST_API = "https://{tenant}.wd3.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
DETAIL_API = "https://{tenant}.wd3.myworkdayjobs.com/wday/cxs/{tenant}/{site}{external_path}"
PAGE_SIZE = 20


def _strip_html(html: str) -> str:
    text = re.sub(r"<li>", "\n- ", html or "")
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def fetch(slug: str) -> list[dict]:
    tenant, _, site = slug.partition(":")
    postings = []
    offset = 0
    while True:
        resp = requests.post(
            LIST_API.format(tenant=tenant, site=site),
            json={"appliedFacets": {}, "limit": PAGE_SIZE, "offset": offset, "searchText": ""},
            headers={"Content-Type": "application/json"},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        job_postings = data.get("jobPostings", [])
        for job in job_postings:
            external_path = job.get("externalPath", "")
            detail = requests.get(
                DETAIL_API.format(tenant=tenant, site=site, external_path=external_path), timeout=20
            )
            detail.raise_for_status()
            info = detail.json().get("jobPostingInfo", {})
            postings.append({
                "ats_id": info.get("jobReqId") or external_path,
                "title": info.get("title") or job.get("title"),
                "location": info.get("location") or job.get("locationsText"),
                "workplace_type": None,
                "team": None,
                "commitment": info.get("timeType"),
                "url": info.get("externalUrl"),
                "description": _strip_html(info.get("jobDescription", "")),
                "posted_at": info.get("startDate"),
            })
        offset += PAGE_SIZE
        if offset >= data.get("total", 0):
            break
    return postings
