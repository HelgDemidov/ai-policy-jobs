"""Shared SQLAlchemy Core schema for postings/organizations/searches — the
single definition used by _repo.py (deployed, queries Neon), alembic/env.py
and scripts/postgres_sync.py (local, migrate/mirror), and tests (SQLite
in-memory). Portable across both dialects with one deliberate exception:
`postings.search_vector` is added by a raw-SQL Postgres-only migration and
is NOT declared here — tsvector has no SQLite equivalent (spec §5).

`postings` mirrors scripts/store.py's SQLite DDL (its own separate source of
truth, intentionally not touched by this migration — spec §1/rationale),
plus `org_id`, a soft FK populated by scripts/postgres_sync.py's mirror step.
"""
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)

metadata = MetaData()

organizations = Table(
    "organizations",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", Text, nullable=False, unique=True),
    Column("tier", Text),  # curated (orgs.yaml) only — NULL for discovered
    Column("ats", Text),
    Column("slug", Text),
    Column("origin", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("origin IN ('curated', 'discovered')", name="ck_organizations_origin"),
)

searches = Table(
    "searches",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("search_id", Text, nullable=False, unique=True),
    Column("source", Text, nullable=False),
    Column("query_text", Text),
    Column("location", Text),
    Column("manual", Boolean, nullable=False, server_default=text("false")),
    Column("raw", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

postings = Table(
    "postings",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("org", Text, nullable=False, index=True),
    Column("tier", Text, index=True),
    Column("source", Text, nullable=False),
    Column("ats_id", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("location", Text),
    Column("workplace_type", Text, index=True),
    Column("team", Text),
    Column("commitment", Text),
    Column("url", Text, nullable=False),
    Column("description", Text),
    Column("posted_at", Text),
    Column("first_seen", Text, nullable=False),
    Column("last_seen", Text, nullable=False),
    Column("status", Text, nullable=False, server_default="new", index=True),
    Column("dedup_key", Text),
    # Soft link, not the source of truth for filtering — see spec §3
    # rationale (tier for query-family postings is geography-derived, not
    # organization-derived; org_id exists for future joins/analytics only).
    Column("org_id", Integer, ForeignKey("organizations.id")),
    UniqueConstraint("source", "ats_id", name="uq_postings_source_ats_id"),
    CheckConstraint(
        "status IN ('new', 'reviewed', 'applied', 'rejected', 'likely_closed')",
        name="ck_postings_status",
    ),
)

Index("ix_postings_org_status", postings.c.org, postings.c.status)


def resolve_database_url(url: str) -> str:
    """Neon/Vercel hand out a bare `postgresql://` URL — SQLAlchemy defaults
    that scheme to the psycopg2 dialect, which isn't installed (this project
    uses psycopg 3). Live-verified 2026-08-04: create_engine() on the raw
    URL raises `ModuleNotFoundError: No module named 'psycopg2'` without
    this rewrite; SQLite URLs (tests) pass through untouched."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url
