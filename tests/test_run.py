"""Tests for the connector orchestrator (scripts/run.py)."""
import run
import store
import yaml


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


def _search_posting(ats_id, org, **overrides):
    base = _posting(ats_id, **overrides)
    base["org"] = org
    return base


def _no_searches_path(tmp_path):
    """A deliberately nonexistent searches.yaml — without this, tests that
    don't care about the search loop would fall back to the real
    searches.yaml at repo root and fire real network requests against
    Himalayas/Adzuna/JobSpy."""
    return tmp_path / "searches.yaml"


# --- ATS-family loop (unchanged behavior, searches loop is a no-op) --------


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

    run.main(orgs_path=orgs_path, db_path=db_path, searches_path=_no_searches_path(tmp_path))

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

    run.main(orgs_path=orgs_path, db_path=db_path, searches_path=_no_searches_path(tmp_path))

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

    run.main(orgs_path=orgs_path, db_path=db_path, searches_path=_no_searches_path(tmp_path))
    run.main(orgs_path=orgs_path, db_path=db_path, searches_path=_no_searches_path(tmp_path))

    conn = store.open_db(db_path)
    count = conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0]
    assert count == 1


# --- search-family loop -----------------------------------------------------


def _empty_orgs_path(tmp_path):
    path = tmp_path / "orgs.yaml"
    path.write_text("[]")
    return path


def test_search_specs_run_and_upsert_with_tier(tmp_path, monkeypatch):
    searches_path = tmp_path / "searches.yaml"
    searches_path.write_text(
        yaml.safe_dump([{"id": "hima-policy", "source": "himalayas", "query": "policy"}])
    )
    db_path = tmp_path / "jobs.db"

    monkeypatch.setitem(
        run.SEARCH_CONNECTORS, "himalayas",
        lambda spec: [_search_posting("h1", "R Street Institute", title="Policy Director")],
    )

    run.main(orgs_path=_empty_orgs_path(tmp_path), db_path=db_path, searches_path=searches_path)

    conn = store.open_db(db_path)
    row = conn.execute("SELECT org, title, tier, source FROM postings WHERE ats_id='h1'").fetchone()
    assert row == ("R Street Institute", "Policy Director", "A", "himalayas")  # himalayas -> tier A always


def test_search_spec_failure_does_not_stop_the_batch(tmp_path, monkeypatch, capsys):
    searches_path = tmp_path / "searches.yaml"
    searches_path.write_text(
        yaml.safe_dump(
            [
                {"id": "broken-search", "source": "himalayas", "query": "x"},
                {"id": "fine-search", "source": "adzuna", "phrase": "think tank", "country": "gb"},
            ]
        )
    )
    db_path = tmp_path / "jobs.db"

    monkeypatch.setitem(run.SEARCH_CONNECTORS, "himalayas", lambda spec: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setitem(
        run.SEARCH_CONNECTORS, "adzuna",
        lambda spec: [_search_posting("a1", "InfluenceMap", title="Analyst")],
    )

    run.main(orgs_path=_empty_orgs_path(tmp_path), db_path=db_path, searches_path=searches_path)

    conn = store.open_db(db_path)
    rows = conn.execute("SELECT org FROM postings").fetchall()
    assert rows == [("InfluenceMap",)]

    captured = capsys.readouterr()
    assert "broken-search" in captured.out
    assert "failed" in captured.out
    assert "fine-search: 1 found, 1 new" in captured.out


def test_manual_search_spec_skipped_without_linkedin_flag(tmp_path, monkeypatch, capsys):
    searches_path = tmp_path / "searches.yaml"
    searches_path.write_text(
        yaml.safe_dump([{"id": "li-search", "source": "jobspy_linkedin", "query": "x", "manual": True}])
    )
    db_path = tmp_path / "jobs.db"
    calls = []
    monkeypatch.setitem(run.SEARCH_CONNECTORS, "jobspy_linkedin", lambda spec: calls.append(spec) or [])

    run.main(orgs_path=_empty_orgs_path(tmp_path), db_path=db_path, searches_path=searches_path)

    assert calls == []  # connector never invoked
    captured = capsys.readouterr()
    assert "li-search: skipped (manual)" in captured.out


def test_manual_search_spec_runs_with_linkedin_flag(tmp_path, monkeypatch):
    searches_path = tmp_path / "searches.yaml"
    searches_path.write_text(
        yaml.safe_dump([{"id": "li-search", "source": "jobspy_linkedin", "query": "x", "manual": True}])
    )
    db_path = tmp_path / "jobs.db"
    monkeypatch.setitem(
        run.SEARCH_CONNECTORS, "jobspy_linkedin",
        lambda spec: [_search_posting("li1", "RAND Europe", title="Research Analyst")],
    )

    run.main(orgs_path=_empty_orgs_path(tmp_path), db_path=db_path, searches_path=searches_path, run_linkedin=True)

    conn = store.open_db(db_path)
    row = conn.execute("SELECT org FROM postings").fetchone()
    assert row == ("RAND Europe",)


def test_non_manual_search_specs_still_run_with_linkedin_flag(tmp_path, monkeypatch):
    """--linkedin adds manual specs on top of the default set — it doesn't
    replace it."""
    searches_path = tmp_path / "searches.yaml"
    searches_path.write_text(
        yaml.safe_dump([{"id": "hima-policy", "source": "himalayas", "query": "policy"}])
    )
    db_path = tmp_path / "jobs.db"
    monkeypatch.setitem(
        run.SEARCH_CONNECTORS, "himalayas",
        lambda spec: [_search_posting("h1", "Acme", title="Role")],
    )

    run.main(orgs_path=_empty_orgs_path(tmp_path), db_path=db_path, searches_path=searches_path, run_linkedin=True)

    conn = store.open_db(db_path)
    assert conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0] == 1


