"""Tests for the SQLite reconciliation store (scripts/store.py).

Every test opens its own tmp_path database — never the real data/jobs.db.
"""
import store


def _posting(ats_id, **overrides):
    base = {
        "ats_id": ats_id,
        "title": "Some Role",
        "location": "Remote",
        "workplace_type": "remote",
        "team": None,
        "commitment": None,
        "url": f"https://example.com/{ats_id}",
        "description": "desc",
        "posted_at": "2024-01-01",
    }
    base.update(overrides)
    return base


def test_open_db_creates_schema(tmp_path):
    conn = store.open_db(tmp_path / "jobs.db")
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='postings'"
    ).fetchone()
    assert row is not None
    conn.close()


def test_insert_new_postings(tmp_path):
    conn = store.open_db(tmp_path / "jobs.db")
    new_count = store.upsert_postings(conn, "Acme", "A", "lever", [_posting("1"), _posting("2")])

    assert new_count == 2
    rows = conn.execute("SELECT ats_id, status FROM postings ORDER BY ats_id").fetchall()
    assert [r[0] for r in rows] == ["1", "2"]
    assert all(r[1] == "new" for r in rows)


def test_rerun_with_same_input_is_idempotent(tmp_path):
    conn = store.open_db(tmp_path / "jobs.db")
    store.upsert_postings(conn, "Acme", "A", "lever", [_posting("1")])

    new_count = store.upsert_postings(conn, "Acme", "A", "lever", [_posting("1")])

    assert new_count == 0
    count = conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0]
    assert count == 1


def test_changed_fields_refresh_but_first_seen_is_preserved(tmp_path):
    conn = store.open_db(tmp_path / "jobs.db")
    store.upsert_postings(conn, "Acme", "A", "lever", [_posting("1", title="Old Title")])
    first_seen_before = conn.execute(
        "SELECT first_seen FROM postings WHERE ats_id='1'"
    ).fetchone()[0]

    store.upsert_postings(conn, "Acme", "A", "lever", [_posting("1", title="New Title")])

    row = conn.execute("SELECT title, first_seen FROM postings WHERE ats_id='1'").fetchone()
    assert row[0] == "New Title"
    assert row[1] == first_seen_before


def test_disappearing_posting_is_marked_likely_closed(tmp_path):
    conn = store.open_db(tmp_path / "jobs.db")
    store.upsert_postings(conn, "Acme", "A", "lever", [_posting("1")])

    store.upsert_postings(conn, "Acme", "A", "lever", [])  # posting no longer in the ATS response

    status = conn.execute("SELECT status FROM postings WHERE ats_id='1'").fetchone()[0]
    assert status == "likely_closed"


def test_manually_set_status_is_never_overwritten_by_reconciliation(tmp_path):
    conn = store.open_db(tmp_path / "jobs.db")
    store.upsert_postings(conn, "Acme", "A", "lever", [_posting("1"), _posting("2")])
    conn.execute("UPDATE postings SET status='applied' WHERE ats_id='2'")
    conn.commit()

    # Next fetch no longer returns either posting.
    store.upsert_postings(conn, "Acme", "A", "lever", [])

    statuses = dict(conn.execute("SELECT ats_id, status FROM postings").fetchall())
    assert statuses["1"] == "likely_closed"  # was 'new' -> reconciled
    assert statuses["2"] == "applied"  # manual status untouched


def test_reconciliation_is_scoped_to_org_and_source(tmp_path):
    conn = store.open_db(tmp_path / "jobs.db")
    store.upsert_postings(conn, "Acme", "A", "lever", [_posting("1")])
    store.upsert_postings(conn, "Beta", "B", "lever", [_posting("2")])

    # Acme's fetch comes back empty; Beta's posting must be unaffected.
    store.upsert_postings(conn, "Acme", "A", "lever", [])

    acme_status = conn.execute("SELECT status FROM postings WHERE org='Acme'").fetchone()[0]
    beta_status = conn.execute("SELECT status FROM postings WHERE org='Beta'").fetchone()[0]
    assert acme_status == "likely_closed"
    assert beta_status == "new"
