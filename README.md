# AI Policy Jobs

A personal job-search tracker for Emerging Tech / AI Policy Analyst roles at
think tanks and international-org research units. Not a product — a
single-purpose tool: relevant openings rarely surface on general job boards,
and checking dozens of career pages by hand doesn't scale.

**Live**: https://ai-policy-jobs.vercel.app (password-gated card view)

## How it works

Two families of source connectors feed one SQLite database, orchestrated by
a daily `scripts/run.py` run (systemd timer):

- **Org-centric** — known organizations polled directly against their ATS:
  Lever, Greenhouse, Personio.
- **Query-centric** — search-term-driven aggregators that surface orgs not
  already on the shortlist: Himalayas, Adzuna, JobSpy (LinkedIn/Indeed).

`store.py` handles dedup/reconciliation; `postgres_sync.py` mirrors the
result into Neon Postgres for the web GUI.

## Stack

Python (connectors, orchestration, tests) · SQLite → Postgres (SQLAlchemy
Core, Alembic) · Vercel-hosted GUI (Python Functions + vanilla JS, no build
step) · GitHub Actions CI (`ruff`, `mypy`, `pytest`).

## Status

Actively used, still evolving — see `docs/user_guides/cli_reference.md`.
