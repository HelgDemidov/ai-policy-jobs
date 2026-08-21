"""Oracle Fusion Cloud HCM (Candidate Experience) ATS connector — public
REST API, no auth required. `slug` encodes the two identifiers this
pattern needs — `{host}:{site_number}` (e.g.
"estm.fa.em2.oraclecloud.com:CX_1") — both fixed per org, same
compound-string rationale as workday.py.

`expand=requisitionList` is required — without it the endpoint returns
only search facets/metadata, not the postings themselves (a live gotcha,
not documented anywhere obvious).

Live-verified 2026-08-21 against UNDP (donabor wave 2) — likely reusable
for other UN bodies mid-migration to this platform (see
docs/think-tank-io-source-sweep/notes.md).
"""
import requests

LIST_API = "https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
JOB_URL = "https://{host}/hcmUI/CandidateExperience/en/sites/{site_number}/job/{job_id}"
PAGE_SIZE = 25


def fetch(slug: str) -> list[dict]:
    host, _, site_number = slug.partition(":")
    postings = []
    offset = 0
    while True:
        resp = requests.get(
            LIST_API.format(host=host),
            params={
                "onlyData": "true",
                "expand": "requisitionList",
                "finder": f"findReqs;siteNumber={site_number},limit={PAGE_SIZE},offset={offset}",
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        requisitions = items[0].get("requisitionList", []) if items else []
        total = items[0].get("TotalJobsCount", 0) if items else 0
        for job in requisitions:
            job_id = job.get("Id")
            postings.append({
                "ats_id": job_id,
                "title": job.get("Title"),
                "location": job.get("PrimaryLocation"),
                "workplace_type": (job.get("WorkplaceType") or None),
                "team": job.get("Organization") or job.get("Department") or job.get("BusinessUnit"),
                "commitment": job.get("WorkerType"),
                "url": JOB_URL.format(host=host, site_number=site_number, job_id=job_id),
                "description": job.get("ShortDescriptionStr") or "",
                "posted_at": job.get("PostedDate"),
            })
        offset += PAGE_SIZE
        if offset >= total or not requisitions:
            break
    return postings
