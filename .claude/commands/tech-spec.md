Turn a feature/change request into a structured spec at `docs/tech_specs/<slug>/spec.md`.

Take the task description from the user's message (and any command args) as the primary input. Everything below is a DEFAULT — an explicit instruction in that message overrides it.

Adapted from G2AI_ME's `/tech-spec`, stripped to what this repo actually has: no CI, no coverage gate, no PR flow, flat `docs/tech_specs/` (no functional blocks), `docs/` tracked rather than gitignored. A private GitHub remote (`github.com/HelgDemidov/ai-policy-job`) exists since 2026-08-04 purely as an off-machine backup — it does not add CI/Actions or a PR flow.

## Cross-cutting principle

The governing rule of this repo (`CLAUDE.md`): **не наращивать функционал просто потому что можем.** A personal tool for one job search, not a product. A spec that introduces a mechanism where a config line, an existing column, or an existing status value would do is a defective spec — fix it before finalizing. What you *rejected* matters as much as what you propose: `## Design rationale / отвергнутые альтернативы` is where this project's value accumulates (see the same habit in `docs/BACKLOG.md` → «Отклонено»).

Grounding — apply on every pass, not just the first:

- **Code.** Every path, function, column, CLI flag verified against the real repo by reading it. Never carried over from a similar-looking project or from memory of an earlier session.
- **Data.** This repo has a live `data/jobs.db`. Any quantitative claim — how noisy a source is, how many rows a change affects, how large an LLM payload would be — must be **measured** with `.venv/bin/python` + `sqlite3`, never estimated. Read-only queries only; a spec session must not write to it.
- **World.** Facts that move — Adzuna's free-tier quota, model pricing and API shape, a job board's query semantics, scheduler behavior — verify live before they enter the spec. Public read-only API probes are cheap and are this project's established habit (`docs/job-aggregator-landscape.md` is entirely built from them).
- **Idempotency and the two storage families.** `run.py` is safely re-runnable: a repeat run yields 0 new rows and only bumps `last_seen`. The ATS family reconciles missing postings to `likely_closed`; the search family must not (see the `store.py` module docstring for why). A spec touching either preserves that. It must also never make a *successful-but-empty* response indistinguishable from "everything closed".
- **Hermetic tests.** `tests/` must never touch the live `data/jobs.db` and never hit the network — and nothing enforces this structurally (`tests/conftest.py` holds only a Streamlit-cache fixture). Cleanliness rests on every test passing `tmp_path` explicitly and overriding `searches_path`. Recorded live trap: `run.main()` resolves `searches_path` to the real `searches.yaml` by default, so a test that forgets silently calls Himalayas/Adzuna/JobSpy on every `pytest` run. Any spec adding a code path states how its tests stay hermetic.

## Step 1 — Ground

Read the modules the spec will touch; `CLAUDE.md`; `docs/BACKLOG.md` (decision history and rejected options — many specs start life as a backlog item there); existing `docs/tech_specs/*/spec.md` for tone and structure. Measure against `data/jobs.db` wherever the spec makes a quantitative claim. Verify moving external facts live.

## Step 2 — Draft

Problem and goal, technical approach, affected files, test plan, commit breakdown.

## Step 3 — Adversarial pass (mandatory)

Re-read the draft as a skeptical reviewer, not its author. Hunt specifically for:

- claims that sound right but were never measured;
- a new mechanism where a config edit or existing field suffices;
- scope the user did not ask for;
- a commit plan whose steps are not independently shippable;
- anything that makes silent failure *more* likely once the work is automated.

If measurement contradicts the premise you started from, **say so in the spec** — a corrected premise is the most valuable output of this step, and burying it to keep the draft tidy is the failure mode to avoid. Genuine multi-way tradeoffs go to `## Открытые вопросы` rather than being decided silently.

Only the synthesized result goes in the file — never the round-by-round working.

## Step 4 — Assemble

Target 40–90 lines. Go longer only when the content earns it.

```
# Спек: <название>

Статус: черновик v1 · <дата>
Происхождение: <backlog item / прямой запрос куратора>

## 0. Что и зачем
<проблема, мотивация, одна строка про границу скоупа>

## 1..N. <технические разделы>
<конкретно, со ссылками на файлы и поля, без воды>

## Design rationale / отвергнутые альтернативы
<что рассматривали и почему отвергли — след шага 3, включая опровергнутые посылки>

## Тестовое покрытие
<новые тесты, по группе на коммит; как каждая остаётся герметичной>

## План коммитов
<нумерованный список, одна строка на коммит, с conventional-commit префиксом>

## Чек-лист реализации
<пустые чекбоксы, зеркалящие план коммитов>

## Открытые вопросы
<развилки, которые может решить только куратор — опустить, если нет>

## Вне скоупа
<явные исключения>
```

Status vocabulary — small and fixed, so a future session can tell built from planned at a glance:
`черновик v1` → `черновик v<N>` (после материальной ревизии) → `реализовано (<short-sha>..<short-sha>)`.

The final value is set by `/feature-workflow`, never here. Keep `## План коммитов`, `## Чек-лист реализации`, `## Открытые вопросы` and `## Вне скоупа` present and well-formed even when short — `/feature-workflow` consumes all four directly (plan to follow, boxes to tick, questions to resolve before coding, boundary not to cross).

Section headers stay in Russian, matching `CLAUDE.md` and the existing specs; only these instructions are English. Tone: terse, technical, file-referenced, no marketing language.

## Step 5 — Place and report

Write to `docs/tech_specs/<kebab-slug>/spec.md`. Slug derived from the feature itself — lowercase ASCII, no spaces — not a copy of the user's raw phrasing.

`docs/` is tracked in this repo, so the spec is a real file in git. **No feature branch by default**: no PR flow here (the GitHub remote is a private backup mirror, not a collaboration repo) — work lands on `master`. Do not commit unless the user asks.

If the spec grew out of a `docs/BACKLOG.md` item, add a pointer line back to it there.

Report the spec path and the single most important finding — especially any premise the grounding step overturned. Do not start implementation unless asked.
