"""Fixtures for tests/integration/ — these need a real Postgres reachable via
DATABASE_URL. The `integration` marker (pyproject.toml addopts) already keeps
them out of a bare `.venv/bin/pytest`; skipping here too is a second line of
defense for anyone running `pytest tests/integration` directly."""
import os

import pytest
from sqlalchemy import create_engine


@pytest.fixture
def pg_engine():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — integration tests need a real Postgres")
    engine = create_engine(url)
    yield engine
    engine.dispose()
