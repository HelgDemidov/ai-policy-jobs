"""Adzuna query-centric connector — REST API, requires a free self-serve
app_id/app_key pair (developer.adzuna.com). Only HTTPS works — the plain
http:// host 301-redirects, and requests won't follow that automatically
without allow_redirects (default True, but the scheme must be https from
the start to avoid an extra round trip — live lesson from testing).

Query lesson from live testing (see docs/job-aggregator-landscape.md):
what_phrase (exact phrase) works well for distinctive phrases like "think
tank", but does NOT fully fix noise for short/common phrases — that's a
config/query concern (searches.yaml), not something this connector can fix.
"""
import os
from pathlib import Path

import requests

API = "https://api.adzuna.com/v1/api/jobs/{country}/search/1"
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _load_env_credentials() -> tuple[str, str]:
    """Minimal KEY=VALUE .env reader — no python-dotenv dependency (pattern
    borrowed from G2AI's core/env.py). Real environment variables always win
    over the .env file, so CI/shell overrides still work."""
    values = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()

    app_id = os.environ.get("ADZUNA_APP_ID") or values.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY") or values.get("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        raise RuntimeError(
            "ADZUNA_APP_ID/ADZUNA_APP_KEY not set — register at developer.adzuna.com "
            "and put them in .env (see docs/tech_specs/query-connectors/spec.md)"
        )
    return app_id, app_key


def fetch(spec: dict) -> list[dict]:
    app_id, app_key = _load_env_credentials()
    country = spec["country"]
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": 50,
        "content-type": "application/json",
    }
    if "phrase" in spec:
        params["what_phrase"] = spec["phrase"]
    elif "query" in spec:
        params["what"] = spec["query"]

    resp = requests.get(API.format(country=country), params=params, timeout=20)
    resp.raise_for_status()

    postings = []
    for r in resp.json().get("results", []):
        postings.append({
            "ats_id": r["id"],
            "org": (r.get("company") or {}).get("display_name"),
            "title": r.get("title"),
            "location": (r.get("location") or {}).get("display_name"),
            "workplace_type": None,  # Adzuna doesn't expose this directly
            "team": None,
            "commitment": r.get("contract_time"),
            "url": r.get("redirect_url"),
            "description": r.get("description"),  # already plain text, no HTML
            "posted_at": (r.get("created") or "")[:10] or None,
        })
    return postings
