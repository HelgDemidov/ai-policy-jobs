"""POST /api/login — {"password": ...} body. On success, issues a
revocable HMAC session token as the gate cookie (spec:
web-auth-hardening) — web/api/postings.py, status.py, and facets.py
check it per request via _auth.is_authenticated.
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
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            write_json(self, 400, {"error": "invalid JSON body"})
            return

        password = payload.get("password", "")
        engine = _repo.get_engine()

        if _auth.is_locked_out(engine):
            write_json(self, 429, {"error": "too many attempts, try again later"})
            return

        if not _auth.check_login(engine, password):
            write_json(self, 401, {"error": "wrong password"})
            return

        token = _auth.issue_token(engine)
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.send_header(
            "Set-Cookie",
            f"{_auth.COOKIE_NAME}={token}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age={_auth.MAX_AGE_SECONDS}",
        )
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
