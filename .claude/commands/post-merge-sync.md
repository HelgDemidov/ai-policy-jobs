Sync CLAUDE.md and project memory after merging a PR (Dependabot or otherwise) into master.

Adapted from scopus_search_code's `/post-merge-sync`, stripped to what this repo actually has: no `frontend/CLAUDE.md` (no frontend), no `docs/` append step (`docs/` here is tracked, not gitignored — `/feature-workflow` already closes specs itself, this command never touches `docs/tech_specs/`), no CI branch-trigger cleanup (`tests.yml` triggers on a static `push: branches: [master]` + `pull_request`, not a growing per-branch list scopus adds to), no README (none exists here).

Run `git log master --oneline -10` and `git diff HEAD~1 --stat` to see what the merge actually changed.

## Step 1 — Update CLAUDE.md

Read the current `CLAUDE.md`. Update ONLY sections factually outdated because of the merge: new top-level files/directories, changed run commands, new dependencies, new CI/config. Follow the `documentation-conventions` memory rule — English, dry, replace-don't-append; never leave a note about what used to be there.

Do not add implementation detail or micropatterns — architectural/infra facts only.

## Step 2 — Update or create memory

Read `MEMORY.md`. For each merge with a lasting consequence (not just a version bump), decide:
- New durable fact about the project → `project_*.md`
- Process/tooling lesson learned → `feedback_*.md`
- New external resource → `reference_*.md`

A routine Dependabot bump with no behavioral change needs neither — most merges are a no-op for this step.

## Step 3 — Commit

Stage only `CLAUDE.md` (memory lives outside git, never committed). Skip entirely if nothing changed.

`git commit -m "docs: sync CLAUDE.md after merging <branch/PR>"`

Report what was updated, or that nothing needed it.
