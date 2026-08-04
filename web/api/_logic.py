"""Pure DB logic for web/api/*.py handlers — no HTTP, no blob I/O, so tests
can exercise it directly against a tmp_path SQLite file.

Mirrors app/app.py's filtering (app.py:383-391) and status-write
(app.py:306-313) logic 1:1 for GUI parity. Deliberately does NOT import
scripts/store.py: this deploys under web/'s Vercel Root Directory, and a
Vercel Function cannot reach files outside its Root Directory — no `..`
(confirmed live against docs.vercel.com/docs/builds/configure-a-build,
2026-08-04). STATUS_VALUES is kept in sync by hand with scripts/store.py's
constant of the same name (itself already hand-synced with app.py's
STATUS_OPTIONS) — one more copy of a 5-item tuple, not new logic.
"""
import sqlite3

STATUS_VALUES = ("new", "reviewed", "applied", "rejected", "likely_closed")


def list_postings(conn: sqlite3.Connection, filters: dict) -> list[dict]:
    """filters keys (all optional):
    - tier, org: list[str] | None. None means no filter on that axis; []
      means filter to nothing — matching an absent vs. an empty HTTP query
      param, not a truthy/falsy check (an empty multiselect is a real
      "show nothing" state in app.py's equivalent `.isin([])`).
    - hide_closed, remote_only: bool, default-false like app.py's checkboxes.
    - query: str, matched against title OR description, case-insensitive.
    """
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM postings ORDER BY COALESCE(posted_at, first_seen) DESC"
    ).fetchall()
    postings = [dict(row) for row in rows]

    tiers = filters.get("tier")
    if tiers is not None:
        postings = [p for p in postings if p["tier"] in tiers]

    orgs = filters.get("org")
    if orgs is not None:
        postings = [p for p in postings if p["org"] in orgs]

    if filters.get("hide_closed"):
        postings = [p for p in postings if p["status"] not in ("likely_closed", "rejected")]

    if filters.get("remote_only"):
        postings = [p for p in postings if (p["workplace_type"] or "").lower() == "remote"]

    query = (filters.get("query") or "").strip().lower()
    if query:
        postings = [
            p for p in postings
            if query in (p["title"] or "").lower() or query in (p["description"] or "").lower()
        ]

    return postings


def set_status(conn: sqlite3.Connection, source: str, ats_id: str, new_status: str) -> None:
    if new_status not in STATUS_VALUES:
        raise ValueError(f"invalid status: {new_status!r}")
    conn.execute(
        "UPDATE postings SET status=? WHERE source=? AND ats_id=?",
        (new_status, source, ats_id),
    )
    conn.commit()
