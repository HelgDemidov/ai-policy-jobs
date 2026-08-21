# scripts/browser — headless-browser resolver (Lightpanda + Puppeteer)

Used by `scripts/connectors/ats/icims.py` (and any future connector that hits
a WAF-protected board) via `scripts/browser_resolver.py`. Ported from the
sibling G2AI_ME repo's `pipeline/browser/` — same tool, ported not
reinvented; rationale/benchmarks in that repo's
`docs/pipeline/core/tech_specs/headless-browser-resolver/spec.md`.

## What's tracked / what's not

- `package.json` — tracked (Node dependency manifest).
- `node_modules/` — gitignored (`node_modules/` is already repo-wide gitignored), install with `npm ci`/`npm install`.
- `lightpanda` — ~120 MB binary, gitignored, downloaded separately.

## Setup (fresh clone)

```bash
# 1. Node driver (puppeteer-core, WITHOUT bundled Chromium)
cd scripts/browser && PUPPETEER_SKIP_DOWNLOAD=1 npm install

# 2. Lightpanda engine (nightly, single Linux x86_64 binary)
curl -L -o lightpanda \
  https://github.com/lightpanda-io/browser/releases/download/nightly/lightpanda-x86_64-linux
chmod +x lightpanda
```

Requires Node >= 20. `scripts/browser_resolver.is_available()` checks for
both and lets calling code degrade (skip that org, log the failure) if
either is missing — the daily cron run doesn't hard-fail over this.

## Notes

- `lightpanda` is `1.0.0-nightly` — a pre-seed startup's engine, not a
  stable release. Pin the working binary if it starts misbehaving; the
  resolver sits behind a narrow interface (`resolve()`/`is_available()`),
  so swapping engine or driver later is localized.
- Verified live 2026-08-21 against CFR's iCIMS board: plain `requests` gets
  an AWS WAF "Human Verification" CAPTCHA page; Lightpanda renders the real
  listing.
