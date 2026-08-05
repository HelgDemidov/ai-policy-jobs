Implement an approved-but-not-yet-built spec (`docs/tech_specs/<slug>/spec.md`) end-to-end, commit by commit.

Direct continuation of `/tech-spec`: that command produces the plan, this one executes it. Invoke as `/feature-workflow [slug | path]`.

Adapted from G2AI_ME's `/feature-workflow`, restructured around the fact that in this repo the spec **already carries its own commit plan and checklist** — so this command follows a plan rather than inventing one. Also stripped: the coverage measurement — none of that exists here. Feature branches + `gh pr create` and `ruff`/`mypy` gates DO now exist in this repo (added 2026-08-05 and by an earlier repo-hygiene tooling upgrade, respectively) — see Step 3 and Step 4.

## Seam with `/tech-spec` — what is guaranteed and consumed

| `/tech-spec` produces | this command does with it |
|---|---|
| `docs/tech_specs/<slug>/spec.md` | Step 1 scans for it |
| `Статус: черновик v<N>` | Step 1 selects on it; Step 7 replaces it |
| `## Открытые вопросы` (deliberately unresolved) | Step 2 resolves them **before** any code |
| `## План коммитов` (numbered, prefixed) | Step 3 follows it — does **not** reinvent it |
| `## Чек-лист реализации` (unchecked) | Step 4 ticks each box in the commit that completes it |
| `## Вне скоупа` | hard boundary — do not build what is listed there |

`/tech-spec` deliberately does not commit anything. **Invoking this command is the authorization to commit**; the two are consistent, not contradictory.

## Step 1 — Find the target spec

With an argument (slug or path), use it directly. Otherwise scan `docs/tech_specs/*/spec.md` and select those still at `Статус: черновик v<N>`. `реализовано (<sha>..<sha>)` means done — skip.

- Zero → report nothing is pending, stop.
- One → proceed.
- Several → ask which (AskUserQuestion), never guess.

Cross-check against reality before building: if the code already does what the spec describes, report it as already implemented and fix the stale status line instead of re-implementing.

## Step 2 — Resolve the open questions first

`## Открытые вопросы` exists because `/tech-spec` refused to guess on a fork only the curator can settle. Ask them (AskUserQuestion), write the answers into the relevant sections, and bump the status `черновик v<N>` → `черновик v<N+1>`.

Do not start building with open questions outstanding — in this project they routinely change the design, not just a constant.

## Step 3 — Confirm the plan, pick where it lands

The commit plan is already in the spec. Re-read it against the current code (it was written earlier; the repo may have moved) and present only the **deltas** for approval — not the whole plan again. If Step 2's answers invalidate a planned commit, say so now rather than discovering it mid-build.

