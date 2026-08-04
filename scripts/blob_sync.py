"""Sync data/jobs.db to/from Vercel Blob via the `vercel` CLI (subprocess).

The raw Blob HTTP PUT contract isn't publicly documented (checked) — the CLI
gives the same result in a specified way, and is needed locally for
`vercel deploy` anyway (docs/tech_specs/vercel-web-gui/spec.md §3), so this
isn't a new dependency.

Only BLOB_READ_WRITE_TOKEN goes into the subprocess env, never the whole
process env verbatim: live-verified 2026-08-04 that the CLI treats
BLOB_STORE_ID being set (without a matching VERCEL_OIDC_TOKEN) as a request
to authenticate via OIDC instead of the read-write token, and errors out —
`.env` in this repo sets both, so blindly inheriting it breaks the call.
"""
import os
import subprocess
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
BLOB_PATHNAME = "jobs.db"


def _load_token() -> str:
    """Minimal KEY=VALUE .env reader for BLOB_READ_WRITE_TOKEN — same
    pattern as connectors/query/adzuna.py's _load_env_credentials. Real
    environment variables win over the .env file."""
    token = os.environ.get("BLOB_READ_WRITE_TOKEN")
    if token:
        return token

    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key.strip() == "BLOB_READ_WRITE_TOKEN":
                return value.strip()

    raise RuntimeError(
        "BLOB_READ_WRITE_TOKEN not set — see docs/tech_specs/vercel-web-gui/spec.md §1"
    )


def _run(args: list[str]) -> None:
    env = dict(os.environ)
    env["BLOB_READ_WRITE_TOKEN"] = _load_token()
    env.pop("BLOB_STORE_ID", None)
    result = subprocess.run(
        ["vercel", "blob", *args], env=env, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"vercel blob {' '.join(args)} failed: {result.stderr}")


def download(dest: Path) -> None:
    """Fetch the current jobs.db blob to `dest`, overwriting it."""
    _run(["get", BLOB_PATHNAME, "--access", "private", "-o", str(dest)])


def upload(src: Path) -> None:
    """Push `src` to the jobs.db blob, overwriting the existing one in place
    (stable pathname — allowOverwrite=true, addRandomSuffix=false, so the
    blob URL never changes across syncs)."""
    _run([
        "put", str(src),
        "--access", "private",
        "--pathname", BLOB_PATHNAME,
        "--allow-overwrite", "true",
        "--add-random-suffix", "false",
    ])
