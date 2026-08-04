# Job Search — Emerging Tech / AI Policy Analyst

Independent track, originally split out of the `side-hustle-job` worktree in another repo (G2AI_ME); has lived here standalone since 2026-07-24. Unrelated to G2AI in content — but the curator's background (AI governance for small states, international regulation) is directly relevant to the roles targeted.

**Principle: don't grow functionality just because we can.** A personal tool for one specific task, not a product or an enterprise system. Any development proposal (mine or the curator's) gets checked against real necessity, not "would be neat/polished" — see `docs/backlog/BACKLOG.md`, "Development recommendations" section, where this is applied in practice.

## What and why

Targeting an **Emerging Tech / AI Policy Analyst** position (analyst → director range, PM optional) at think tanks and international-org research units focused on policy/governance/global security/strategic stability around emerging tech and AI (NOT technical standardization).

Geo priority: **Tier A** (remote / Montenegro-Serbia) > **Tier B** (Western Europe) > **Tier C** (US/Japan, strong matches only). Out of scope: China, Russia, Middle East, Eastern Europe.

Curator's citizenship — Russian, ~4 years emigrated with no plans to return (stated openly in applications) — adds an extra filter specifically for Tier C (details and methodology in `docs/backlog/BACKLOG.md`).

Employment: full-time preferred, part-time also fine. Languages: fluent English and Russian, no others needed.

## Where things live

- **`docs/backlog/BACKLOG.md`** — status by tier, filtering methodology, plan, decision history and rejected options. Read here for detail, not this file.
- **`docs/ats-aggregator-sweep/notes.md`** — track 1: ATS-platform sweep (Lever/Greenhouse/Personio) for shortlist orgs.
- **`docs/job-aggregator-landscape/notes.md`** — knowledge update on query-centric job aggregators (JobSpy, RemoteOK, Himalayas, Adzuna) — shift from org-centric to query-centric approach.
- **`artifacts/think-tank-shortlist.html`** — canonical org shortlist artifact (also published as a Claude Artifact — republish with the same `url` on update, to avoid minting new links).
- **`docs/tech_specs/query-connectors/spec.md`** — spec for query-centric connectors (Himalayas/Adzuna/JobSpy), a second family complementing org-centric ATS. Status: implemented.
- **`docs/tech_specs/triage-and-autonomy/spec.md`** — spec for LLM relevance triage, run reliability, and unattended scheduling. Status: run reliability + scheduling (systemd timer, 00:00 UTC) implemented 2026-07-26; LLM relevance triage remains a draft.
- **`docs/tech_specs/postings-schema-hardening/spec.md`** — spec for `postings` schema robustness: two-layer input validation (connector boundary + `store.py` backstop against `sqlite3.IntegrityError`), STRICT + `CHECK(status)` migration, cross-source `dedup_key` symmetry between the ATS and search storage families. Status: implemented 2026-08-04.
- **`docs/tech_specs/vercel-web-gui/spec.md`** — spec for a hosted card-view GUI on Vercel, replacing local Streamlit. Status: infra live (Vercel project `ai-policy-jobs`, Blob store, env vars — see spec §3/§4), application code not yet built.
- **`.claude/commands/`** — custom commands, working as pairs: **`/tech-spec`** turns a request into a spec following the `docs/tech_specs/<slug>/spec.md` convention (commit plan, checklist, open questions, out of scope) and commits nothing; **`/feature-workflow`** is its direct continuation — picks up a spec at `черновик v<N>`, resolves open questions first, then executes the commit plan commit by commit and finally flips status to `реализовано (<sha>..<sha>)`.
- **`config/orgs.yaml`** (org-centric: known org → ATS) + **`config/searches.yaml`** (query-centric: search term → orgs/postings from the data) + **`scripts/`** — the job-monitoring tool → local SQLite (`data/jobs.db`, gitignored). `scripts/run.py` (orchestrator) and `scripts/store.py` (persistence) stay at the top level — `run.py` is the systemd `ExecStart` target (`docs/user_guides/cli_reference.md`), moving it would touch a live unit outside git. The six source connectors live under `scripts/connectors/{ats,query}/`, split along the same ATS/query-centric line as `config/`. Run: **`.venv/bin/python scripts/run.py`** (NOT bare `python3` — system Python lacks `python-jobspy`/`pandas`). Since 2026-07-25 one run covers every source including LinkedIn; the `--linkedin` flag stays in the code but no spec is marked `manual: true` anymore, so it's currently a no-op.
- **`app/app.py`** + **`.streamlit/config.toml`** — card-view web UI for browsing postings (Streamlit, shares the repo's single `.venv/`), deliberately kept separate from `scripts/` (ingestion) — same split the future `web/` GUI (`docs/tech_specs/vercel-web-gui/spec.md`) will follow: one ingestion tool, multiple independent UIs reading its output. Run: `.venv/bin/streamlit run app/app.py`.
- **`tests/`** — pytest, hermetic (never touches live `data/jobs.db`), mirrors `scripts/`'s layout (`tests/connectors/{ats,query}/`). Run: `.venv/bin/pytest`.
- **Tooling** — `ruff`/`mypy` (config in `pyproject.toml`, deps in `requirements-dev.txt`) for `scripts/`+`app/`; `eslint` (flat config `eslint.config.js`, deps in `package.json`) scoped to the not-yet-built `web/public/**/*.js`. `uv` (already on the machine) is the local venv/install tool — see `docs/user_guides/cli_reference.md`, "Окружение". `requirements.txt`/`requirements-dev.txt` stay the dependency source of truth (both CI and Dependabot's `pip` ecosystem read them); `uv` installs from them, it doesn't replace them.
- **`docs/user_guides/cli_reference.md`** — short command cheat sheet for manual operation (venv/tooling bootstrap, Streamlit UI address, direct DB access, config format).
- **`.github/`** — CI (`workflows/tests.yml`, runs `ruff check` + `tests/` on push/PR to `main`) + `dependabot.yml` (pip + npm + github-actions, weekly). No branch protection — GitHub Pro is required for that on a private personal-account repo.
- **GitHub** — private mirror at `github.com/HelgDemidov/ai-policy-jobs` (set up 2026-08-04, renamed 2026-08-04 to match the Vercel project, purely an off-machine backup). No PR flow — work still lands directly on `main`, pushed to `origin` manually or at the end of `/feature-workflow`.
