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

import store
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parent.parent / "app" / "app.py")


def _vacancy_counter_text(at):
    # Match the rendered <span>, not the injected <style> block that also
    # mentions the class name in its own CSS rule.
    return next(md.value for md in at.markdown if 'class="vacancy-counter"' in md.value)


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
    # The compass emoji title became a custom <h1> + inline SVG logo (a
    # monochrome transformer-block icon), so it's an st.markdown element now,
    # not an st.title one — at.title is empty.
    assert any("AI Policy Job Tracker" in md.value for md in at.markdown if "<h1" in md.value)
    assert "Current vacancies: 2" in _vacancy_counter_text(at)

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
    assert "Current vacancies: 1" in _vacancy_counter_text(at)
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


def test_tier_filter_narrows_visible_postings(tmp_path, monkeypatch):
    db_path = tmp_path / "jobs.db"
    _seed_two_orgs(db_path)
    monkeypatch.setattr(store, "DB_PATH", db_path)

    at = AppTest.from_file(APP_PATH)
    at.run(timeout=15)

    tier_filter = next(ms for ms in at.multiselect if ms.label == "Tier")
    tier_filter.set_value(["A"]).run(timeout=15)

    assert not at.exception
    assert "Current vacancies: 1" in _vacancy_counter_text(at)
    card_titles = [md.value for md in at.markdown if 'class="card-title"' in md.value]
    assert any("Policy Analyst" in t for t in card_titles)
    assert not any("Senior Researcher" in t for t in card_titles)


def test_search_filters_by_title_or_description(tmp_path, monkeypatch):
    db_path = tmp_path / "jobs.db"
    _seed_two_orgs(db_path)
    monkeypatch.setattr(store, "DB_PATH", db_path)

    at = AppTest.from_file(APP_PATH)
    at.run(timeout=15)

    at.text_input[0].set_value("Senior").run(timeout=15)

    assert not at.exception
    assert "Current vacancies: 1" in _vacancy_counter_text(at)
    card_titles = [md.value for md in at.markdown if 'class="card-title"' in md.value]
    assert any("Senior Researcher" in t for t in card_titles)
    assert not any("Policy Analyst" in t for t in card_titles)


def test_tier_badge_uses_a_distinct_css_class_per_tier(tmp_path, monkeypatch):
    # Regression test for TIER_CSS_CLASS: A/B/C used to share one "tier" class
    # (and therefore one color) — this pins each tier to its OWN class so a
    # future edit can't silently collapse them back into a single color.
    db_path = tmp_path / "jobs.db"
    _seed_two_orgs(db_path)
    monkeypatch.setattr(store, "DB_PATH", db_path)

    at = AppTest.from_file(APP_PATH)
    at.run(timeout=15)

    assert not at.exception
    chip_markdown = [md.value for md in at.markdown if "card-chip" in md.value and "Tier" in md.value]
    assert any('class="card-chip tier-a">Tier A' in c for c in chip_markdown)
    assert any('class="card-chip tier-b">Tier B' in c for c in chip_markdown)


def test_only_remote_checkbox_filters_to_remote_postings(tmp_path, monkeypatch):
    db_path = tmp_path / "jobs.db"
    _seed_two_orgs(db_path)  # Acme is remote, Beta is onsite
    monkeypatch.setattr(store, "DB_PATH", db_path)

    at = AppTest.from_file(APP_PATH)
    at.run(timeout=15)

    remote_checkbox = next(cb for cb in at.checkbox if cb.label == "Only remote")
    remote_checkbox.check().run(timeout=15)

    assert not at.exception
    assert "Current vacancies: 1" in _vacancy_counter_text(at)
    card_titles = [md.value for md in at.markdown if 'class="card-title"' in md.value]
    assert any("Policy Analyst" in t for t in card_titles)
    assert not any("Senior Researcher" in t for t in card_titles)


def test_only_remote_checkbox_treats_missing_workplace_type_as_not_remote(tmp_path, monkeypatch):
    # ~87 of 200 rows in the real database have no workplace_type at all
    # (query-centric sources don't always report it) — this is the realistic
    # failure mode for the filter, not a contrived edge case.
    db_path = tmp_path / "jobs.db"
    conn = store.open_db(db_path)
    store.upsert_postings(
        conn,
        "Gamma",
        "A",
        "lever",
        [
            {
                "ats_id": "3",
                "title": "Mystery Role",
                "location": None,
                "workplace_type": None,
                "team": None,
                "commitment": None,
                "url": "https://example.com/3",
                "description": "",
                "posted_at": "2024-01-03",
            }
        ],
    )
    conn.close()
    monkeypatch.setattr(store, "DB_PATH", db_path)

    at = AppTest.from_file(APP_PATH)
    at.run(timeout=15)

    remote_checkbox = next(cb for cb in at.checkbox if cb.label == "Only remote")
    remote_checkbox.check().run(timeout=15)

    assert not at.exception
    assert "Current vacancies: 0" in _vacancy_counter_text(at)


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

    assert "Current vacancies: 1" in _vacancy_counter_text(at)  # Beta hidden by default

    hide_checkbox = at.checkbox[0]
    hide_checkbox.uncheck().run(timeout=15)

    assert "Current vacancies: 2" in _vacancy_counter_text(at)  # now shown
