"""Shared-secret cookie gate (spec §4). Vercel Password Protection needs a
paid plan on Hobby, so this is the minimal app-level substitute: one env
var, one HttpOnly cookie carrying that same value, checked on every
request. Not a session token/hash scheme — deliberately as small as the
spec calls for ("не новый сервис, ~20 строк") for a single-curator tool.
"""
import os

COOKIE_NAME = "site_auth"


def _secret() -> str:
    secret = os.environ.get("SITE_PASSWORD")
    if not secret:
        raise RuntimeError("SITE_PASSWORD not set in the function's environment")
    return secret


def check_password(password: str) -> bool:
    return password == _secret()


def is_authenticated(cookie_header: str | None) -> bool:
    if not cookie_header:
        return False
    for part in cookie_header.split(";"):
        name, _, value = part.strip().partition("=")
        if name == COOKIE_NAME:
            return value == _secret()
    return False