**Branch: always a feature branch, unconditionally (curator's 2026-08-05 decision).** Create `feature/<slug>` off `main` before Step 4's first commit; every commit in this workflow lands there, never directly on `main`. This holds regardless of how small the spec turns out to be — the size-based main-vs-branch split documented in `CLAUDE.md` governs other work, not `/feature-workflow`, which always branches and opens a PR at the end (Step 7).

## Step 4 — Implement, commit by commit

One logical change per commit; never batch unrelated work. Conventional-commit prefixes consistent with the existing history (`feat(store):`, `feat(connectors):`, `feat(run):`, `docs:`, `chore:`).

**The gate is `.venv/bin/ruff check .` + `.venv/bin/pytest`** — both are what CI's `test` job actually runs (`.github/workflows/tests.yml`), since the repo-hygiene tooling upgrade added `ruff`/`mypy` (`requirements-dev.txt`, config in `pyproject.toml`). CI does not run `mypy` as a gate, but it's cheap to check locally too (`.venv/bin/mypy web/api scripts app`) — do so before pushing, since a type error caught locally is faster than one caught on review. Do not slip in a *new* tool (black, a coverage threshold) as part of a feature commit — that is its own decision, subject to `CLAUDE.md`'s «не наращивать функционал»; ruff/mypy are not new, they're the existing gate.

- While iterating: the touched test file only, e.g. `.venv/bin/pytest tests/test_store.py`.
- Before every commit: `.venv/bin/ruff check .` and the full test suite. Skipping `ruff` locally means finding out from a red CI check on the PR instead — strictly slower, not faster.

**Tick the `## Чек-лист реализации` box in the same commit that completes the item.** `docs/` is tracked in this repo (unlike G2AI, where the spec was gitignored), so the checklist is part of history — keeping it current per-commit makes every point in the log honest, instead of a single cosmetic sweep at the end.

## Step 5 — Hermeticity check (repo-specific, do not skip)

Test hermeticity here is a **convention, not a guard**: `tests/conftest.py` contains only a Streamlit-cache-clearing fixture. Nothing structurally prevents a test from opening the live `data/jobs.db` or calling a real API. The suite stays clean because every test passes `tmp_path` explicitly and overrides `searches_path` — a new test that forgets either will silently write to production data or hammer Himalayas/Adzuna/JobSpy on every `pytest` run. This has happened once already (recorded in `docs/backlog/BACKLOG.md`).

So measure around the suite whenever a commit adds tests:

```bash
q='SELECT COUNT(*) FROM postings'
before=$(.venv/bin/python -c "import sqlite3;print(sqlite3.connect('data/jobs.db').execute('$q').fetchone()[0])")
.venv/bin/pytest -q
after=$(.venv/bin/python -c "import sqlite3;print(sqlite3.connect('data/jobs.db').execute('$q').fetchone()[0])")
[ "$before" = "$after" ] && echo "герметично: $before" || echo "НАРУШЕНО: $before -> $after"
```

A mismatch means a new test is writing to the live database — fix it before committing, do not rationalize it.

## Step 6 — Verify behavior, not just tests

Green tests are necessary, not sufficient. But in this repo a real run **mutates production state and can cost money**, so verification is a deliberate, announced step — never a casual one, and never "run the suite twice".

- **`run.py`** hits live APIs and writes to `data/jobs.db`. Record row count and status distribution before and after, confirm the delta matches what the spec predicted, and confirm a second consecutive run is a no-op (0 new, only `last_seen` bumped) — that idempotency is a load-bearing invariant.
- **`triage.py`** and anything else calling a paid API: state the expected cost from the spec's own estimate *before* running, then compare the actual against it and record the result.
- **`app/app.py`**: `.venv/bin/streamlit run app/app.py` on `localhost:8501` and look at it, or `AppTest` when the change is logic-only.
- Anything touching reconciliation: confirm a successful-but-empty response does not mass-archive an organization (`store.py` guard).

## Step 7 — Close the spec

Once every planned commit has landed:

1. Full `.venv/bin/ruff check .` and `.venv/bin/pytest` one final time; report the count. CI (`.github/workflows/tests.yml`) runs the same `ruff check` gate on the PR — catch it here, not on a red check after pushing.
2. Status line → `реализовано (<first-sha>..<last-sha>)`, every checklist box ticked, the commit plan annotated with the actual short hashes.
3. **Add `## Что разошлось с планом`** — renamed helpers, a design fork resolved differently once real code appeared, a decision reversed mid-flight, a predicted consequence that actually materialized. This is what tells a future session the spec was a plan rather than a transcript. Omit only when genuinely nothing diverged.
4. Update `docs/backlog/BACKLOG.md`: status of the originating item plus a pointer to the spec; and `CLAUDE.md` if the spec changed how the tool is run.
5. Commit the closure as `docs: ...`.

Push the feature branch to `origin` and open a PR with `gh pr create` (title from the spec's name; body summarizing what shipped, pointing at the spec's `## Что разошлось с планом`). Do not merge it — curator reviews and merges. Report: commits landed, final test result, what diverged from the plan, what the spec explicitly left out of scope, and the PR URL.
