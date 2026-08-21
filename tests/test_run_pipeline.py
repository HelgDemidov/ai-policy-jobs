"""End-to-end integration test for the full run.py -> postgres_sync chain —
the biggest single risk in the Postgres migration (spec §0bis: "does
everything wired in run.py.__main__ actually work together"), not
otherwise covered by any per-function unit test.

Connectors are mocked the same way tests/test_run.py already does
(monkeypatch.setitem on run.CONNECTORS/SEARCH_CONNECTORS) — this file
doesn't re-test run.main()'s own orchestration (already covered there);
it tests the SEAM between main()'s SQLite output and postgres_sync's
functions consuming it. `pg_engine` is SQLite standing in for Postgres,
same as tests/test_postgres_sync.py — ensure_schema()/Alembic itself
(Postgres-only past migration 0002's raw SQL) is exercised for real only
in tests/integration/test_migrations.py, not here.
"""
import _schema
import postgres_sync
import run
import store
import yaml
from sqlalchemy import create_engine, select


def _pg_engine():
    engine = create_engine("sqlite:///:memory:")
    _schema.metadata.create_all(engine)
    return engine


def _posting(ats_id, **overrides):
    base = {
        "ats_id": ats_id, "title": "Role", "location": None, "workplace_type": None,
        "team": None, "commitment": None, "url": f"https://example.com/{ats_id}",
        "description": "", "posted_at": None,
    }
    base.update(overrides)
    return base


def _run_full_pipeline(pg_engine, orgs_path, searches_path, db_path):
    conn = store.open_db(db_path)
    postgres_sync.pull_statuses(pg_engine, conn)
    conn.close()

    # Deliberately nonexistent filters.yaml, same idiom as test_run.py's
    # _no_filters_path — otherwise these tests' placeholder titles ("Role")
    # would be evaluated against the real production config/filters.yaml.
    filters_path = db_path.parent / "filters.yaml"
    exit_code = run.main(orgs_path=orgs_path, db_path=db_path, searches_path=searches_path, filters_path=filters_path)

    conn = store.open_db(db_path)
    postgres_sync.sync_organizations(pg_engine, orgs_path, conn)
    postgres_sync.sync_searches(pg_engine, searches_path)
    postgres_sync.mirror_to_postgres(pg_engine, conn)
    conn.close()
    return exit_code


def test_full_pipeline_populates_all_three_postgres_tables(tmp_path, monkeypatch):
    pg = _pg_engine()
    orgs_path = tmp_path / "orgs.yaml"
    orgs_path.write_text(yaml.safe_dump([{"org": "Acme", "tier": "A", "ats": "lever", "slug": "acme"}]))
    searches_path = tmp_path / "searches.yaml"
    searches_path.write_text(
        yaml.safe_dump([{"id": "adzuna-check", "source": "adzuna", "phrase": "policy", "country": "gb"}])
    )
    db_path = tmp_path / "jobs.db"

    monkeypatch.setitem(run.CONNECTORS, "lever", lambda slug: [_posting("l1")])
    monkeypatch.setitem(
        run.SEARCH_CONNECTORS, "adzuna",
        lambda spec: [dict(_posting("h1", title="Policy Role"), org="R Street Institute")],
    )

    exit_code = _run_full_pipeline(pg, orgs_path, searches_path, db_path)

    assert exit_code == 0
    with pg.connect() as conn:
        orgs = {r.name: r.origin for r in conn.execute(select(_schema.organizations))}
        postings = conn.execute(select(_schema.postings)).all()
        searches = conn.execute(select(_schema.searches)).all()

    assert orgs == {"Acme": "curated", "R Street Institute": "discovered"}
    assert {p.ats_id for p in postings} == {"l1", "h1"}
    assert all(p.org_id is not None for p in postings)  # every posting's org resolved
    assert [s.search_id for s in searches] == ["adzuna-check"]


def test_full_pipeline_second_run_is_idempotent(tmp_path, monkeypatch):
    pg = _pg_engine()
    orgs_path = tmp_path / "orgs.yaml"
    orgs_path.write_text(yaml.safe_dump([{"org": "Acme", "tier": "A", "ats": "lever", "slug": "acme"}]))
    searches_path = tmp_path / "searches.yaml"
    searches_path.write_text("[]")
    db_path = tmp_path / "jobs.db"
    monkeypatch.setitem(run.CONNECTORS, "lever", lambda slug: [_posting("l1")])

    _run_full_pipeline(pg, orgs_path, searches_path, db_path)
    _run_full_pipeline(pg, orgs_path, searches_path, db_path)

    with pg.connect() as conn:
        postings = conn.execute(select(_schema.postings)).all()
        orgs = conn.execute(select(_schema.organizations)).all()

    assert len(postings) == 1  # not duplicated
    assert len(orgs) == 1


def test_full_pipeline_preserves_status_edit_made_via_postgres_across_a_rerun(tmp_path, monkeypatch):
    """The property blob_sync.download()/upload() used to guarantee: a
    status set through the web GUI (here: written directly to the
    Postgres stand-in, simulating that) must survive the next run.py
    cycle, not get reset to 'new' by the connector re-upserting the same
    posting. This is pull_statuses' entire reason to exist."""
    pg = _pg_engine()
    orgs_path = tmp_path / "orgs.yaml"
    orgs_path.write_text(yaml.safe_dump([{"org": "Acme", "tier": "A", "ats": "lever", "slug": "acme"}]))
    searches_path = tmp_path / "searches.yaml"
    searches_path.write_text("[]")
    db_path = tmp_path / "jobs.db"
    monkeypatch.setitem(run.CONNECTORS, "lever", lambda slug: [_posting("l1")])

    _run_full_pipeline(pg, orgs_path, searches_path, db_path)  # posting lands as 'new'

    with pg.begin() as conn:
        conn.execute(
            _schema.postings.update()
            .where(_schema.postings.c.source == "lever", _schema.postings.c.ats_id == "l1")
            .values(status="applied")
        )

    # Same connector, same posting, still returned "open" on the next run —
    # without pull_statuses this would get re-upserted and stay 'new'.
    _run_full_pipeline(pg, orgs_path, searches_path, db_path)

    with pg.connect() as conn:
        status = conn.execute(
            select(_schema.postings.c.status).where(_schema.postings.c.ats_id == "l1")
        ).scalar_one()
    assert status == "applied"
