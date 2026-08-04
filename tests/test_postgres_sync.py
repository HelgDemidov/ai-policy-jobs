"""Tests for scripts/postgres_sync.py. `pg_engine` fixtures below are
SQLite (in-memory, via _schema.py's portable metadata) standing in for
Postgres — postgres_sync.py's functions use plain select/insert/update,
not Postgres-specific ON CONFLICT syntax, precisely so this substitution
is valid (see the module's own docstring). Never touches the live
data/jobs.db or the network.
"""
import _schema
import postgres_sync
import store
import yaml
from sqlalchemy import create_engine, select


def _pg_engine():
    engine = create_engine("sqlite:///:memory:")
    _schema.metadata.create_all(engine)
    return engine


def _local_conn(tmp_path):
    return store.open_db(tmp_path / "jobs.db")


def _write_yaml(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(yaml.dump(content))
    return path


def test_sync_organizations_upserts_curated_and_adds_discovered_stubs(tmp_path):
    pg = _pg_engine()
    conn = _local_conn(tmp_path)
    store.upsert_postings(conn, "Curated Org", "A", "lever", [
        {"ats_id": "1", "title": "Role", "location": None, "workplace_type": None,
         "team": None, "commitment": None, "url": "https://x/1", "description": None,
         "posted_at": None},
    ])
    store.upsert_search_postings(conn, "himalayas", [
        {"org": "Discovered Org", "tier": "B", "ats_id": "https://x/2", "title": "Role 2",
         "location": None, "workplace_type": None, "team": None, "commitment": None,
         "url": "https://x/2", "description": None, "posted_at": None},
    ])
    orgs_yaml = _write_yaml(tmp_path, "orgs.yaml", [
        {"org": "Curated Org", "tier": "A", "ats": "lever", "slug": "curated-org"},
    ])

    postgres_sync.sync_organizations(pg, orgs_yaml, conn)

    with pg.connect() as pgconn:
        rows = {r.name: r for r in pgconn.execute(select(_schema.organizations))}

    assert rows["Curated Org"].origin == "curated"
    assert rows["Curated Org"].tier == "A"
    assert rows["Curated Org"].slug == "curated-org"
    assert rows["Discovered Org"].origin == "discovered"
    assert rows["Discovered Org"].tier is None


def test_sync_organizations_curated_never_overwritten_by_discovered(tmp_path):
    """A discovered stub must never clobber a curated row that happens to
    share a name — curated always wins, regardless of sync order."""
    pg = _pg_engine()
    conn = _local_conn(tmp_path)
    store.upsert_postings(conn, "Same Name Org", "A", "lever", [
        {"ats_id": "1", "title": "Role", "location": None, "workplace_type": None,
         "team": None, "commitment": None, "url": "https://x/1", "description": None,
         "posted_at": None},
    ])
    orgs_yaml = _write_yaml(tmp_path, "orgs.yaml", [
        {"org": "Same Name Org", "tier": "A", "ats": "lever", "slug": "same-name-org"},
    ])

    postgres_sync.sync_organizations(pg, orgs_yaml, conn)
    postgres_sync.sync_organizations(pg, orgs_yaml, conn)  # repeat run

    with pg.connect() as pgconn:
        rows = pgconn.execute(select(_schema.organizations)).all()

    assert len(rows) == 1
    assert rows[0].origin == "curated"
    assert rows[0].slug == "same-name-org"


def test_sync_searches_full_mirror_replaces_previous_content(tmp_path):
    pg = _pg_engine()
    searches_yaml = _write_yaml(tmp_path, "searches.yaml", [
        {"id": "spec-a", "source": "himalayas", "query": "policy"},
    ])
    postgres_sync.sync_searches(pg, searches_yaml)

    searches_yaml_v2 = _write_yaml(tmp_path, "searches.yaml", [
        {"id": "spec-b", "source": "adzuna", "phrase": "think tank", "country": "gb"},
    ])
    postgres_sync.sync_searches(pg, searches_yaml_v2)

    with pg.connect() as pgconn:
        rows = pgconn.execute(select(_schema.searches)).all()

    assert len(rows) == 1
    assert rows[0].search_id == "spec-b"
    assert rows[0].query_text == "think tank"
    assert rows[0].location == "gb"
    assert rows[0].raw["id"] == "spec-b"


def test_mirror_to_postgres_replaces_all_rows_and_resolves_org_id(tmp_path):
    pg = _pg_engine()
    conn = _local_conn(tmp_path)
    store.upsert_postings(conn, "Org A", "A", "lever", [
        {"ats_id": "1", "title": "Role", "location": None, "workplace_type": None,
         "team": None, "commitment": None, "url": "https://x/1", "description": None,
         "posted_at": None},
    ])
    orgs_yaml = _write_yaml(tmp_path, "orgs.yaml", [{"org": "Org A", "tier": "A", "ats": "lever"}])
    postgres_sync.sync_organizations(pg, orgs_yaml, conn)

    postgres_sync.mirror_to_postgres(pg, conn)

    with pg.connect() as pgconn:
        rows = pgconn.execute(select(_schema.postings)).all()
        org_id = pgconn.execute(
            select(_schema.organizations.c.id).where(_schema.organizations.c.name == "Org A")
        ).scalar_one()

    assert len(rows) == 1
    assert rows[0].org == "Org A"
    assert rows[0].org_id == org_id


def test_mirror_to_postgres_second_run_reflects_status_changes(tmp_path):
    pg = _pg_engine()
    conn = _local_conn(tmp_path)
    store.upsert_postings(conn, "Org A", "A", "lever", [
        {"ats_id": "1", "title": "Role", "location": None, "workplace_type": None,
         "team": None, "commitment": None, "url": "https://x/1", "description": None,
         "posted_at": None},
    ])
    postgres_sync.mirror_to_postgres(pg, conn)

    conn.execute("UPDATE postings SET status = 'applied' WHERE ats_id = '1'")
    conn.commit()
    postgres_sync.mirror_to_postgres(pg, conn)

    with pg.connect() as pgconn:
        rows = pgconn.execute(select(_schema.postings)).all()

    assert len(rows) == 1
    assert rows[0].status == "applied"


def test_mirror_to_postgres_refuses_to_wipe_when_local_is_empty_but_postgres_is_not(tmp_path):
    pg = _pg_engine()
    conn = _local_conn(tmp_path)
    store.upsert_postings(conn, "Org A", "A", "lever", [
        {"ats_id": "1", "title": "Role", "location": None, "workplace_type": None,
         "team": None, "commitment": None, "url": "https://x/1", "description": None,
         "posted_at": None},
    ])
    postgres_sync.mirror_to_postgres(pg, conn)  # Postgres now has 1 row

    conn.execute("DELETE FROM postings")  # simulate a bug: local table now empty
    conn.commit()

    try:
        postgres_sync.mirror_to_postgres(pg, conn)
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass

    with pg.connect() as pgconn:
        rows = pgconn.execute(select(_schema.postings)).all()
    assert len(rows) == 1  # untouched, not wiped


def test_pull_statuses_updates_local_from_postgres(tmp_path):
    pg = _pg_engine()
    conn = _local_conn(tmp_path)
    store.upsert_postings(conn, "Org A", "A", "lever", [
        {"ats_id": "1", "title": "Role", "location": None, "workplace_type": None,
         "team": None, "commitment": None, "url": "https://x/1", "description": None,
         "posted_at": None},
    ])
    postgres_sync.mirror_to_postgres(pg, conn)

    with pg.begin() as pgconn:
        pgconn.execute(
            _schema.postings.update()
            .where(_schema.postings.c.source == "lever", _schema.postings.c.ats_id == "1")
            .values(status="applied")
        )

    postgres_sync.pull_statuses(pg, conn)

    row = conn.execute("SELECT status FROM postings WHERE ats_id = '1'").fetchone()
    assert row[0] == "applied"
