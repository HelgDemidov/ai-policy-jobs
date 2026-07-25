"""Tests for the Streamlit card-view app (app.py) via Streamlit's AppTest
harness — runs the real script headlessly, no browser required.

Each test redirects store.DB_PATH to a tmp_path database via monkeypatch
BEFORE calling AppTest.run(). This works because app.py's own
`from store import DB_PATH` re-executes on every .run() call (verified
empirically) and reads whatever store.DB_PATH currently holds — so patching
the shared, already-imported `store` module's attribute (not app.py's) is
what redirects the app away from the real data/jobs.db.
"""
from pathlib import Path

from streamlit.testing.v1 import AppTest

import store

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")


def _seed_two_orgs(db_path):
    conn = store.open_db(db_path)
    store.upsert_postings(
        conn,
        "Acme",
        "A",
        "lever",
        [
            {
                "ats_id": "1",
                "title": "Policy Analyst",
                "location": "Remote",
                "workplace_type": "remote",
                "team": None,
                "commitment": None,
                "url": "https://example.com/1",
                "description": "About the Acme role",
                "posted_at": "2024-01-02",
            }
        ],
    )
    store.upsert_postings(
        conn,
        "Beta",
        "B",
        "lever",
        [
            {
                "ats_id": "2",
                "title": "Senior Researcher",
                "location": "London",
                "workplace_type": "onsite",
                "team": None,
                "commitment": None,
                "url": "https://example.com/2",
                "description": "About the Beta role",
                "posted_at": "2024-01-01",
            }
        ],
    )
    conn.close()


def test_app_loads_and_shows_seeded_postings(tmp_path, monkeypatch):
    db_path = tmp_path / "jobs.db"
    _seed_two_orgs(db_path)
    monkeypatch.setattr(store, "DB_PATH", db_path)

    at = AppTest.from_file(APP_PATH)
    at.run(timeout=15)

    assert not at.exception
    assert at.title[0].value == "🧭 Job Search Tracker"
    assert at.caption[0].value == "2 of 2 tracked posting(s)"

    card_titles = [md.value for md in at.markdown if 'class="card-title"' in md.value]
    assert any("Policy Analyst" in t for t in card_titles)
    assert any("Senior Researcher" in t for t in card_titles)


def test_missing_db_shows_info_message_instead_of_crashing(tmp_path, monkeypatch):
    db_path = tmp_path / "never_created.db"
    monkeypatch.setattr(store, "DB_PATH", db_path)

    at = AppTest.from_file(APP_PATH)
    at.run(timeout=15)

    assert not at.exception
    assert any("scripts/run.py" in i.value for i in at.info)


def test_organization_filter_narrows_visible_postings(tmp_path, monkeypatch):
    db_path = tmp_path / "jobs.db"
    _seed_two_orgs(db_path)
    monkeypatch.setattr(store, "DB_PATH", db_path)

    at = AppTest.from_file(APP_PATH)
    at.run(timeout=15)

    org_filter = next(ms for ms in at.multiselect if ms.label == "Organization")
    org_filter.set_value(["Acme"]).run(timeout=15)

    assert not at.exception
    assert at.caption[0].value == "1 of 2 tracked posting(s)"
    card_titles = [md.value for md in at.markdown if 'class="card-title"' in md.value]
    assert any("Policy Analyst" in t for t in card_titles)
    assert not any("Senior Researcher" in t for t in card_titles)


def test_changing_status_writes_back_to_the_database(tmp_path, monkeypatch):
    db_path = tmp_path / "jobs.db"
    _seed_two_orgs(db_path)
    monkeypatch.setattr(store, "DB_PATH", db_path)

    at = AppTest.from_file(APP_PATH)
    at.run(timeout=15)

    # Cards are sorted by posted_at desc, so index 0 is Acme's posting (ats_id "1").
    at.selectbox[0].select("applied").run(timeout=15)

    assert not at.exception
    conn = store.open_db(db_path)
    status = conn.execute("SELECT status FROM postings WHERE ats_id='1'").fetchone()[0]
    conn.close()
    assert status == "applied"


def test_hide_closed_checkbox_excludes_rejected_postings(tmp_path, monkeypatch):
    db_path = tmp_path / "jobs.db"
    _seed_two_orgs(db_path)
    conn = store.open_db(db_path)
    conn.execute("UPDATE postings SET status='rejected' WHERE ats_id='2'")
    conn.commit()
    conn.close()
    monkeypatch.setattr(store, "DB_PATH", db_path)

    at = AppTest.from_file(APP_PATH)
    at.run(timeout=15)

    assert at.caption[0].value == "1 of 2 tracked posting(s)"  # Beta hidden by default

    hide_checkbox = at.checkbox[0]
    hide_checkbox.uncheck().run(timeout=15)

    assert at.caption[0].value == "2 of 2 tracked posting(s)"  # now shown