def test_search_loop_never_reconciles_missing_postings(tmp_path, monkeypatch):
    searches_path = tmp_path / "searches.yaml"
    searches_path.write_text(
        yaml.safe_dump([{"id": "hima-policy", "source": "himalayas", "query": "policy"}])
    )
    db_path = tmp_path / "jobs.db"
    monkeypatch.setitem(
        run.SEARCH_CONNECTORS, "himalayas",
        lambda spec: [_search_posting("h1", "Acme", title="Role")],
    )
    run.main(orgs_path=_empty_orgs_path(tmp_path), db_path=db_path, searches_path=searches_path)

    # Next run, the search comes back empty — unlike the ATS family, this
    # must NOT mark the posting likely_closed (see store.py docstring).
    monkeypatch.setitem(run.SEARCH_CONNECTORS, "himalayas", lambda spec: [])
    run.main(orgs_path=_empty_orgs_path(tmp_path), db_path=db_path, searches_path=searches_path)

    conn = store.open_db(db_path)
    status = conn.execute("SELECT status FROM postings WHERE ats_id='h1'").fetchone()[0]
    assert status == "new"


def test_expire_stale_runs_after_search_loop_and_is_scoped(tmp_path, monkeypatch):
    """expire_stale_search_postings must be scoped to search-family sources
    only — an old, still-'new' ATS posting must not be swept up by it."""
    orgs_path = tmp_path / "orgs.yaml"
    orgs_path.write_text(
        yaml.safe_dump([{"org": "Acme", "tier": "A", "ats": "lever", "slug": "acme"}])
    )
    db_path = tmp_path / "jobs.db"
    monkeypatch.setitem(run.CONNECTORS, "lever", lambda slug: [_posting("l1")])

    run.main(orgs_path=orgs_path, db_path=db_path, searches_path=_no_searches_path(tmp_path))

    from datetime import datetime, timedelta, timezone
    conn = store.open_db(db_path)
    old = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    conn.execute("UPDATE postings SET last_seen=? WHERE ats_id='l1'", (old,))
    conn.commit()
    conn.close()

    run.main(orgs_path=orgs_path, db_path=db_path, searches_path=_no_searches_path(tmp_path))

    conn = store.open_db(db_path)
    status = conn.execute("SELECT status FROM postings WHERE ats_id='l1'").fetchone()[0]
    assert status == "new"  # untouched — lever isn't a search-family source


# --- exit code (added for the daily systemd timer — see spec §3: a scheduler
# --- can't otherwise tell "everything broke" apart from "nothing new") ----


def test_main_returns_1_when_every_attempted_source_fails(tmp_path, monkeypatch):
    orgs_path = tmp_path / "orgs.yaml"
    orgs_path.write_text(
        yaml.safe_dump([{"org": "Broken", "tier": "A", "ats": "lever", "slug": "broken"}])
    )
    db_path = tmp_path / "jobs.db"
    monkeypatch.setitem(run.CONNECTORS, "lever", lambda slug: (_ for _ in ()).throw(RuntimeError("boom")))

    exit_code = run.main(orgs_path=orgs_path, db_path=db_path, searches_path=_no_searches_path(tmp_path))

    assert exit_code == 1


def test_main_returns_0_when_a_source_in_either_family_succeeds(tmp_path, monkeypatch):
    # The org connector fails outright, but a search connector succeeds.
    # Pins that "succeeded" is summed across BOTH families rather than
    # checked per-family — a plausible bug that would wrongly report failure
    # here even though real data landed this run.
    orgs_path = tmp_path / "orgs.yaml"
    orgs_path.write_text(
        yaml.safe_dump([{"org": "Broken", "tier": "A", "ats": "lever", "slug": "broken"}])
    )
    searches_path = tmp_path / "searches.yaml"
    searches_path.write_text(
        yaml.safe_dump([{"id": "hima-policy", "source": "himalayas", "query": "policy"}])
    )
    db_path = tmp_path / "jobs.db"
    monkeypatch.setitem(run.CONNECTORS, "lever", lambda slug: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setitem(
        run.SEARCH_CONNECTORS, "himalayas",
        lambda spec: [_search_posting("h1", "R Street Institute", title="Policy Director")],
    )

    exit_code = run.main(orgs_path=orgs_path, db_path=db_path, searches_path=searches_path)

    assert exit_code == 0


def test_main_returns_0_when_config_is_completely_empty(tmp_path):
    orgs_path = tmp_path / "orgs.yaml"
    orgs_path.write_text("[]")
    db_path = tmp_path / "jobs.db"

    exit_code = run.main(orgs_path=orgs_path, db_path=db_path, searches_path=_no_searches_path(tmp_path))

    assert exit_code == 0  # nothing attempted is not the same as everything failing


def test_main_returns_0_when_only_manual_specs_exist_and_are_skipped(tmp_path):
    # A manual-only searches.yaml without --linkedin is 0 attempted (all
    # skipped) — same "no signal" case as an empty config, not a failure.
    searches_path = tmp_path / "searches.yaml"
    searches_path.write_text(
        yaml.safe_dump([{"id": "li-search", "source": "jobspy_linkedin", "query": "x", "manual": True}])
    )
    db_path = tmp_path / "jobs.db"

    exit_code = run.main(orgs_path=_empty_orgs_path(tmp_path), db_path=db_path, searches_path=searches_path)

    assert exit_code == 0
