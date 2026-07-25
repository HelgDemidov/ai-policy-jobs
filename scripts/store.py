"""SQLite storage for tracked job postings.

Philosophy borrowed from the G2AI pipeline's reconciliation pattern: state is
derived from what a connector actually returns on each run, not accumulated
assumptions. A posting no longer returned by its org+source is inferred
"likely_closed" — but only while it's still in the default 'new' status, so a
posting you've already marked 'applied' or 'rejected' is never silently
overwritten by a re-run.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS postings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org TEXT NOT NULL,
    tier TEXT,
    source TEXT NOT NULL,
    ats_id TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT,
    workplace_type TEXT,
    team TEXT,
    commitment TEXT,
    url TEXT NOT NULL,
    description TEXT,
    posted_at TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    UNIQUE(source, ats_id)
);
"""


def open_db(path: Path | None = None) -> sqlite3.Connection:
    path = path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(SCHEMA)
    return conn


def upsert_postings(conn: sqlite3.Connection, org: str, tier: str | None, source: str, postings: list[dict]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    new_count = 0
    seen_ids = []
    for p in postings:
        seen_ids.append(p["ats_id"])
        row = conn.execute(
            "SELECT id FROM postings WHERE source=? AND ats_id=?",
            (source, p["ats_id"]),
        ).fetchone()
        if row is None:
            conn.execute(
                """INSERT INTO postings
                   (org, tier, source, ats_id, title, location, workplace_type,
                    team, commitment, url, description, posted_at, first_seen, last_seen, status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'new')""",
                (org, tier, source, p["ats_id"], p["title"], p.get("location"),
                 p.get("workplace_type"), p.get("team"), p.get("commitment"),
                 p["url"], p.get("description"), p.get("posted_at"), now, now),
            )
            new_count += 1
        else:
            conn.execute(
                """UPDATE postings SET title=?, location=?, workplace_type=?,
                   team=?, commitment=?, description=?, last_seen=?
                   WHERE source=? AND ats_id=?""",
                (p["title"], p.get("location"), p.get("workplace_type"),
                 p.get("team"), p.get("commitment"), p.get("description"), now,
                 source, p["ats_id"]),
            )

    if seen_ids:
        placeholders = ",".join("?" * len(seen_ids))
        conn.execute(
            f"""UPDATE postings SET status='likely_closed'
                WHERE org=? AND source=? AND status='new' AND ats_id NOT IN ({placeholders})""",
            (org, source, *seen_ids),
        )
    else:
        conn.execute(
            "UPDATE postings SET status='likely_closed' WHERE org=? AND source=? AND status='new'",
            (org, source),
        )
    conn.commit()
    return new_count
