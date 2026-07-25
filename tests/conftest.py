"""Shared test setup: make scripts/ importable as plain modules, matching how
app.py and the scripts themselves resolve their own imports (sys.path insert,
not a package)."""
import sys
from pathlib import Path

import pytest
import streamlit as st

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture(autouse=True)
def _clear_streamlit_cache():
    """st.cache_data is a process-global cache keyed by function identity, not
    by AppTest instance — without this, one test's cached load_postings()
    result leaks into the next test's AppTest run against a different tmp_path
    database (caught live: a 'missing DB' test saw a previous test's cached
    non-empty DataFrame instead of the real empty one)."""
    st.cache_data.clear()
    yield
