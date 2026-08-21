"""Headless-browser resolver: Puppeteer-core (Node) drives the Lightpanda
engine over CDP, returns one page's rendered HTML. Bypasses AWS WAF's JS
challenge (verified live 2026-08-21 against CFR's iCIMS board — plain
`requests` gets a "Human Verification" CAPTCHA page, Lightpanda gets the
real listing) — see docs/tech_specs/point-source-connectors/spec.md §1.

Ported from the sibling G2AI_ME repo's `core/browser_resolver.py`
(`docs/pipeline/core/tech_specs/headless-browser-resolver/spec.md` there),
adapted: paths for this repo's flat `scripts/` layout instead of `core/`,
and `frame_url_contains` added — iCIMS renders its actual job list inside a
child iframe, not the top-level document (the parent's own G2AI targets
never needed sub-frame access).

Subprocess bridge to a Node script (`scripts/browser/resolve.mjs`) — same
pattern as any external-binary dependency: the logic doesn't move into
Python. Requires Node >=20 + `puppeteer-core` (`scripts/browser/node_modules`)
+ the `lightpanda` binary (`scripts/browser/`) — both gitignored, install
instructions in `scripts/browser/README.md`. `is_available()` lets calling
code degrade gracefully without them.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

BROWSER_DIR = Path(__file__).resolve().parent / "browser"
LIGHTPANDA_BINARY = BROWSER_DIR / "lightpanda"
RESOLVE_SCRIPT = BROWSER_DIR / "resolve.mjs"

DEFAULT_WAIT_MS = 9000
DEFAULT_TIMEOUT_S = 45  # headroom over wait_ms + goto timeout + lightpanda start/stop (see resolve.mjs)


class BrowserResolverUnavailable(RuntimeError):
    """Tooling failure: Node/lightpanda not installed, resolve.mjs crashed,
    hung, or returned non-JSON. Does NOT mean "the page returned a WAF
    block" — that's a different, meaningful outcome (`BrowserResult(ok=False,
    ...)`), which calling code treats as an ordinary failure, not as the
    tool being unavailable.
    """


@dataclass
class BrowserResult:
    ok: bool
    html: str
    final_url: str
    error: str


def is_available() -> bool:
    """Cheap environment check (no process spawn): Node on PATH and the
    lightpanda binary on disk. `node_modules`/`puppeteer-core` isn't checked
    separately — its absence will surface as a clear error on first resolve,
    which is diagnostic enough without a second stat call per call site."""
    return shutil.which("node") is not None and LIGHTPANDA_BINARY.exists()


def resolve(
    url: str,
    *,
    wait_ms: int = DEFAULT_WAIT_MS,
    timeout: int = DEFAULT_TIMEOUT_S,
    frame_url_contains: str | None = None,
) -> BrowserResult:
    """Render `url` via Lightpanda through Puppeteer-core, return its HTML.

    `frame_url_contains`, if given, returns the content of the first child
    frame whose URL contains that substring instead of the top-level
    document — needed for platforms (iCIMS) that only populate a nested
    iframe, not the outer page.

    Raises `BrowserResolverUnavailable` if Node/lightpanda aren't installed
    (cheaper to check via `is_available()` up front than catch this per URL
    in a batch) — or if the Node process itself didn't respond/crashed/
    returned invalid JSON in time. A meaningful page-level failure (WAF still
    blocked it, Lightpanda's own navigation timeout) comes back as an
    ordinary return value (`BrowserResult(ok=False, error=...)`), not an
    exception.
    """
    if not is_available():
        raise BrowserResolverUnavailable("Node and/or scripts/browser/lightpanda not found")
    args = ["node", str(RESOLVE_SCRIPT), url, str(wait_ms)]
    if frame_url_contains:
        args.append(frame_url_contains)
    try:
        proc = subprocess.run(
            args, cwd=BROWSER_DIR, capture_output=True, text=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise BrowserResolverUnavailable(f"resolve.mjs didn't respond within {timeout}s") from exc
    if proc.returncode != 0:
        raise BrowserResolverUnavailable(f"resolve.mjs exited {proc.returncode}: {proc.stderr[:300]}")
    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise BrowserResolverUnavailable(f"resolve.mjs returned invalid JSON: {proc.stdout[:300]}") from exc
    if payload.get("ok"):
        return BrowserResult(ok=True, html=payload.get("html", ""), final_url=payload.get("url", url), error="")
    return BrowserResult(ok=False, html="", final_url=url, error=str(payload.get("error", "unknown")))
