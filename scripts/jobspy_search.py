"""JobSpy wrapper — query-centric connectors across LinkedIn and Indeed via
the python-jobspy scraping library (github.com/speedyapply/JobSpy).

Two separate fetch functions, not one parameterized by site, so each gets
its own `source` value in the DB — LinkedIn and Indeed have very different
reliability/relevance profiles in live testing (see
docs/job-aggregator-landscape.md): LinkedIn found the single best match of
any source tested (RAND Europe).

LinkedIn was gated behind run.py's `--linkedin` flag until 2026-07-25 over
ToS/rate-limit concerns, then un-gated: the call is unauthenticated (no
account of ours is involved — a rate limit costs us an empty result set for
that run, not a ban) and `linkedin_fetch_description` defaults to False, so
one run is ~2-3 requests. The real cost knob is `fetch_description: true` in
searches.yaml — it issues one request PER POSTING (~20x a run). Leave it off.

Query lesson from live testing: Indeed does broad OR-of-words matching on
an unquoted search_term — use quoted phrases in searches.yaml
(e.g. '"AI policy" OR "AI governance"'), or single words like "analyst"
alone will match almost anything.
"""
import pandas as pd
from jobspy import scrape_jobs

RESULTS_WANTED = 20


def _clean(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _row_to_posting(row: pd.Series) -> dict | None:
    ats_id = _clean(row.get("id")) or _clean(row.get("job_url"))
    if ats_id is None:
        return None  # str(None) == "None" (truthy) — must check before str()
    org = _clean(row.get("company"))
    title = _clean(row.get("title"))
    url = _clean(row.get("job_url"))
    if not org or not title or not url:
        return None  # неполные записи — нетриажируемы, не сохраняем
    date_posted = _clean(row.get("date_posted"))
    posted_at = date_posted.isoformat() if hasattr(date_posted, "isoformat") else None
    is_remote = _clean(row.get("is_remote"))
    return {
        "ats_id": str(ats_id),
        "org": org,
        "title": title,
        "location": _clean(row.get("location")),
        "workplace_type": "remote" if is_remote is True else None,
        "team": None,
        "commitment": _clean(row.get("job_type")),
        "url": url,
        "description": _clean(row.get("description")),
        "posted_at": posted_at,
    }


def fetch_linkedin(spec: dict) -> list[dict]:
    df = scrape_jobs(
        site_name=["linkedin"],
        search_term=spec["query"],
        location=spec.get("location"),
        results_wanted=RESULTS_WANTED,
        linkedin_fetch_description=spec.get("fetch_description", False),
    )
    if df.empty:
        return []
    return [p for p in (_row_to_posting(row) for _, row in df.iterrows()) if p is not None]


def fetch_indeed(spec: dict) -> list[dict]:
    df = scrape_jobs(
        site_name=["indeed"],
        search_term=spec["query"],
        location=spec.get("location"),
        results_wanted=RESULTS_WANTED,
        country_indeed=spec.get("country_indeed", "USA"),
    )
    if df.empty:
        return []
    return [p for p in (_row_to_posting(row) for _, row in df.iterrows()) if p is not None]
