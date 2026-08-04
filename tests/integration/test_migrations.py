"""Verifies the integration tier's plumbing (CI Postgres service, DATABASE_URL,
psycopg driver) works end-to-end. Real migration/schema-drift checks land here
in the Alembic commit (docs/tech_specs/web-postgres-migration/spec.md §4) —
starts as a bare connectivity smoke test.
"""
import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


def test_can_connect_and_query(pg_engine):
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar_one() == 1
