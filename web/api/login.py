"""POST /api/login — {"password": ...} body. Sets the HttpOnly gate cookie
on success (spec §4); web/api/postings.py and status.py check it per request.
"""
import json
from http.server import BaseHTTPRequestHandler

import _auth
from _http import write_json

# 30 days — a personal single-curator tool, not worth re-prompting often.
_MAX_AGE = 60 * 60 * 24 * 30


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            write_json(self, 400, {"error": "invalid JSON body"})
            return

        password = payload.get("password", "")
        if not _auth.check_password(password):
            write_json(self, 401, {"error": "wrong password"})
            return

        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.send_header(
            "Set-Cookie",
            f"{_auth.COOKIE_NAME}={password}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age={_MAX_AGE}",
        )
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
