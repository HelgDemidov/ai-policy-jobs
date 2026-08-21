#!/usr/bin/env python3
"""One-off retroactive cleanup: apply relevance_filter.evaluate() to every
row already in data/jobs.db and hard-delete the ones that fail it.

This is a deliberate, one-time exception to store.py's append-only contract
(docs/tech_specs/postings-schema-hardening/spec.md) — the normal live
pipeline (scripts/run.py) never deletes; this script does, directly against
SQLite, once, by curator decision
(docs/tech_specs/relevance-filtering/spec.md §4). Does not touch Postgres —
run scripts/postgres_sync.py (or scripts/run.py, which calls it as part of
its __main__) afterward to propagate the deletion: mirror_to_postgres() does
a full delete+insert every sync, so a smaller local table simply mirrors
down (its "don't wipe Postgres" guard only fires on a fully EMPTY local
table, which this isn't).

Usage: .venv/bin/python scripts/backfill_relevance_filter.py [--db-path PATH] [--filters-path PATH]
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import relevance_filter  # noqa: E402
import store  # noqa: E402


def backfill(db_path: Path | None = None, filters_path: Path | None = None) -> tuple[int, int]:
    """Returns (total_rows, deleted_rows). Prints a summary (counts per
    source, a few examples with the rejection reason) before deleting —
    this IS the live-calibration step the spec's testing section describes,
    not a dry-run mode."""
    filters_path = filters_path or relevance_filter.FILTERS_PATH
    filters = relevance_filter.load_filters(filters_path)

    conn = store.open_db(db_path)
    rows = conn.execute("SELECT id, org, title, source FROM postings").fetchall()

    to_delete: list[int] = []
    counts_by_source: Counter = Counter()
    examples: list[str] = []
    for row_id, org, title, source in rows:
        result = relevance_filter.evaluate(org, title, filters)
        if not result.passed:
            to_delete.append(row_id)
            counts_by_source[source] += 1
            if len(examples) < 15:
                examples.append(f"    [{source}] {org!r} / {title!r} — {result.reason}")

    print(f"{len(rows)} total posting(s), {len(to_delete)} filtered out.")
    if counts_by_source:
        print("By source:")
        for source, count in counts_by_source.most_common():
            print(f"  {source}: {count}")
        print("Examples:")
        for line in examples:
            print(line)

    if to_delete:
        placeholders = ",".join("?" * len(to_delete))
        conn.execute(f"DELETE FROM postings WHERE id IN ({placeholders})", to_delete)
        conn.commit()

    conn.close()
    return len(rows), len(to_delete)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--filters-path", type=Path, default=None)
    args = parser.parse_args()

    total, deleted = backfill(args.db_path, args.filters_path)
    print(f"\nDone. {total - deleted} posting(s) remain.")
