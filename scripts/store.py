"""SQLite storage for tracked job postings.

Two storage families share one `postings` table but reconcile differently:

- ATS family (`upsert_postings`): a connector's response is a full listing for
  one org+source, so a posting missing from it is a reliable "closed" signal
  — reconciled to 'likely_closed' immediately, but only while still 'new'.
- Search family (`upsert_search_postings`): a query-centric connector's
  response is a ranked/windowed search result, NOT a full listing — absence
  from one search proves nothing, so there is no per-call reconciliation.
  Staleness is instead handled by `expire_stale_search_postings` on a
  last-seen age threshold.

Both families share cross-source dedup via `dedup_key` (normalized org+title):
a posting already known — from ANY source — is touched (last_seen bumped),
not re-inserted.
"""
import re
import sqlite3
from datetime import datetime, timedelta, timezone
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


def _normalize_dedup_key(org: str, title: str) -> str:
    combined = f"{org} {title}".lower()
    combined = re.sub(r"[^\w\s]", "", combined)
    combined = re.sub(r"\s+", " ", combined).strip()
    return combined


def _ensure_dedup_key_column(conn: sqlite3.Connection) -> None:
    cols = [row[1] for row in conn.execute("PRAGMA table_info(postings)").fetchall()]
    if "dedup_key" not in cols:
        conn.execute("ALTER TABLE postings ADD COLUMN dedup_key TEXT")
        conn.commit()

    # Backfill rows inserted before this column existed so cross-source
    # dedup can actually match against them (idempotent: no-op once done).
    stale = conn.execute("SELECT id, org, title FROM postings WHERE dedup_key IS NULL").fetchall()
    for row_id, org, title in stale:
        conn.execute(
            "UPDATE postings SET dedup_key=? WHERE id=?",
            (_normalize_dedup_key(org, title), row_id),
        )
    if stale:
        conn.commit()


def open_db(path: Path | None = None) -> sqlite3.Connection:
    path = path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(SCHEMA)
    _ensure_dedup_key_column(conn)
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
                    team, commitment, url, description, posted_at, first_seen, last_seen, status, dedup_key)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'new', ?)""",
                (org, tier, source, p["ats_id"], p["title"], p.get("location"),
                 p.get("workplace_type"), p.get("team"), p.get("commitment"),
                 p["url"], p.get("description"), p.get("posted_at"), now, now,
                 _normalize_dedup_key(org, p["title"])),
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
        # An empty response is only a trustworthy "org closed everything"
        # signal if we've never had a reason to doubt it. Under a daily
        # unattended timer, a renamed ATS slug or a connector parsing a
        # changed response shape ALSO looks like "zero postings" — and would
        # otherwise silently mass-close every known posting for this org on
        # the first bad run. If we already know about postings here, treat
        # the empty response as suspicious and skip reconciliation instead of
        # trusting it; a genuinely empty org (no history at all) has nothing
        # to wrongly close, so that case is left as a no-op UPDATE below.
        known = conn.execute(
            "SELECT COUNT(*) FROM postings WHERE org=? AND source=?", (org, source)
        ).fetchone()[0]
        if known:
            print(
                f"  ! {org} ({source}): empty response but {known} known posting(s) on file — "
                "skipping reconciliation (looks like a broken fetch, not a real closure)"
            )
        else:
            conn.execute(
                "UPDATE postings SET status='likely_closed' WHERE org=? AND source=? AND status='new'",
                (org, source),
            )
    conn.commit()
    return new_count


def upsert_search_postings(conn: sqlite3.Connection, source: str, postings: list[dict]) -> int:
    """Insert/touch postings from a query-centric connector.

    Each posting dict carries its own `org` and (optionally) `tier` — unlike
    `upsert_postings`, where both are fixed per-call for a single known org.
    No reconciliation to 'likely_closed' here; see module docstring.
    """
    now = datetime.now(timezone.utc).isoformat()
    new_count = 0
    for p in postings:
        row = conn.execute(
            "SELECT id FROM postings WHERE source=? AND ats_id=?",
            (source, p["ats_id"]),
        ).fetchone()
        if row is not None:
            conn.execute(
                """UPDATE postings SET title=?, location=?, workplace_type=?,
                   team=?, commitment=?, description=?, last_seen=?
                   WHERE source=? AND ats_id=?""",
                (p["title"], p.get("location"), p.get("workplace_type"),
                 p.get("team"), p.get("commitment"), p.get("description"), now,
                 source, p["ats_id"]),
            )
            continue

        dedup_key = _normalize_dedup_key(p["org"], p["title"])
        dup = conn.execute("SELECT id FROM postings WHERE dedup_key=?", (dedup_key,)).fetchone()
        if dup is not None:
            conn.execute("UPDATE postings SET last_seen=? WHERE id=?", (now, dup[0]))
            continue

        conn.execute(
            """INSERT INTO postings
               (org, tier, source, ats_id, title, location, workplace_type,
                team, commitment, url, description, posted_at, first_seen, last_seen, status, dedup_key)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'new', ?)""",
            (p["org"], p.get("tier"), source, p["ats_id"], p["title"], p.get("location"),
             p.get("workplace_type"), p.get("team"), p.get("commitment"),
             p["url"], p.get("description"), p.get("posted_at"), now, now, dedup_key),
        )
        new_count += 1

    conn.commit()
    return new_count


def expire_stale_search_postings(conn: sqlite3.Connection, sources: list[str], max_age_days: int = 45) -> int:
    """Age-based staleness for the search family — see module docstring for
    why this replaces per-call reconciliation. Never touches non-'new' rows
    or sources outside the given list (e.g. ATS-family sources)."""
    if not sources:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
    placeholders = ",".join("?" * len(sources))
    cur = conn.execute(
        f"""UPDATE postings SET status='likely_closed'
            WHERE source IN ({placeholders}) AND status='new' AND last_seen < ?""",
        (*sources, cutoff),
    )
    conn.commit()
    return cur.rowcount
