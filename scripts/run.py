#!/usr/bin/env python3
"""Fetch current postings from all configured ATS + query-centric connectors
and upsert into the local SQLite store. One entry's failure doesn't stop the
rest of its batch (either family).

Between fetch() and the upsert, each posting is checked against
relevance_filter.evaluate() (config/filters.yaml) — anything that fails
never reaches store.py, so store.py's append-only contract is untouched
(docs/tech_specs/relevance-filtering/spec.md).

Usage: python3 scripts/run.py [--linkedin]
--linkedin also runs `manual: true` search specs. As of 2026-07-25 no spec is
marked manual (LinkedIn was un-gated — see docs/backlog/BACKLOG.md), so the flag is a
no-op; the mechanism is kept for gating a future source.
"""
import argparse
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import postgres_sync  # noqa: E402
import relevance_filter  # noqa: E402
import store  # noqa: E402
from connectors.ats import (  # noqa: E402
    applicantpro,
    bamboohr,
    greenhouse,
    html_scrape,
    icims,
    jazzhr,
    lever,
    oracle_fusion_hcm,
    personio,
    pinpoint,
    recruiterbox,
    smartrecruiters,
    teamtailor,
    workable,
    workday,
    wp_json,
)
from connectors.query import adzuna, jobspy_search, recruitee, un_secretariat  # noqa: E402
from connectors.query import common as query_common  # noqa: E402

CONNECTORS = {
    "lever": lever.fetch,
    "greenhouse": greenhouse.fetch,
    "personio": personio.fetch,
    "smartrecruiters": smartrecruiters.fetch,
    "teamtailor": teamtailor.fetch,
    "workable": workable.fetch,
    "pinpoint": pinpoint.fetch,
    "icims": icims.fetch,
    "jazzhr": jazzhr.fetch,
    "bamboohr": bamboohr.fetch,
    "recruiterbox": recruiterbox.fetch,
    "workday": workday.fetch,
    "oracle_fusion_hcm": oracle_fusion_hcm.fetch,
    "applicantpro": applicantpro.fetch,
}
# html_scrape/wp_json aren't here — different fetch() signature (url(+extra
# params), not a single slug) — explicit dispatch in _run_org_connectors.

SEARCH_CONNECTORS = {
    "adzuna": adzuna.fetch,
    "jobspy_linkedin": jobspy_search.fetch_linkedin,
    "un_secretariat": un_secretariat.fetch,
    "recruitee": recruitee.fetch,
}


def _filter_out(postings: list[dict], org_getter, filters: dict) -> tuple[list[dict], int]:
    """org_getter(posting) -> org — a fixed org for the whole ATS-family
    batch, or per-posting for the search family (each carries its own)."""
    passing = [p for p in postings if relevance_filter.evaluate(org_getter(p), p["title"], filters).passed]
    return passing, len(postings) - len(passing)


def _run_org_connectors(conn, orgs_path: Path, filters: dict) -> tuple[int, int, int]:
    """Returns (new_count, succeeded, attempted)."""
    orgs = yaml.safe_load(orgs_path.read_text()) or []
    total_new = 0
    succeeded = 0
    for entry in orgs:
        try:
            if entry["ats"] == "html_scrape":
                # Different fetch() signature (url + optional list_selector/
                # needs_browser/use_browser_ua, not a slug against a known
                # platform) — an honest explicit branch beats forcing a fake
                # uniform interface (point-source-connectors spec §2).
                postings = html_scrape.fetch(
                    entry["url"],
                    list_selector=entry.get("list_selector"),
                    needs_browser=entry.get("needs_browser", False),
                    use_browser_ua=entry.get("use_browser_ua", False),
                )
            elif entry["ats"] == "wp_json":
                postings = wp_json.fetch(entry["url"], entry["post_type"])
            else:
                postings = CONNECTORS[entry["ats"]](entry["slug"])
        except Exception as exc:  # noqa: BLE001 — isolate this org's failure, keep the batch going
            source_ref = entry.get("url") or entry.get("slug")
            print(f"  ! {entry['org']} ({entry['ats']}:{source_ref}) — failed: {exc}")
            continue
        if entry.get("tier") is None:
            # No single fixed tier fits this org (global board — see the
            # orgs.yaml comment on its entry) — derive one per posting from
            # its own location/workplace_type instead, same heuristic the
            # query-centric family uses.
            for p in postings:
                p["tier"] = query_common.derive_tier(entry["ats"], entry, p)
        passing, filtered = _filter_out(postings, lambda _p: entry["org"], filters)
        new_count = store.upsert_postings(conn, entry["org"], entry.get("tier"), entry["ats"], passing)
        total_new += new_count
        succeeded += 1
        suffix = f", {filtered} filtered" if filtered else ""
        print(f"  {entry['org']}: {len(postings)} open, {new_count} new{suffix}")
    return total_new, succeeded, len(orgs)


