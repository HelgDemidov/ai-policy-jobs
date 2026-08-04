"""Tests for the SQLite reconciliation store (scripts/store.py).

Every test opens its own tmp_path database — never the real data/jobs.db.
"""
import sqlite3
from datetime import datetime, timedelta, timezone

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


def _search_posting(ats_id, org, **overrides):
    base = _posting(ats_id, **overrides)
    base["org"] = org
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
    store.upsert_postings(conn, "Acme", "A", "lever", [_posting("1"), _posting("2")])

    # "2" is gone from the next fetch, but the response isn't empty — "1" is
    # still there — so this is a normal, trustworthy partial reconciliation
    # (see the empty-response tests below for the *untrustworthy* case).
    store.upsert_postings(conn, "Acme", "A", "lever", [_posting("1")])

    statuses = dict(conn.execute("SELECT ats_id, status FROM postings").fetchall())
    assert statuses["1"] == "new"
    assert statuses["2"] == "likely_closed"


def test_manually_set_status_is_never_overwritten_by_reconciliation(tmp_path):
    conn = store.open_db(tmp_path / "jobs.db")
    store.upsert_postings(conn, "Acme", "A", "lever", [_posting("1"), _posting("2")])
    conn.execute("UPDATE postings SET status='applied' WHERE ats_id='2'")
    conn.commit()

    # Next fetch no longer returns either "1" or "2", but does return a new
    # posting "3" — a non-empty response, so reconciliation is trusted.
    store.upsert_postings(conn, "Acme", "A", "lever", [_posting("3")])

    statuses = dict(conn.execute("SELECT ats_id, status FROM postings").fetchall())
    assert statuses["1"] == "likely_closed"  # was 'new' -> reconciled
    assert statuses["2"] == "applied"  # manual status untouched
    assert statuses["3"] == "new"


def test_reconciliation_is_scoped_to_org_and_source(tmp_path):
    conn = store.open_db(tmp_path / "jobs.db")
    store.upsert_postings(conn, "Acme", "A", "lever", [_posting("1"), _posting("2")])
    store.upsert_postings(conn, "Beta", "B", "lever", [_posting("3")])

    # Acme's fetch drops "2" but still returns "1"; Beta must be unaffected.
    store.upsert_postings(conn, "Acme", "A", "lever", [_posting("1")])

    acme_statuses = dict(
        conn.execute("SELECT ats_id, status FROM postings WHERE org='Acme'").fetchall()
    )
    beta_status = conn.execute("SELECT status FROM postings WHERE org='Beta'").fetchone()[0]
    assert acme_statuses == {"1": "new", "2": "likely_closed"}
    assert beta_status == "new"


# --- empty-response guard (added alongside the systemd daily timer: an ---
# --- unattended run can no longer have a human notice "that looks wrong") -


def test_empty_response_with_no_history_is_a_harmless_noop(tmp_path):
    conn = store.open_db(tmp_path / "jobs.db")

    new_count = store.upsert_postings(conn, "Acme", "A", "lever", [])

    assert new_count == 0
    assert conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0] == 0


def test_empty_response_with_existing_history_skips_reconciliation(tmp_path, capsys):
    conn = store.open_db(tmp_path / "jobs.db")
    store.upsert_postings(conn, "Acme", "A", "lever", [_posting("1")])

    # A renamed slug or a changed response shape looks exactly like this to
    # the connector — a real closure must not be inferred from it alone.
    store.upsert_postings(conn, "Acme", "A", "lever", [])

    status = conn.execute("SELECT status FROM postings WHERE ats_id='1'").fetchone()[0]
    assert status == "new"  # NOT reconciled — the empty response is not trusted
    captured = capsys.readouterr()
    assert "Acme" in captured.out
    assert "skipping reconciliation" in captured.out


def test_empty_response_guard_is_scoped_to_org_and_source(tmp_path):
    conn = store.open_db(tmp_path / "jobs.db")
    store.upsert_postings(conn, "Acme", "A", "lever", [_posting("1")])

    # Beta has no history at all for (Beta, lever) — its empty response is
    # the harmless-noop case, not the guarded one, and must not affect Acme.
    store.upsert_postings(conn, "Beta", "B", "lever", [])

    acme_status = conn.execute("SELECT status FROM postings WHERE org='Acme'").fetchone()[0]
    beta_count = conn.execute("SELECT COUNT(*) FROM postings WHERE org='Beta'").fetchone()[0]
    assert acme_status == "new"
    assert beta_count == 0


