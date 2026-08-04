"""Single source of truth for postings filtering, pagination, and status
writes — used by web/api/postings.py and status.py (deployed, queries
Neon) and tests/web/test_repo.py (SQLite in-memory). Mirrors
scripts/store.py's STATUS_VALUES and app/app.py's filter semantics 1:1 for
GUI parity, same as the _logic.py this replaces
(docs/tech_specs/web-postgres-migration/spec.md §3/§6).
"""
import os

from sqlalchemy import column, create_engine, func, or_, select

import _schema

STATUS_VALUES = ("new", "reviewed", "applied", "rejected", "likely_closed")

_ENGINE = None


def get_engine():
    """Module-scope singleton — created once per warm function instance, not
    per request (the "cache expensive setup at module scope" lesson from
    scopus_search_code, spec §3). Even on a cold instance where this runs on
    every invocation, Neon's pooled endpoint (-pooler hostname) absorbs the
    connection churn safely — that's the actual load-bearing safety net,
    not warm reuse."""
    global _ENGINE
    if _ENGINE is None:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL not set in the function's environment")
        _ENGINE = create_engine(_schema.resolve_database_url(url), pool_pre_ping=True)
    return _ENGINE


def _build_where(filters, dialect_name):
    """filters keys (all optional):
    - tier, org: list[str] | None. None means no filter on that axis; []
      means filter to nothing — matching an absent vs. an empty HTTP query
      param (see web/api/postings.py), not a truthy/falsy check.
    - hide_closed, remote_only: bool, default-false like app.py's checkboxes.
    - query: str, matched against title/description.

    Returns (conditions: list, order_by): order_by is relevance-ranked when
    a Postgres full-text search is active, otherwise the usual recency
    ordering. The only place this function's behavior depends on the
    dialect — search_vector has no SQLite equivalent (spec §5).
    """
    postings = _schema.postings
    conditions = []

    tiers = filters.get("tier")
    if tiers is not None:
        conditions.append(postings.c.tier.in_(tiers))

    orgs = filters.get("org")
    if orgs is not None:
        conditions.append(postings.c.org.in_(orgs))

    if filters.get("hide_closed"):
        conditions.append(postings.c.status.notin_(("likely_closed", "rejected")))

    if filters.get("remote_only"):
        conditions.append(func.lower(postings.c.workplace_type) == "remote")

    query_text = (filters.get("query") or "").strip()
    # Matches the old _logic.py's ORDER BY COALESCE(posted_at, first_seen)
    # DESC — a posting without a parsed posted_at still sorts by recency
    # rather than sinking to the bottom.
    order_by = func.coalesce(postings.c.posted_at, postings.c.first_seen).desc()

    if query_text:
        if dialect_name == "postgresql":
            # search_vector isn't declared in _schema.py's portable Table
            # (no SQLite equivalent, added by a raw-SQL migration — spec
            # §5); referenced ad hoc via sqlalchemy.column, valid only on
            # this dialect branch.
            search_vector = column("search_vector")
            tsquery = func.websearch_to_tsquery("english", query_text)
            conditions.append(search_vector.op("@@")(tsquery))
            order_by = func.ts_rank(search_vector, tsquery).desc()
        else:
            like = f"%{query_text.lower()}%"
            conditions.append(
                or_(
                    func.lower(postings.c.title).like(like),
                    func.lower(postings.c.description).like(like),
                )
            )

    return conditions, order_by


def list_postings(engine, filters, page=1, size=60):
    postings = _schema.postings
    conditions, order_by = _build_where(filters, engine.dialect.name)

    with engine.connect() as conn:
        count_stmt = select(func.count()).select_from(postings)
        if conditions:
            count_stmt = count_stmt.where(*conditions)
        total = conn.execute(count_stmt).scalar_one()

        stmt = select(postings).order_by(order_by).limit(size).offset((page - 1) * size)
        if conditions:
            stmt = stmt.where(*conditions)
        rows = conn.execute(stmt).mappings().all()

    return [dict(row) for row in rows], total


def set_status(engine, source, ats_id, new_status):
    if new_status not in STATUS_VALUES:
        raise ValueError(f"invalid status: {new_status!r}")
    postings = _schema.postings
    with engine.begin() as conn:
        conn.execute(
            postings.update()
            .where(postings.c.source == source, postings.c.ats_id == ats_id)
            .values(status=new_status)
        )
