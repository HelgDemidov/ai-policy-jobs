"""GET /api/postings?tier=A&tier=B&org=...&hide_closed=true&remote_only=false&query=...&page=1&size=60
Thin Vercel handler — all filtering/pagination logic lives in
_repo.list_postings (docs/tech_specs/web-postgres-migration/spec.md §4).
"""
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Vercel's Python runtime loads each api/*.py file as an isolated entrypoint
# module (importlib spec_from_file_location on that one file) — it does NOT
# put the file's own directory on sys.path, so bare `import _auth` etc.
# 404s with ModuleNotFoundError at cold start (live-verified 2026-08-04:
# reproduced locally with the same importlib call Vercel's loader uses).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _auth  # noqa: E402
import _repo  # noqa: E402
from _http import write_json  # noqa: E402

DEFAULT_SIZE = 60
MAX_SIZE = 200


def _parse_filters(query: dict) -> dict:
    filters = {}
    if "tier" in query:
        filters["tier"] = query["tier"]
    if "org" in query:
        filters["org"] = query["org"]
    # hide_closed defaults true, remote_only defaults false — matches
    # app.py's checkbox defaults (app.py:377,379) for GUI parity.
    filters["hide_closed"] = query.get("hide_closed", ["true"])[0].lower() == "true"
    filters["remote_only"] = query.get("remote_only", ["false"])[0].lower() == "true"
    filters["query"] = query.get("query", [""])[0]
    return filters


def _parse_pagination(query: dict) -> tuple[int, int]:
    try:
        page = max(1, int(query.get("page", ["1"])[0]))
    except ValueError:
        page = 1
    try:
        size = int(query.get("size", [str(DEFAULT_SIZE)])[0])
    except ValueError:
        size = DEFAULT_SIZE
    return page, max(1, min(size, MAX_SIZE))


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not _auth.is_authenticated(self.headers.get("Cookie")):
            write_json(self, 401, {"error": "unauthorized"})
            return

        query = parse_qs(urlparse(self.path).query)
        filters = _parse_filters(query)
        page, size = _parse_pagination(query)

        items, total = _repo.list_postings(_repo.get_engine(), filters, page=page, size=size)

        write_json(self, 200, {"items": items, "total": total, "page": page, "size": size})