# --- IntegrityError backstop (invalid records don't crash the batch) --------


def test_upsert_postings_skips_invalid_record_without_crashing(tmp_path, capsys):
    conn = store.open_db(tmp_path / "jobs.db")

    new_count = store.upsert_postings(
        conn, "Acme", "A", "lever",
        [_posting("1", title=None), _posting("2")],
    )

    assert new_count == 1
    ats_ids = [r[0] for r in conn.execute("SELECT ats_id FROM postings").fetchall()]
    assert ats_ids == ["2"]
    captured = capsys.readouterr()
    assert "skipping invalid posting" in captured.out


def test_upsert_search_postings_skips_invalid_record_without_crashing(tmp_path, capsys):
    conn = store.open_db(tmp_path / "jobs.db")

    new_count = store.upsert_search_postings(
        conn, "himalayas",
        [_search_posting("h1", None, title="No Employer"), _search_posting("h2", "Acme", title="Role")],
    )

    assert new_count == 1
    ats_ids = [r[0] for r in conn.execute("SELECT ats_id FROM postings").fetchall()]
    assert ats_ids == ["h2"]
    captured = capsys.readouterr()
    assert "skipping invalid posting" in captured.out


# --- dedup_key migration + backfill ---------------------------------------


def test_ats_insert_populates_dedup_key(tmp_path):
    conn = store.open_db(tmp_path / "jobs.db")
    store.upsert_postings(conn, "Acme Corp", "A", "lever", [_posting("1", title="Policy Analyst")])

    key = conn.execute("SELECT dedup_key FROM postings WHERE ats_id='1'").fetchone()[0]
    assert key == "acme corp policy analyst"


