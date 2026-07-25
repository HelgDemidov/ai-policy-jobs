#!/usr/bin/env python3
"""Fetch current postings from all configured ATS connectors and upsert into
the local SQLite store. One org's failure doesn't stop the rest of the batch.

Usage: python3 scripts/run.py
"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import greenhouse  # noqa: E402
import lever  # noqa: E402
import personio  # noqa: E402
import store  # noqa: E402

CONNECTORS = {"lever": lever.fetch, "greenhouse": greenhouse.fetch, "personio": personio.fetch}


def main(orgs_path: Path | None = None, db_path: Path | None = None) -> None:
    orgs_path = orgs_path or Path(__file__).resolve().parent.parent / "orgs.yaml"
    orgs = yaml.safe_load(orgs_path.read_text())

    conn = store.open_db(db_path)
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
    conn.close()
    print(f"\nDone. {total_new} new posting(s) this run.")


if __name__ == "__main__":
    main()
