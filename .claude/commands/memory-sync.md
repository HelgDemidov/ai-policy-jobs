Audit CLAUDE.md and project memory against live repo state, fix what's stale.

Adapted from scopus_search_code's `/memory-sync`, stripped to this repo's actual scale: a single `CLAUDE.md` (~45 lines), no `frontend/CLAUDE.md`, currently one memory file — no backup-rotation system, no multi-phase resumable worklist, no C1–C5 claim-taxonomy table. The core discipline carries over unchanged: code/git is truth, `CLAUDE.md` and memory are the patients, fix only what's provably stale, replace in place — never append a correction (see the `documentation-conventions` memory entry).

Run manually, periodically, or before a work session that will lean on memory being accurate. Audit only — do not add new facts (that's `/post-merge-sync`'s job) or restructure/restyle beyond factual fixes.

## 1. Sources of truth

Live code (`scripts/`, `app/`, `tests/`, `config/`), `git log`/`gh`, filesystem (path existence, directory layout). NOT truth — the patients: `CLAUDE.md`, memory files, `docs/`. Your context already holds `CLAUDE.md`/`MEMORY.md` from session start — treat both as unverified until checked against a fresh command.

## 2. Evidence discipline

Every fix needs two pieces of evidence: disproof of the old claim + confirmation of the new one (path, command output, git log). An absence claim ("no such file") needs two independent search phrasings, not one empty grep. If code confirms neither the old nor a new phrasing, mark unresolved rather than inventing one.

## 3. Edit rights

- `feedback` memory: the lesson/Why is untouchable; only fix dead anchors (paths, commands). Never delete a feedback entry — flag it, the curator decides.
- `project`/`reference` memory and `CLAUDE.md`: fix stale paths, commands, statuses freely; leave rationale/history alone unless it directly contradicts a later dated entry.
- `.claude/commands/*.md`: anchor audit only (dead paths) — never rewrite a command's actual protocol.

## 4. Execution

One pass, no phases needed at this scale: read `CLAUDE.md` top to bottom, verify every checkable claim (file exists at that path? command runs? dependency present?); then walk the memory directory the same way. Fix confirmed staleness in place. List anything ambiguous instead of guessing.

## 5. Wrap-up

Summarize in the reply: N claims checked, M fixed with evidence pairs, anything flagged unresolved. Show the `CLAUDE.md` diff. On confirmation, commit only `CLAUDE.md` (`docs: memory-sync — fix N stale claims`) — memory is never committed, `docs/tech_specs/` is out of scope here (that's `/feature-workflow`'s domain).

## 6. Out of scope

Adding new facts, restructuring `CLAUDE.md`, editing code/tests/`docs/`, verifying external references (`docs/job-aggregator-landscape/notes.md` etc.).
