"""Tests for web/api/_logic.py (scripts/store.py's schema is reused here to
build a realistic test DB — this is a test-only import, not something
_logic.py itself does; the deployed function can't reach scripts/)."""
import _logic
import store


def _conn(tmp_path):
    return store.open_db(tmp_path / "jobs.db")


def _insert(conn, ats_id, **overrides):
    row = {
        "org": "Org", "tier": "A", "source": "lever", "ats_id": ats_id,
        "title": "Role", "location": None, "workplace_type": None, "team": None,
        "commitment": None, "url": f"https://example.com/{ats_id}", "description": None,
        "posted_at": None, "first_seen": "2026-01-01T00:00:00+00:00",
        "last_seen": "2026-01-01T00:00:00+00:00", "status": "new",
    }
    row.update(overrides)
    conn.execute(
        """INSERT INTO postings
           (org, tier, source, ats_id, title, location, workplace_type, team,
            commitment, url, description, posted_at, first_seen, last_seen, status)
           VALUES (:org,:tier,:source,:ats_id,:title,:location,:workplace_type,:team,
                   :commitment,:url,:description,:posted_at,:first_seen,:last_seen,:status)""",
        row,
    )
    conn.commit()


def test_list_postings_no_filters_returns_everything(tmp_path):
    conn = _conn(tmp_path)
    _insert(conn, "1")
    _insert(conn, "2")

    result = _logic.list_postings(conn, {})

    assert len(result) == 2


def test_tier_filter_none_means_no_filter(tmp_path):
    conn = _conn(tmp_path)
    _insert(conn, "1", tier="A")
    _insert(conn, "2", tier="B")

    result = _logic.list_postings(conn, {"tier": None})

    assert len(result) == 2


def test_tier_filter_empty_list_means_filter_to_nothing(tmp_path):
    """An empty list is NOT the same as no filter — it mirrors app.py's
    st.multiselect with everything deselected, which shows zero cards
    (df["tier"].isin([])), not all cards."""
    conn = _conn(tmp_path)
    _insert(conn, "1", tier="A")

    result = _logic.list_postings(conn, {"tier": []})

    assert result == []


def test_tier_filter_selects_matching_only(tmp_path):
    conn = _conn(tmp_path)
    _insert(conn, "1", tier="A")
    _insert(conn, "2", tier="B")

    result = _logic.list_postings(conn, {"tier": ["A"]})

    assert [p["ats_id"] for p in result] == ["1"]


def test_org_filter_matches_tier_filter_semantics(tmp_path):
    conn = _conn(tmp_path)
    _insert(conn, "1", org="Alpha")
    _insert(conn, "2", org="Beta")

    result = _logic.list_postings(conn, {"org": ["Alpha"]})

    assert [p["ats_id"] for p in result] == ["1"]


def test_hide_closed_excludes_likely_closed_and_rejected(tmp_path):
    conn = _conn(tmp_path)
    _insert(conn, "1", status="new")
    _insert(conn, "2", status="likely_closed")
    _insert(conn, "3", status="rejected")

    result = _logic.list_postings(conn, {"hide_closed": True})

    assert [p["ats_id"] for p in result] == ["1"]


def test_hide_closed_false_includes_everything(tmp_path):
    conn = _conn(tmp_path)
    _insert(conn, "1", status="new")
    _insert(conn, "2", status="likely_closed")

    result = _logic.list_postings(conn, {"hide_closed": False})

    assert len(result) == 2


def test_remote_only_matches_case_insensitively(tmp_path):
    conn = _conn(tmp_path)
    _insert(conn, "1", workplace_type="Remote")
    _insert(conn, "2", workplace_type="onsite")
    _insert(conn, "3", workplace_type=None)

    result = _logic.list_postings(conn, {"remote_only": True})

    assert [p["ats_id"] for p in result] == ["1"]


def test_query_matches_title_or_description(tmp_path):
    conn = _conn(tmp_path)
    _insert(conn, "1", title="AI Policy Analyst", description="")
    _insert(conn, "2", title="Software Engineer", description="Works on AI policy tools")
    _insert(conn, "3", title="Chef", description="Cooking")

    result = _logic.list_postings(conn, {"query": "ai policy"})

    assert {p["ats_id"] for p in result} == {"1", "2"}


def test_ordering_uses_posted_at_falling_back_to_first_seen(tmp_path):
    conn = _conn(tmp_path)
    _insert(conn, "old", posted_at="2026-01-01", first_seen="2026-01-01T00:00:00+00:00")
    _insert(conn, "new", posted_at="2026-02-01", first_seen="2026-01-01T00:00:00+00:00")

    result = _logic.list_postings(conn, {})

    assert [p["ats_id"] for p in result] == ["new", "old"]


def test_set_status_updates_matching_row(tmp_path):
    conn = _conn(tmp_path)
    _insert(conn, "1", source="lever", status="new")

    _logic.set_status(conn, "lever", "1", "applied")

    row = conn.execute("SELECT status FROM postings WHERE ats_id='1'").fetchone()
    assert row[0] == "applied"


def test_set_status_rejects_invalid_status(tmp_path):
    conn = _conn(tmp_path)
    _insert(conn, "1", source="lever", status="new")

    try:
        _logic.set_status(conn, "lever", "1", "not-a-real-status")
        assert False, "expected ValueError"
    except ValueError:
        pass

    row = conn.execute("SELECT status FROM postings WHERE ats_id='1'").fetchone()
    assert row[0] == "new"


def test_set_status_no_matching_row_is_a_silent_noop(tmp_path):
    conn = _conn(tmp_path)
    _insert(conn, "1", source="lever", status="new")

    _logic.set_status(conn, "greenhouse", "nonexistent", "applied")

    row = conn.execute("SELECT status FROM postings WHERE ats_id='1'").fetchone()
    assert row[0] == "new"
