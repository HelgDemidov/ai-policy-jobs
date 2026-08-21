"""WordPress REST API connector — for orgs whose career page is a custom
post type on a self-hosted WordPress site (WP core's REST API is the same
shape regardless of which plugin registered the post type — WP Job
Manager's `job-listings` and a bespoke `job-opportunity` type both work
through this one connector, live-verified 2026-08-21 on UN Global Pulse
and Atlantic Council respectively).

Different fetch() signature (site url + post type, not a slug) — same
"explicit branch in run.py" reasoning as html_scrape.py: the params are
genuinely two independent pieces, not worth encoding into one string.
"""
import re

import requests

LIST_API = "{site_url}/wp-json/wp/v2/{post_type}"
PER_PAGE = 100


def _strip_html(html: str) -> str:
    text = re.sub(r"<li>", "\n- ", html or "")
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def fetch(site_url: str, post_type: str) -> list[dict]:
    postings = []
    page = 1
    while True:
        resp = requests.get(
            LIST_API.format(site_url=site_url.rstrip("/"), post_type=post_type),
            params={"per_page": PER_PAGE, "page": page},
            timeout=20,
        )
        if resp.status_code == 400:  # WP returns 400 "invalid page number" past the last page
            break
        resp.raise_for_status()
        posts = resp.json()
        if not posts:
            break
        for post in posts:
            title = (post.get("title") or {}).get("rendered", "")
            content = (post.get("content") or {}).get("rendered", "")
            postings.append({
                "ats_id": str(post["id"]),
                "title": _strip_html(title),
                "location": None,
                "workplace_type": None,
                "team": None,
                "commitment": None,
                "url": post.get("link"),
                "description": _strip_html(content),
                "posted_at": (post.get("date") or "")[:10] or None,
            })
        page += 1
    return postings
