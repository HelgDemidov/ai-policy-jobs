#!/usr/bin/env python3
"""Fetch current postings from all configured ATS + query-centric connectors
and upsert into the local SQLite store. One entry's failure doesn't stop the
rest of its batch (either family).

Usage: python3 scripts/run.py [--linkedin]
--linkedin also runs `manual: true` search specs. As of 2026-07-25 no spec is
marked manual (LinkedIn was un-gated — see docs/backlog/BACKLOG.md), so the flag is a
no-op; the mechanism is kept for gating a future source.
"""
import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import store  # noqa: E402
from connectors.ats import greenhouse, lever, personio  # noqa: E402
from connectors.query import adzuna, himalayas, jobspy_search  # noqa: E402
from connectors.query import common as query_common  # noqa: E402

CONNECTORS = {"lever": lever.fetch, "greenhouse": greenhouse.fetch, "personio": personio.fetch}

SEARCH_CONNECTORS = {
    "himalayas": himalayas.fetch,
    "adzuna": adzuna.fetch,
    "jobspy_linkedin": jobspy_search.fetch_linkedin,
    "jobspy_indeed": jobspy_search.fetch_indeed,
}


def _run_org_connectors(conn, orgs_path: Path) -> tuple[int, int, int]:
    """Returns (new_count, succeeded, attempted)."""
    orgs = yaml.safe_load(orgs_path.read_text()) or []
    total_new = 0
    succeeded = 0
    for entry in orgs:
        fetch = CONNECTORS[entry["ats"]]
        try:
            postings = fetch(entry["slug"])
        except Exception as exc:  # noqa: BLE001 — isolate this org's failure, keep the batch going
            print(f"  ! {entry['org']} ({entry['ats']}:{entry['slug']}) — failed: {exc}")
            continue
        new_count = store.upsert_postings(conn, entry["org"], entry.get("tier"), entry["ats"], postings)
        total_new += new_count
        succeeded += 1
        print(f"  {entry['org']}: {len(postings)} open, {new_count} new")
    return total_new, succeeded, len(orgs)


def _run_search_connectors(conn, searches_path: Path, run_linkedin: bool) -> tuple[int, int, int]:
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
        new_count = store.upsert_search_postings(conn, spec["source"], postings)
        total_new += new_count
        succeeded += 1
        print(f"  {spec['id']}: {len(postings)} found, {new_count} new")
    return total_new, succeeded, attempted


def main(
    orgs_path: Path | None = None,
    db_path: Path | None = None,
    searches_path: Path | None = None,
    run_linkedin: bool = False,
) -> int:
    """Returns a process exit code: 1 if every attempted source failed (an
    unattended daily timer can't otherwise tell "everything is broken" apart
    from "nothing new today" — see docs/tech_specs/triage-and-autonomy/spec.md
    §3), 0 otherwise, including on partial failure or an empty config."""
    orgs_path = orgs_path or Path(__file__).resolve().parent.parent / "config" / "orgs.yaml"
    searches_path = searches_path or Path(__file__).resolve().parent.parent / "config" / "searches.yaml"

    conn = store.open_db(db_path)

    org_new, org_ok, org_attempted = _run_org_connectors(conn, orgs_path)

    print()
    search_new, search_ok, search_attempted = _run_search_connectors(conn, searches_path, run_linkedin)

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--linkedin", action="store_true",
        help="also run manual:true search specs (no spec is marked manual right now — kept for future gating)",
    )
    args = parser.parse_args()
    sys.exit(main(run_linkedin=args.linkedin))
