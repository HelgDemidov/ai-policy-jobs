"""GET /api/postings?tier=A&tier=B&org=...&hide_closed=true&remote_only=false&query=...
Thin Vercel handler — all filtering logic lives in _logic.list_postings.
"""
import sqlite3
import sys
import tempfile
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Vercel's Python runtime loads each api/*.py file as an isolated entrypoint
# module (importlib spec_from_file_location on that one file) — it does NOT
# put the file's own directory on sys.path, so bare `import _auth` etc.
# 404s with ModuleNotFoundError at cold start (live-verified 2026-08-04:
# reproduced locally with the same importlib call Vercel's loader uses).
# Same fix pattern as scripts/run.py and app/app.py's sys.path inserts.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _auth  # noqa: E402
import _blob  # noqa: E402
import _logic  # noqa: E402
from _http import write_json  # noqa: E402


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


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not _auth.is_authenticated(self.headers.get("Cookie")):
            write_json(self, 401, {"error": "unauthorized"})
            return

        filters = _parse_filters(parse_qs(urlparse(self.path).query))

        db_bytes = _blob.download()
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            f.write(db_bytes)
            tmp_path = Path(f.name)

        try:
            conn = sqlite3.connect(tmp_path)
            postings = _logic.list_postings(conn, filters)
            conn.close()
        finally:
            tmp_path.unlink(missing_ok=True)

        write_json(self, 200, postings)
