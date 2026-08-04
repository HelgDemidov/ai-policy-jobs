"""POST /api/status — {"source": ..., "ats_id": ..., "status": ...} body.
Updates postings.status and republishes the blob with an ETag-guarded write
(spec §3) so a concurrent run.py sync can't be silently clobbered.
"""
import json
import sqlite3
import tempfile
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import _auth
import _blob
import _logic
import requests
from _http import write_json


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
        if not source or not ats_id or new_status not in _logic.STATUS_VALUES:
            write_json(self, 400, {"error": "source, ats_id, and a valid status are required"})
            return

        db_bytes, etag = _blob.download_with_etag()
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            f.write(db_bytes)
            tmp_path = Path(f.name)

        try:
            conn = sqlite3.connect(tmp_path)
            _logic.set_status(conn, source, ats_id, new_status)
            conn.close()

            try:
                _blob.upload(tmp_path.read_bytes(), if_match=etag)
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 412:
                    write_json(self, 409, {"error": "jobs.db changed concurrently — try again"})
                    return
                raise
        finally:
            tmp_path.unlink(missing_ok=True)

        write_json(self, 200, {"ok": True})
