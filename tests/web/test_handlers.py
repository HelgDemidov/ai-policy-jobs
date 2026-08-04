"""HTTP-integration tests for the Vercel handler classes themselves
(postings.py/status.py/login.py) — the layer nothing previously tested
directly (only _repo.py's/its predecessor _logic.py's pure functions were
unit-tested; query-string parsing, cookie auth, and JSON (de)serialization
were only ever checked by hand against the live site). Real HTTPServer
instances on loopback, tmp_path SQLite standing in for Postgres via
DATABASE_URL — no live network, no real Postgres, no live site touched
(docs/tech_specs/web-postgres-migration/spec.md §0bis, tier 2).
"""
import threading
from http.server import HTTPServer

import _repo
import _schema
import facets
import login
import postings
import pytest
import requests
import status
from sqlalchemy import create_engine

SITE_PASSWORD = "test-password-xyz"


@pytest.fixture
def live_servers(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SITE_PASSWORD", SITE_PASSWORD)
    # _repo.get_engine() caches a module-scope singleton (deliberately, for
    # a warm serverless instance) — reset it so each test gets an engine
    # bound to ITS OWN tmp_path db, not a previous test's.
    _repo._ENGINE = None

    engine = create_engine(db_url)
    _schema.metadata.create_all(engine)
    engine.dispose()

    servers, threads = [], []

    def _start(handler_cls):
        server = HTTPServer(("127.0.0.1", 0), handler_cls)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append(server)
        threads.append(thread)
        return f"http://127.0.0.1:{server.server_port}"

    urls = {
        "postings": _start(postings.handler),
        "status": _start(status.handler),
        "login": _start(login.handler),
        "facets": _start(facets.handler),
    }

    yield urls, engine

    for server in servers:
        server.shutdown()
    _repo._ENGINE = None


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


def _auth_cookie():
    return {"Cookie": f"site_auth={SITE_PASSWORD}"}


def test_postings_requires_auth(live_servers):
    urls, _ = live_servers
    resp = requests.get(urls["postings"])
    assert resp.status_code == 401


def test_postings_returns_paginated_shape(live_servers):
    urls, engine = live_servers
    _insert(engine, "1")
    _insert(engine, "2")

    resp = requests.get(urls["postings"], headers=_auth_cookie())

    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"items", "total", "page", "size"}
    assert body["total"] == 2
    assert body["page"] == 1
    assert len(body["items"]) == 2


def test_postings_applies_query_string_filters(live_servers):
    urls, engine = live_servers
    _insert(engine, "1", tier="A")
    _insert(engine, "2", tier="B")

    resp = requests.get(urls["postings"], headers=_auth_cookie(), params={"tier": "A"})

    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["ats_id"] == "1"


def test_postings_pagination_params_are_parsed(live_servers):
    urls, engine = live_servers
    for i in range(3):
        _insert(engine, str(i))

    resp = requests.get(urls["postings"], headers=_auth_cookie(), params={"page": "1", "size": "2"})

    body = resp.json()
    assert body["size"] == 2
    assert len(body["items"]) == 2
    assert body["total"] == 3


def test_postings_size_is_capped_at_max(live_servers):
    urls, _ = live_servers
    resp = requests.get(urls["postings"], headers=_auth_cookie(), params={"size": "99999"})
    assert resp.json()["size"] == postings.MAX_SIZE


def test_facets_requires_auth(live_servers):
    urls, _ = live_servers
    resp = requests.get(urls["facets"])
    assert resp.status_code == 401


def test_facets_returns_distinct_values_not_a_capped_page(live_servers):
    """The regression this endpoint exists to prevent: distinct org count
    must reflect ALL rows, not be truncated by postings.py's MAX_SIZE (a
    page-rendering safety valve, unrelated to this endpoint) or any other
    row-count ceiling — live-caught 2026-08-04 when a big-page-based
    approach silently dropped orgs past its cutoff."""
    urls, engine = live_servers
    for i in range(300):  # comfortably past postings.py's old, since-removed 200/2000 caps
        _insert(engine, str(i), tier="A", org=f"Org {i}")

    resp = requests.get(urls["facets"], headers=_auth_cookie())

    assert resp.status_code == 200
    body = resp.json()
    assert body["tiers"] == ["A"]
    assert len(body["orgs"]) == 300


def test_status_requires_auth(live_servers):
    urls, _ = live_servers
    resp = requests.post(urls["status"], json={"source": "lever", "ats_id": "1", "status": "applied"})
    assert resp.status_code == 401


def test_status_updates_and_is_visible_via_postings(live_servers):
    urls, engine = live_servers
    _insert(engine, "1", source="lever", status="new")

    resp = requests.post(
        urls["status"], headers=_auth_cookie(),
        json={"source": "lever", "ats_id": "1", "status": "applied"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    listed = requests.get(urls["postings"], headers=_auth_cookie()).json()
    assert listed["items"][0]["status"] == "applied"


def test_status_rejects_invalid_status_value(live_servers):
    urls, engine = live_servers
    _insert(engine, "1", source="lever", status="new")

    resp = requests.post(
        urls["status"], headers=_auth_cookie(),
        json={"source": "lever", "ats_id": "1", "status": "not-a-real-status"},
    )

    assert resp.status_code == 400
    listed = requests.get(urls["postings"], headers=_auth_cookie()).json()
    assert listed["items"][0]["status"] == "new"  # unchanged


def test_status_rejects_malformed_json_body(live_servers):
    urls, _ = live_servers
    resp = requests.post(
        urls["status"], headers={**_auth_cookie(), "Content-Type": "application/json"},
        data="not json",
    )
    assert resp.status_code == 400


def test_login_wrong_password_rejected(live_servers):
    urls, _ = live_servers
    resp = requests.post(urls["login"], json={"password": "wrong"})
    assert resp.status_code == 401


def test_login_correct_password_sets_cookie_that_authenticates(live_servers):
    """login.py's Set-Cookie carries `Secure`, so requests' cookie jar
    correctly refuses to resend it over this test server's plain HTTP
    (matching real browser behavior) — extracting the value directly to
    verify what actually matters here: that the *value* login.py issues is
    the one postings.py accepts, independent of transport security."""
    urls, engine = live_servers
    _insert(engine, "1")

    login_resp = requests.post(urls["login"], json={"password": SITE_PASSWORD})
    assert login_resp.status_code == 200
    assert login_resp.cookies["site_auth"] == SITE_PASSWORD

    postings_resp = requests.get(urls["postings"], headers={"Cookie": f"site_auth={login_resp.cookies['site_auth']}"})
    assert postings_resp.status_code == 200
    assert postings_resp.json()["total"] == 1
