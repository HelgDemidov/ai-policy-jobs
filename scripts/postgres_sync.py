"""Sync data/jobs.db to/from Neon Postgres — replaces blob_sync.py's role
now that the web GUI reads/writes Postgres directly instead of a SQLite
file in Vercel Blob (docs/tech_specs/web-postgres-migration/spec.md §7).

store.py's upsert/reconciliation logic is untouched and stays the single
source of truth for what's "new" vs "closed" — this module only mirrors
its *result* into Postgres, in the same pull-before/push-after shape
blob_sync.py used:

1. ensure_schema   — `alembic upgrade head`, idempotent every run.
2. pull_statuses   — before connectors run, so a status set via the web
                      GUI isn't lost when store.py re-upserts.
3. (connectors run, via store.py — unchanged)
4. sync_organizations — curated (orgs.yaml) + discovered (postings.org)
5. sync_searches      — full mirror from searches.yaml
6. mirror_to_postgres — full mirror of postings, one transaction

organizations/searches use plain SELECT-then-INSERT-or-UPDATE rather than
a dialect-specific ON CONFLICT construct: at this data volume (single-digit
to low-hundreds of rows) the extra round trips are free, and it keeps this
module's tests hermetic against SQLite standing in for Postgres (SQLite's
and Postgres's native ON CONFLICT syntax differ at the SQLAlchemy
construct level; plain select/insert/update doesn't).
"""
import sys
from pathlib import Path

import yaml
from alembic.config import Config
from sqlalchemy import create_engine, func, select

from alembic import command

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_API_DIR = REPO_ROOT / "web" / "api"
if str(WEB_API_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_API_DIR))

import _schema  # noqa: E402

_POSTINGS_COLUMNS = [
    "org", "tier", "source", "ats_id", "title", "location", "workplace_type",
    "team", "commitment", "url", "description", "posted_at", "first_seen",
    "last_seen", "status", "dedup_key",
]


def get_engine(database_url: str):
    """Unlike _repo.py's get_engine(), takes the URL explicitly and isn't a
    module-scope singleton — run.py is a one-shot script invocation, not a
    long-lived server process, so there's no repeated-call/cold-start
    caching benefit to a global here."""
    return create_engine(_schema.resolve_database_url(database_url), pool_pre_ping=True)


def ensure_schema(database_url: str) -> None:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", _schema.resolve_database_url(database_url).replace("%", "%%"))
    command.upgrade(cfg, "head")


def pull_statuses(pg_engine, sqlite_conn) -> None:
    """Pulls status values from Postgres into local SQLite by
    (source, ats_id) — preserves web-GUI status edits that would otherwise
    be silently overwritten by the next store.py upsert cycle. Raises on
    connection failure (no try/except here) so run.py exits non-zero
    rather than silently proceeding on stale statuses and mirroring them
    back over Postgres's real ones."""
    postings = _schema.postings
    with pg_engine.connect() as conn:
        rows = conn.execute(
            select(postings.c.source, postings.c.ats_id, postings.c.status)
        ).all()
    sqlite_conn.executemany(
        "UPDATE postings SET status = ? WHERE source = ? AND ats_id = ?",
        [(row.status, row.source, row.ats_id) for row in rows],
    )
    sqlite_conn.commit()


def sync_organizations(pg_engine, orgs_yaml_path: Path, sqlite_conn) -> None:
    """Curated entries from orgs.yaml (origin='curated') always win; a stub
    row (origin='discovered', tier/ats/slug NULL) is added for any org name
    seen in local postings that isn't already present — never overwrites an
    existing row, curated or discovered (spec §3: most orgs are
    query-family discoveries, not curated)."""
    orgs = yaml.safe_load(orgs_yaml_path.read_text()) or []
    organizations = _schema.organizations

    with pg_engine.begin() as conn:
        for entry in orgs:
            existing = conn.execute(
                select(organizations.c.id).where(organizations.c.name == entry["org"])
            ).scalar_one_or_none()
            values = {
                "tier": entry.get("tier"),
                "ats": entry.get("ats"),
                "slug": entry.get("slug"),
                "origin": "curated",
            }
            if existing is None:
                conn.execute(organizations.insert().values(name=entry["org"], **values))
            else:
                conn.execute(organizations.update().where(organizations.c.id == existing).values(**values))

        discovered = [row[0] for row in sqlite_conn.execute("SELECT DISTINCT org FROM postings").fetchall()]
        for name in discovered:
            existing = conn.execute(
                select(organizations.c.id).where(organizations.c.name == name)
            ).scalar_one_or_none()
            if existing is None:
                conn.execute(organizations.insert().values(name=name, origin="discovered"))


def sync_searches(pg_engine, searches_yaml_path: Path) -> None:
    """Full mirror from searches.yaml — unlike organizations, searches has
    only one data source, so replacing everything on each run is both
    simpler and correct (it also removes rows for specs deleted from the
    YAML, which upsert-only would leave stale)."""
    specs = yaml.safe_load(searches_yaml_path.read_text()) if searches_yaml_path.exists() else None
    specs = specs or []
    searches = _schema.searches

    with pg_engine.begin() as conn:
        conn.execute(searches.delete())
        for spec in specs:
            conn.execute(
                searches.insert().values(
                    search_id=spec["id"],
                    source=spec["source"],
                    query_text=spec.get("query") or spec.get("phrase"),
                    location=spec.get("location") or spec.get("country") or spec.get("country_indeed"),
                    manual=bool(spec.get("manual", False)),
                    raw=spec,
                )
            )


def mirror_to_postgres(pg_engine, sqlite_conn) -> None:
    """Full mirror of postings, one transaction (delete + insert both
    inside the same `with pg_engine.begin()` block): a network blip
    mid-sync rolls back to the previous good state instead of leaving prod
    with an empty or half-populated table — the one thing the old Blob
    approach got for free (a single atomic file PUT) that a multi-statement
    SQL sync has to earn explicitly.

    Also refuses to wipe Postgres if local SQLite has zero postings but
    Postgres currently has some — store.py's postings table is append-only
    (rows are marked likely_closed, never deleted), so a legitimately empty
    local table only happens before the very first successful connector
    run, never after. Same "don't let successful-but-empty look like
    everything's closed" guard store.py already applies to per-connector
    reconciliation, extended to this sync step.
    """
    cursor = sqlite_conn.execute(f"SELECT {', '.join(_POSTINGS_COLUMNS)} FROM postings")
    rows = cursor.fetchall()

    postings = _schema.postings
    organizations = _schema.organizations

    with pg_engine.begin() as conn:
        if not rows:
            existing_count = conn.execute(select(func.count()).select_from(postings)).scalar_one()
            if existing_count:
                raise RuntimeError(
                    f"mirror_to_postgres: local postings is empty but Postgres has "
                    f"{existing_count} row(s) — refusing to wipe, this looks like a bug"
                )

        # .all() first, not dict(conn.execute(...)) directly: CursorResult
        # has its own .keys() (the column names), so dict() would treat the
        # result as already mapping-like and try result["name"] instead of
        # consuming it as an iterable of (name, id) row-tuples.
        org_ids = dict(conn.execute(select(organizations.c.name, organizations.c.id)).all())
        conn.execute(postings.delete())
        if rows:
            conn.execute(
                postings.insert(),
                [dict(zip(_POSTINGS_COLUMNS, row), org_id=org_ids.get(row[0])) for row in rows],
            )
