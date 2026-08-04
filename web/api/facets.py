"""GET /api/facets — distinct tier/org values across all postings, used to
populate the filter widgets. Deliberately its own endpoint doing a
DISTINCT query rather than app.js fetching a "big enough" page of
/api/postings and deriving values client-side — that approach has an
inherent size ceiling that silently truncates once postings outgrows it
(live-caught 2026-08-04, see _repo.get_facets's docstring).
"""
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _auth  # noqa: E402
import _repo  # noqa: E402
from _http import write_json  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        engine = _repo.get_engine()
        if not _auth.is_authenticated(self.headers.get("Cookie"), engine):
            write_json(self, 401, {"error": "unauthorized"})
            return

        write_json(self, 200, _repo.get_facets(engine))
