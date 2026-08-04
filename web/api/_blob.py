"""Raw HTTP client for Vercel Blob, used by web/api/postings.py and
web/api/status.py. These run *inside* a deployed Vercel Python Function,
where the `vercel` CLI that scripts/blob_sync.py shells out to is not
available — this is the local-machine-vs-deployed-function split, not a
duplicate of blob_sync.py's job.

The write contract isn't in Vercel's public docs (spec's own research
confirmed this). Reverse-engineered from the official @vercel/blob SDK
source (github.com/vercel/storage, packages/blob/src/{put-helpers,
helpers}.ts: the x-* header names and the /api/blob control-plane URL) and
live-verified 2026-08-04 against the real ai-policy-jobs store:
- PUT without `x-api-version: 12` fails with a misleading "Invalid
  pathname" error rather than anything mentioning the missing header.
- Overwrite/if-match semantics confirmed with real 400 (no allow-overwrite,
  blob exists) / 412 (if-match mismatch) / 200 (correct if-match) responses.
"""
import os

import requests

BLOB_PATHNAME = "jobs.db"
# Stable for the lifetime of this one store (ai-policy-jobs' only Blob
# store) — confirmed via `vercel blob list`. Not derived from BLOB_STORE_ID
# because that mapping (lowercase, "store_" prefix stripped) isn't
# documented, just observed once; a literal beats an unverified pattern.
_STORE_BASE_URL = "https://tzxwwo2y42v4il6x.private.blob.vercel-storage.com"
_API_URL = "https://vercel.com/api/blob"


def _token() -> str:
    token = os.environ.get("BLOB_READ_WRITE_TOKEN")
    if not token:
        raise RuntimeError("BLOB_READ_WRITE_TOKEN not set in the function's environment")
    return token


def download() -> bytes:
    resp = requests.get(
        f"{_STORE_BASE_URL}/{BLOB_PATHNAME}",
        headers={"Authorization": f"Bearer {_token()}"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.content


def download_with_etag() -> tuple[bytes, str]:
    resp = requests.get(
        f"{_STORE_BASE_URL}/{BLOB_PATHNAME}",
        headers={"Authorization": f"Bearer {_token()}"},
        timeout=20,
    )
    resp.raise_for_status()
    etag = resp.headers["etag"]
    # GET responses through the CDN cache layer come back as a *weak*
    # validator (`W/"..."`, live-verified on jobs.db — likely because this
    # file is large enough to get gzip'd in transit). If-Match requires
    # strong comparison per RFC 7232 — a weak etag NEVER satisfies it, so
    # passing it straight through made every write fail with a 412/409
    # regardless of whether the content had actually changed. PUT's own
    # response etag came back strong with no prefix, confirming this is a
    # GET-path-only quirk, not something the write side needs to match.
    if etag.startswith("W/"):
        etag = etag[2:]
    return resp.content, etag


def upload(data: bytes, if_match: str) -> None:
    """Overwrite the jobs.db blob, but only if it still matches `if_match`
    (spec §3: guards against a race with a concurrent run.py sync — raises
    on a 412 so the caller can surface a clean "try again" to the client
    instead of silently clobbering a newer version)."""
    resp = requests.put(
        _API_URL,
        params={"pathname": BLOB_PATHNAME},
        headers={
            "Authorization": f"Bearer {_token()}",
            "x-api-version": "12",
            "x-vercel-blob-access": "private",
            "x-content-type": "application/octet-stream",
            "x-allow-overwrite": "1",
            "x-if-match": if_match,
        },
        data=data,
        timeout=20,
    )
    resp.raise_for_status()
