"""Verifies Alembic migrations produce exactly the schema _schema.py
declares, plus the Postgres-only search_vector/GIN index (excluded from
that portable metadata by design — see alembic/env.py's include_object).

Runs only in CI's test-integration job, which applies `alembic upgrade
head` against a fresh postgres:17 service container before this module
executes — never against a real dev/prod database (see pg_engine in
tests/integration/conftest.py, which skips locally when DATABASE_URL is
unset).
"""
import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

WEB_API_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "api"
if str(WEB_API_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_API_DIR))

pytestmark = pytest.mark.integration


def test_migrated_tables_match_schema(pg_engine):
    inspector = inspect(pg_engine)
    tables = set(inspector.get_table_names())
    assert {"postings", "organizations", "searches"} <= tables


def test_postings_has_org_id_fk_to_organizations(pg_engine):
    inspector = inspect(pg_engine)
    fks = inspector.get_foreign_keys("postings")
    assert any(fk["referred_table"] == "organizations" for fk in fks)


def test_search_vector_column_and_gin_index_exist(pg_engine):
    with pg_engine.connect() as conn:
        data_type = conn.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'postings' AND column_name = 'search_vector'"
            )
        ).scalar_one_or_none()
    assert data_type == "tsvector"

    inspector = inspect(pg_engine)
    index_names = {ix["name"] for ix in inspector.get_indexes("postings")}
    assert "ix_postings_search_vector" in index_names


def test_full_text_search_ranks_title_match_above_description_only(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO organizations (name, origin) VALUES ('FTS Test Org', 'discovered')")
        )
        conn.execute(
            text(
                """INSERT INTO postings
                   (org, source, ats_id, title, description, url, first_seen, last_seen)
                   VALUES
                   ('FTS Test Org', 'fts_test', '1', 'AI Governance Analyst',
                    'We need someone for governance work', 'https://example.com/1',
                    '2026-01-01', '2026-01-01'),
                   ('FTS Test Org', 'fts_test', '2', 'Software Engineer',
                    'AI is mentioned once here, governance is not the focus',
                    'https://example.com/2', '2026-01-01', '2026-01-01')"""
            )
        )
        rows = conn.execute(
            text(
                """SELECT title, ts_rank(search_vector, websearch_to_tsquery('english', 'AI governance')) AS rank
                   FROM postings WHERE source = 'fts_test'
                   ORDER BY rank DESC"""
            )
        ).all()
        conn.execute(text("DELETE FROM postings WHERE source = 'fts_test'"))
        conn.execute(text("DELETE FROM organizations WHERE name = 'FTS Test Org'"))

    assert len(rows) == 2
    assert rows[0].title == "AI Governance Analyst"
    assert rows[0].rank > rows[1].rank