def test_open_db_backfills_dedup_key_on_legacy_rows(tmp_path):
    db_path = tmp_path / "jobs.db"
    # Simulate a pre-migration database: schema without dedup_key, one row
    # inserted the old way (no dedup_key column at all).
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE postings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org TEXT NOT NULL, tier TEXT, source TEXT NOT NULL, ats_id TEXT NOT NULL,
            title TEXT NOT NULL, location TEXT, workplace_type TEXT, team TEXT,
            commitment TEXT, url TEXT NOT NULL, description TEXT, posted_at TEXT,
            first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new',
            UNIQUE(source, ats_id)
        )
    """)
    conn.execute(
        """INSERT INTO postings (org, tier, source, ats_id, title, url, first_seen, last_seen)
           VALUES ('Legacy Org', 'A', 'lever', '1', 'Old Role', 'https://x/1', 'x', 'x')"""
    )
    conn.commit()
    conn.close()

    conn = store.open_db(db_path)  # triggers _ensure_dedup_key_column
    key = conn.execute("SELECT dedup_key FROM postings WHERE ats_id='1'").fetchone()[0]
    assert key == "legacy org old role"


# --- upsert_search_postings -------------------------------------------------


def test_search_insert_new_postings(tmp_path):
    conn = store.open_db(tmp_path / "jobs.db")
    new_count = store.upsert_search_postings(
        conn, "himalayas", [_search_posting("h1", "R Street Institute", title="Policy Director")]
    )

    assert new_count == 1
    row = conn.execute("SELECT org, title, status FROM postings WHERE ats_id='h1'").fetchone()
    assert row == ("R Street Institute", "Policy Director", "new")


def test_search_rerun_same_ats_id_updates_not_duplicates(tmp_path):
    conn = store.open_db(tmp_path / "jobs.db")
    store.upsert_search_postings(conn, "himalayas", [_search_posting("h1", "Acme", title="Old")])

    new_count = store.upsert_search_postings(conn, "himalayas", [_search_posting("h1", "Acme", title="New")])

    assert new_count == 0
    row = conn.execute("SELECT title FROM postings WHERE ats_id='h1'").fetchone()
    assert row[0] == "New"


def test_search_postings_dedup_across_sources_by_org_and_title(tmp_path):
    conn = store.open_db(tmp_path / "jobs.db")
    store.upsert_postings(conn, "RAND Europe", "B", "lever", [_posting("l1", title="Research Analyst")])

    # A different source (query-centric) finds "the same" posting under a
    # different native id — must touch the existing row, not insert a dupe.
    new_count = store.upsert_search_postings(
        conn, "jobspy_linkedin", [_search_posting("li-999", "RAND Europe", title="Research Analyst")]
    )

    assert new_count == 0
    count = conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0]
    assert count == 1
    # The original ATS-family row is the one that persists, now touched.
    row = conn.execute("SELECT source, ats_id FROM postings").fetchone()
    assert row == ("lever", "l1")


def test_search_postings_no_reconciliation_on_empty_batch(tmp_path):
    conn = store.open_db(tmp_path / "jobs.db")
    store.upsert_search_postings(conn, "himalayas", [_search_posting("h1", "Acme", title="Role")])

    # Next search for the same query comes back empty — unlike the ATS
    # family, this must NOT mark the posting likely_closed.
    store.upsert_search_postings(conn, "himalayas", [])

    status = conn.execute("SELECT status FROM postings WHERE ats_id='h1'").fetchone()[0]
    assert status == "new"


def test_search_posting_carries_its_own_tier(tmp_path):
    conn = store.open_db(tmp_path / "jobs.db")
    store.upsert_search_postings(conn, "himalayas", [_search_posting("h1", "Acme", title="Role", tier="A")])

    tier = conn.execute("SELECT tier FROM postings WHERE ats_id='h1'").fetchone()[0]
    assert tier == "A"


# --- expire_stale_search_postings -------------------------------------------


def _set_last_seen(conn, ats_id, when):
    conn.execute("UPDATE postings SET last_seen=? WHERE ats_id=?", (when.isoformat(), ats_id))
    conn.commit()


def test_expire_stale_marks_old_new_postings_closed(tmp_path):
    conn = store.open_db(tmp_path / "jobs.db")
    store.upsert_search_postings(conn, "himalayas", [_search_posting("h1", "Acme", title="Role")])
    _set_last_seen(conn, "h1", datetime.now(timezone.utc) - timedelta(days=100))

    count = store.expire_stale_search_postings(conn, ["himalayas"], max_age_days=45)

    assert count == 1
    status = conn.execute("SELECT status FROM postings WHERE ats_id='h1'").fetchone()[0]
    assert status == "likely_closed"


def test_expire_stale_leaves_recent_postings_alone(tmp_path):
    conn = store.open_db(tmp_path / "jobs.db")
    store.upsert_search_postings(conn, "himalayas", [_search_posting("h1", "Acme", title="Role")])

    store.expire_stale_search_postings(conn, ["himalayas"], max_age_days=45)

    status = conn.execute("SELECT status FROM postings WHERE ats_id='h1'").fetchone()[0]
    assert status == "new"


def test_expire_stale_never_overwrites_manual_status(tmp_path):
    conn = store.open_db(tmp_path / "jobs.db")
    store.upsert_search_postings(conn, "himalayas", [_search_posting("h1", "Acme", title="Role")])
    conn.execute("UPDATE postings SET status='applied' WHERE ats_id='h1'")
    _set_last_seen(conn, "h1", datetime.now(timezone.utc) - timedelta(days=100))

    store.expire_stale_search_postings(conn, ["himalayas"], max_age_days=45)

    status = conn.execute("SELECT status FROM postings WHERE ats_id='h1'").fetchone()[0]
    assert status == "applied"


def test_expire_stale_scoped_to_given_sources_only(tmp_path):
    conn = store.open_db(tmp_path / "jobs.db")
    store.upsert_postings(conn, "Acme", "A", "lever", [_posting("1")])
    _set_last_seen(conn, "1", datetime.now(timezone.utc) - timedelta(days=100))

    # lever is an ATS source, not in the search-family sources list — must
    # not be touched by expiry even though it's old and still 'new'.
    store.expire_stale_search_postings(conn, ["himalayas"], max_age_days=45)

    status = conn.execute("SELECT status FROM postings WHERE ats_id='1'").fetchone()[0]
    assert status == "new"
