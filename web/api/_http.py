"""Tiny JSON-response helper shared by web/api/*.py handlers."""
import json


def write_json(handler, status: int, payload) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-type", "application/json")
    handler.end_headers()
    handler.wfile.write(body)
