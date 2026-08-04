"""Tests for web/api/_repo.py — SQLite in-memory via _schema.py's shared
metadata, exercising the same filter semantics the old _logic.py had, plus
pagination and the dialect-branch fallback for full-text search (the
postgresql-only path is covered live against real Neon by
tests/integration/test_migrations.py, not here — see _repo._build_where's
docstring).
"""
import _repo
import _schema
from sqlalchemy import create_engine


def _engine():
    engine = create_engine("sqlite:///:memory:")
    _schema.metadata.create_all(engine)
    return engine


def _insert(engine, ats_id, **overrides):
    row = {
        "org": "Org", "tier": "A", "source": "lever", "ats_id": ats_id,
        "title": "Role", "location": None, "workplace_type": None, "team": None,
        "commitment": None, "url": f"https://example.com/{ats_id}", "description": None,
        "posted_at": None, "first_seen": "2026-01-01T00:00:00+00:00",
        "last_seen": "2026-01-01T00:00:00+00:00", "status": "new",
    }
    row.update(overrides)
    with engine.begin() as conn:
        conn.execute(_schema.postings.insert(), row)


def test_list_postings_no_filters_returns_everything():
    engine = _engine()
    _insert(engine, "1")
    _insert(engine, "2")

    items, total = _repo.list_postings(engine, {})

    assert len(items) == 2
    assert total == 2


def test_tier_filter_none_means_no_filter():
    engine = _engine()
    _insert(engine, "1", tier="A")
    _insert(engine, "2", tier="B")

    items, total = _repo.list_postings(engine, {"tier": None})

    assert total == 2


def test_tier_filter_empty_list_means_filter_to_nothing():
    """An empty list is NOT the same as no filter — mirrors app.py's
    st.multiselect with everything deselected: zero cards, not all cards."""
    engine = _engine()
    _insert(engine, "1", tier="A")

    items, total = _repo.list_postings(engine, {"tier": []})

    assert items == []
    assert total == 0


def test_tier_filter_selects_matching_only():
    engine = _engine()
    _insert(engine, "1", tier="A")
    _insert(engine, "2", tier="B")

    items, total = _repo.list_postings(engine, {"tier": ["A"]})

    assert [p["ats_id"] for p in items] == ["1"]
    assert total == 1


def test_org_filter_matches_tier_filter_semantics():
    engine = _engine()
    _insert(engine, "1", org="Alpha")
    _insert(engine, "2", org="Beta")

    items, _ = _repo.list_postings(engine, {"org": ["Alpha"]})

    assert [p["ats_id"] for p in items] == ["1"]


def test_hide_closed_excludes_likely_closed_and_rejected():
    engine = _engine()
    _insert(engine, "1", status="new")
    _insert(engine, "2", status="likely_closed")
    _insert(engine, "3", status="rejected")

    items, _ = _repo.list_postings(engine, {"hide_closed": True})

    assert [p["ats_id"] for p in items] == ["1"]


def test_hide_closed_false_includes_everything():
    engine = _engine()
    _insert(engine, "1", status="new")
    _insert(engine, "2", status="likely_closed")

    items, total = _repo.list_postings(engine, {"hide_closed": False})

    assert total == 2


def test_remote_only_matches_case_insensitively():
    engine = _engine()
    _insert(engine, "1", workplace_type="Remote")
    _insert(engine, "2", workplace_type="onsite")
    _insert(engine, "3", workplace_type=None)

    items, _ = _repo.list_postings(engine, {"remote_only": True})

    assert [p["ats_id"] for p in items] == ["1"]


def test_query_matches_title_or_description_via_like_fallback():
    """SQLite engines always take the LIKE-fallback branch of
    _build_where — this is the only branch exercisable in a hermetic test;
    the postgresql websearch_to_tsquery branch is verified live in
    tests/integration/test_migrations.py."""
    engine = _engine()
    _insert(engine, "1", title="AI Policy Analyst", description="")
    _insert(engine, "2", title="Software Engineer", description="Works on AI policy tools")
    _insert(engine, "3", title="Chef", description="Cooking")

    items, _ = _repo.list_postings(engine, {"query": "ai policy"})

    assert {p["ats_id"] for p in items} == {"1", "2"}


def test_ordering_uses_posted_at_falling_back_to_first_seen():
    engine = _engine()
    _insert(engine, "old", posted_at="2026-01-01", first_seen="2026-01-01T00:00:00+00:00")
    _insert(engine, "new", posted_at="2026-02-01", first_seen="2026-01-01T00:00:00+00:00")

    items, _ = _repo.list_postings(engine, {})

    assert [p["ats_id"] for p in items] == ["new", "old"]


def test_pagination_returns_requested_page_and_total_reflects_all_matches():
    engine = _engine()
    for i in range(5):
        _insert(engine, str(i), posted_at=f"2026-01-0{i + 1}")

    items, total = _repo.list_postings(engine, {}, page=2, size=2)

    # ats_ids "0".."4" posted 01-01.."01-05" -> newest-first: 4,3,2,1,0 ->
    # page 2 of size 2 is [2,1]
    assert [p["ats_id"] for p in items] == ["2", "1"]
    assert total == 5


def test_pagination_total_reflects_filters_not_just_the_page():
    engine = _engine()
    _insert(engine, "1", tier="A")
    _insert(engine, "2", tier="A")
    _insert(engine, "3", tier="B")

    items, total = _repo.list_postings(engine, {"tier": ["A"]}, page=1, size=1)

    assert len(items) == 1
    assert total == 2


def test_set_status_updates_matching_row():
    engine = _engine()
    _insert(engine, "1", source="lever", status="new")

    _repo.set_status(engine, "lever", "1", "applied")

    items, _ = _repo.list_postings(engine, {})
    assert items[0]["status"] == "applied"


def test_set_status_rejects_invalid_status():
    engine = _engine()
    _insert(engine, "1", source="lever", status="new")

    try:
        _repo.set_status(engine, "lever", "1", "not-a-real-status")
        assert False, "expected ValueError"
    except ValueError:
        pass

    items, _ = _repo.list_postings(engine, {})
    assert items[0]["status"] == "new"


def test_set_status_no_matching_row_is_a_silent_noop():
    engine = _engine()
    _insert(engine, "1", source="lever", status="new")

    _repo.set_status(engine, "greenhouse", "nonexistent", "applied")

    items, _ = _repo.list_postings(engine, {})
    assert items[0]["status"] == "new"
