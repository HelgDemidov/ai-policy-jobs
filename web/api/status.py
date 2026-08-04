"""POST /api/status — {"source": ..., "ats_id": ..., "status": ...} body.
Updates postings.status directly in Postgres via a plain transactional
UPDATE — no ETag/blob-swap machinery needed anymore (Postgres gives
atomicity for free; the old file-swap approach had to earn it manually,
see docs/tech_specs/web-postgres-migration/spec.md §4).
"""
import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

# See postings.py for why this is needed — Vercel's Python runtime doesn't
# put an api/*.py file's own directory on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _auth  # noqa: E402
import _repo  # noqa: E402
from _http import write_json  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if not _auth.is_authenticated(self.headers.get("Cookie")):
            write_json(self, 401, {"error": "unauthorized"})
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            write_json(self, 400, {"error": "invalid JSON body"})
            return

        source = payload.get("source")
        ats_id = payload.get("ats_id")
        new_status = payload.get("status")
        if not source or not ats_id or new_status not in _repo.STATUS_VALUES:
            write_json(self, 400, {"error": "source, ats_id, and a valid status are required"})
            return

        _repo.set_status(_repo.get_engine(), source, ats_id, new_status)

        write_json(self, 200, {"ok": True})
