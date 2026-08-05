"""POST /api/logout — bumps auth_state.epoch, invalidating every
outstanding session token globally (spec: web-auth-hardening §2), and
clears the gate cookie. Requires an already-valid cookie — otherwise an
anonymous POST could force-logout the curator with zero attempts, a worse
DoS than the login-lockout this project already accepts (spec §4).
"""
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
        engine = _repo.get_engine()
        if not _auth.is_authenticated(self.headers.get("Cookie"), engine):
            write_json(self, 401, {"error": "unauthorized"})
            return

        _auth.bump_epoch(engine)

        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.send_header(
            "Set-Cookie",
            f"{_auth.COOKIE_NAME}=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0",
        )
        self.end_headers()
        self.wfile.write(b'{"ok": true}')