def _run_search_connectors(
    conn, searches_path: Path, run_linkedin: bool, filters: dict
) -> tuple[int, int, int]:
    """Returns (new_count, succeeded, attempted). Specs skipped via the
    manual-gate aren't "attempted" — they were deliberately not run, not a
    failure, and shouldn't count against the all-sources-failed check."""
    specs = yaml.safe_load(searches_path.read_text()) if searches_path.exists() else None
    specs = specs or []
    total_new = 0
    succeeded = 0
    attempted = 0
    for spec in specs:
        if spec.get("manual") and not run_linkedin:
            print(f"  - {spec['id']}: skipped (manual)")
            continue
        attempted += 1
        fetch = SEARCH_CONNECTORS[spec["source"]]
        try:
            postings = fetch(spec)
        except Exception as exc:  # noqa: BLE001 — isolate this search's failure, keep the batch going
            print(f"  ! {spec['id']} ({spec['source']}) — failed: {exc}")
            continue
        for p in postings:
            p["tier"] = query_common.derive_tier(spec["source"], spec, p)
        passing, filtered = _filter_out(postings, lambda p: p["org"], filters)
        new_count = store.upsert_search_postings(conn, spec["source"], passing)
        total_new += new_count
        succeeded += 1
        suffix = f", {filtered} filtered" if filtered else ""
        print(f"  {spec['id']}: {len(postings)} found, {new_count} new{suffix}")
    return total_new, succeeded, attempted


def main(
    orgs_path: Path | None = None,
    db_path: Path | None = None,
    searches_path: Path | None = None,
    filters_path: Path | None = None,
    run_linkedin: bool = False,
) -> int:
    """Returns a process exit code: 1 if every attempted source failed (an
    unattended daily timer can't otherwise tell "everything is broken" apart
    from "nothing new today"), 0 otherwise, including on partial failure or
    an empty config."""
    orgs_path = orgs_path or Path(__file__).resolve().parent.parent / "config" / "orgs.yaml"
    searches_path = searches_path or Path(__file__).resolve().parent.parent / "config" / "searches.yaml"
    filters_path = filters_path or relevance_filter.FILTERS_PATH
    filters = relevance_filter.load_filters(filters_path)

    conn = store.open_db(db_path)

    org_new, org_ok, org_attempted = _run_org_connectors(conn, orgs_path, filters)

    print()
    search_new, search_ok, search_attempted = _run_search_connectors(conn, searches_path, run_linkedin, filters)

    expired = store.expire_stale_search_postings(conn, list(SEARCH_CONNECTORS.keys()))
    if expired:
        print(f"\n{expired} stale search posting(s) expired to likely_closed.")

    conn.close()

    total_new = org_new + search_new
    total_attempted = org_attempted + search_attempted
    total_ok = org_ok + search_ok
    print(f"\nDone. {total_new} new posting(s) this run.")

    if total_attempted and not total_ok:
        print(f"! All {total_attempted} source(s) failed this run.", file=sys.stderr)
        return 1
    return 0


ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _load_database_url() -> str:
    """Same minimal KEY=VALUE .env reader pattern as blob_sync.py's
    _load_token / connectors/query/adzuna.py's _load_env_credentials — real
    environment variables win over the .env file."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key.strip() == "DATABASE_URL":
                return value.strip()
    raise RuntimeError(
        "DATABASE_URL not set — see docs/tech_specs/web-postgres-migration/spec.md §2"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--linkedin", action="store_true",
        help="also run manual:true search specs (no spec is marked manual right now — kept for future gating)",
    )
    args = parser.parse_args()

    database_url = _load_database_url()
    pg_engine = postgres_sync.get_engine(database_url)
    config_dir = Path(__file__).resolve().parent.parent / "config"

    postgres_sync.ensure_schema(database_url)

    conn = store.open_db()
    postgres_sync.pull_statuses(pg_engine, conn)  # preserve status writes from the web GUI
    conn.close()

    exit_code = main(run_linkedin=args.linkedin)

    conn = store.open_db()
    postgres_sync.sync_organizations(pg_engine, config_dir / "orgs.yaml", conn)
    postgres_sync.sync_searches(pg_engine, config_dir / "searches.yaml")
    postgres_sync.mirror_to_postgres(pg_engine, conn)  # publish this run's result
    conn.close()

    sys.exit(exit_code)
