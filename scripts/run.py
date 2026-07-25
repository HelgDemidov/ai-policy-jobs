#!/usr/bin/env python3
"""Fetch current postings from all configured ATS + query-centric connectors
and upsert into the local SQLite store. One entry's failure doesn't stop the
rest of its batch (either family).

Usage: python3 scripts/run.py [--linkedin]
--linkedin also runs `manual: true` search specs (currently just LinkedIn —
rate-limit/ToS-risky, so it's opt-in rather than part of the default run).
"""
import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adzuna  # noqa: E402
import greenhouse  # noqa: E402
import himalayas  # noqa: E402
import jobspy_search  # noqa: E402
import lever  # noqa: E402
import personio  # noqa: E402
import query_common  # noqa: E402
import store  # noqa: E402

CONNECTORS = {"lever": lever.fetch, "greenhouse": greenhouse.fetch, "personio": personio.fetch}

SEARCH_CONNECTORS = {
    "himalayas": himalayas.fetch,
    "adzuna": adzuna.fetch,
    "jobspy_linkedin": jobspy_search.fetch_linkedin,
    "jobspy_indeed": jobspy_search.fetch_indeed,
}


def _run_org_connectors(conn, orgs_path: Path) -> int:
    orgs = yaml.safe_load(orgs_path.read_text()) or []
    total_new = 0
    for entry in orgs:
        fetch = CONNECTORS[entry["ats"]]
        try:
            postings = fetch(entry["slug"])
        except Exception as exc:  # noqa: BLE001 — isolate this org's failure, keep the batch going
            print(f"  ! {entry['org']} ({entry['ats']}:{entry['slug']}) — failed: {exc}")
            continue
        new_count = store.upsert_postings(conn, entry["org"], entry.get("tier"), entry["ats"], postings)
        total_new += new_count
        print(f"  {entry['org']}: {len(postings)} open, {new_count} new")
    return total_new


def _run_search_connectors(conn, searches_path: Path, run_linkedin: bool) -> int:
    specs = yaml.safe_load(searches_path.read_text()) if searches_path.exists() else None
    specs = specs or []
    total_new = 0
    for spec in specs:
        if spec.get("manual") and not run_linkedin:
            print(f"  - {spec['id']}: skipped (manual)")
            continue
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
        print(f"  {spec['id']}: {len(postings)} found, {new_count} new")
    return total_new


def main(
    orgs_path: Path | None = None,
    db_path: Path | None = None,
    searches_path: Path | None = None,
    run_linkedin: bool = False,
) -> None:
    orgs_path = orgs_path or Path(__file__).resolve().parent.parent / "orgs.yaml"
    searches_path = searches_path or Path(__file__).resolve().parent.parent / "searches.yaml"

    conn = store.open_db(db_path)

    total_new = _run_org_connectors(conn, orgs_path)

    print()
    total_new += _run_search_connectors(conn, searches_path, run_linkedin)

    expired = store.expire_stale_search_postings(conn, list(SEARCH_CONNECTORS.keys()))
    if expired:
        print(f"\n{expired} stale search posting(s) expired to likely_closed.")

    conn.close()
    print(f"\nDone. {total_new} new posting(s) this run.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--linkedin", action="store_true",
        help="also run manual:true search specs (currently just LinkedIn — rate-limit/ToS-risky, opt-in)",
    )
    args = parser.parse_args()
    main(run_linkedin=args.linkedin)
