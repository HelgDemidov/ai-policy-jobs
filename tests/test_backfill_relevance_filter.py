"""Tests for scripts/backfill_relevance_filter.py — the one-off retroactive
cleanup (docs/tech_specs/relevance-filtering/spec.md §4)."""
import backfill_relevance_filter
import store


def _insert(conn, ats_id, org, title, source="lever"):
    conn.execute(
        """INSERT INTO postings
           (org, source, ats_id, title, url, first_seen, last_seen, dedup_key)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            org, source, ats_id, title, f"https://example.com/{ats_id}",
            "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z",
            store._normalize_dedup_key(org, title),
        ),
    )
    conn.commit()


def test_deletes_rows_that_fail_filter_keeps_rows_that_pass(tmp_path):
    db_path = tmp_path / "jobs.db"
    filters_path = tmp_path / "filters.yaml"
    filters_path.write_text("org_blocklist: []\ntitle_require_any: [policy]\ntitle_exclude_any: [intern]\n")

    conn = store.open_db(db_path)
    _insert(conn, "keep1", "Think Tank Org", "Policy Analyst")
    _insert(conn, "drop1", "Think Tank Org", "Policy Intern")   # exclude-list hit
    _insert(conn, "drop2", "Think Tank Org", "Office Manager")  # no require-list hit
    conn.close()

    total, deleted = backfill_relevance_filter.backfill(db_path, filters_path)

    assert total == 3
    assert deleted == 2
    conn = store.open_db(db_path)
    remaining = conn.execute("SELECT ats_id FROM postings").fetchall()
    assert remaining == [("keep1",)]


def test_org_blocklist_deletes_regardless_of_title(tmp_path):
    db_path = tmp_path / "jobs.db"
    filters_path = tmp_path / "filters.yaml"
    filters_path.write_text("org_blocklist: [Spammy Recruiter]\n")

    conn = store.open_db(db_path)
    _insert(conn, "keep1", "Real Think Tank", "Policy Analyst")
    _insert(conn, "drop1", "Spammy Recruiter", "Senior Policy Analyst")
    conn.close()

    total, deleted = backfill_relevance_filter.backfill(db_path, filters_path)

    assert total == 2
    assert deleted == 1
    conn = store.open_db(db_path)
    remaining = conn.execute("SELECT ats_id FROM postings").fetchall()
    assert remaining == [("keep1",)]


def test_nothing_deleted_is_a_no_op(tmp_path):
    db_path = tmp_path / "jobs.db"
    filters_path = tmp_path / "filters.yaml"
    filters_path.write_text("org_blocklist: []\n")

    conn = store.open_db(db_path)
    _insert(conn, "keep1", "Think Tank", "Policy Analyst")
    conn.close()

    total, deleted = backfill_relevance_filter.backfill(db_path, filters_path)

    assert total == 1
    assert deleted == 0
    conn = store.open_db(db_path)
    assert conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0] == 1


def test_summary_printed_to_stdout(tmp_path, capsys):
    db_path = tmp_path / "jobs.db"
    filters_path = tmp_path / "filters.yaml"
    filters_path.write_text("title_exclude_any: [intern]\n")

    conn = store.open_db(db_path)
    _insert(conn, "drop1", "Some Org", "Policy Intern", source="himalayas")
    conn.close()

    backfill_relevance_filter.backfill(db_path, filters_path)

    captured = capsys.readouterr()
    assert "1 total posting(s), 1 filtered out." in captured.out
    assert "himalayas: 1" in captured.out
    assert "title_exclude_any" in captured.out


def test_missing_filters_path_deletes_nothing(tmp_path):
    """Same "missing config -> no-op" behavior relevance_filter.load_filters
    already guarantees — a backfill run against a not-yet-created
    filters.yaml must not wipe the table."""
    db_path = tmp_path / "jobs.db"
    conn = store.open_db(db_path)
    _insert(conn, "keep1", "Any Org", "Any Title At All")
    conn.close()

    total, deleted = backfill_relevance_filter.backfill(db_path, tmp_path / "does-not-exist.yaml")

    assert total == 1
    assert deleted == 0
