"""Tests for the connector orchestrator (scripts/run.py)."""
import yaml

import run
import store


def _posting(ats_id, **overrides):
    base = {
        "ats_id": ats_id,
        "title": "Role",
        "location": None,
        "workplace_type": None,
        "team": None,
        "commitment": None,
        "url": f"https://example.com/{ats_id}",
        "description": "",
        "posted_at": None,
    }
    base.update(overrides)
    return base


def test_orchestrates_multiple_orgs_and_upserts_each(tmp_path, monkeypatch):
    orgs_path = tmp_path / "orgs.yaml"
    orgs_path.write_text(
        yaml.safe_dump(
            [
                {"org": "Acme", "tier": "A", "ats": "lever", "slug": "acme"},
                {"org": "Beta", "tier": "B", "ats": "greenhouse", "slug": "beta"},
            ]
        )
    )
    db_path = tmp_path / "jobs.db"

    monkeypatch.setitem(run.CONNECTORS, "lever", lambda slug: [_posting("l1")])
    monkeypatch.setitem(run.CONNECTORS, "greenhouse", lambda slug: [_posting("g1")])

    run.main(orgs_path=orgs_path, db_path=db_path)

    conn = store.open_db(db_path)
    rows = conn.execute("SELECT org, ats_id FROM postings ORDER BY org").fetchall()
    assert rows == [("Acme", "l1"), ("Beta", "g1")]


def test_one_org_failure_does_not_stop_the_batch(tmp_path, monkeypatch, capsys):
    orgs_path = tmp_path / "orgs.yaml"
    orgs_path.write_text(
        yaml.safe_dump(
            [
                {"org": "Broken", "tier": "A", "ats": "lever", "slug": "broken"},
                {"org": "Fine", "tier": "B", "ats": "lever", "slug": "fine"},
            ]
        )
    )
    db_path = tmp_path / "jobs.db"

    def fake_lever_fetch(slug):
        if slug == "broken":
            raise RuntimeError("simulated network failure")
        return [_posting("ok1")]

    monkeypatch.setitem(run.CONNECTORS, "lever", fake_lever_fetch)

    run.main(orgs_path=orgs_path, db_path=db_path)

    conn = store.open_db(db_path)
    rows = conn.execute("SELECT org FROM postings").fetchall()
    assert rows == [("Fine",)]  # Broken's exception didn't stop Fine from being processed

    captured = capsys.readouterr()
    assert "Broken" in captured.out
    assert "failed" in captured.out
    assert "Fine: 1 open, 1 new" in captured.out


def test_rerunning_main_is_idempotent(tmp_path, monkeypatch):
    orgs_path = tmp_path / "orgs.yaml"
    orgs_path.write_text(
        yaml.safe_dump([{"org": "Acme", "tier": "A", "ats": "lever", "slug": "acme"}])
    )
    db_path = tmp_path / "jobs.db"
    monkeypatch.setitem(run.CONNECTORS, "lever", lambda slug: [_posting("l1")])

    run.main(orgs_path=orgs_path, db_path=db_path)
    run.main(orgs_path=orgs_path, db_path=db_path)

    conn = store.open_db(db_path)
    count = conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0]
    assert count == 1
