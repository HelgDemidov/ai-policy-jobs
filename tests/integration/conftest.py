"""Fixtures for tests/integration/ — these need a real Postgres reachable via
DATABASE_URL. The `integration` marker (pyproject.toml addopts) already keeps
them out of a bare `.venv/bin/pytest`; skipping here too is a second line of
defense for anyone running `pytest tests/integration` directly."""
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine

WEB_API_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "api"
if str(WEB_API_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_API_DIR))

import _schema  # noqa: E402


@pytest.fixture
def pg_engine():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — integration tests need a real Postgres")
    engine = create_engine(_schema.resolve_database_url(url))
    yield engine
    engine.dispose()
