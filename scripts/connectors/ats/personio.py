"""Personio ATS connector — public XML recruiting feed, no auth required.

Personio doesn't include a direct posting URL in the XML feed, but each
position's numeric id maps to a predictable job page: {slug}.jobs.personio.com
job/{id} (verified live against ECFR's board).
"""
import re
import xml.etree.ElementTree as ET

import requests

XML_API = "https://{slug}.jobs.personio.com/xml"
JOB_URL = "https://{slug}.jobs.personio.com/job/{job_id}"


def _strip_html(html: str) -> str:
    text = re.sub(r"<li>", "\n- ", html or "")
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def _text(position: ET.Element, tag: str) -> str | None:
    el = position.find(tag)
    return el.text.strip() if el is not None and el.text else None


def fetch(slug: str) -> list[dict]:
    resp = requests.get(XML_API.format(slug=slug), timeout=20)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    postings = []
    for position in root.findall("position"):
        job_id = _text(position, "id")
        if job_id is None:
            continue

        parts = []
        job_descriptions = position.find("jobDescriptions")
        if job_descriptions is not None:
            for jd in job_descriptions:
                name = _text(jd, "name") or ""
                value_el = jd.find("value")
                value = _strip_html(value_el.text) if value_el is not None and value_el.text else ""
                parts.append(f"{name}\n{value}")

        posted_at = _text(position, "createdAt")
        if posted_at:
            posted_at = posted_at[:10]  # ISO datetime -> date

        postings.append({
            "ats_id": job_id,
            "title": _text(position, "name"),
            "location": _text(position, "office"),
            "workplace_type": None,
            "team": _text(position, "department"),
            "commitment": _text(position, "schedule"),
            "url": JOB_URL.format(slug=slug, job_id=job_id),
            "description": "\n\n".join(parts).strip(),
            "posted_at": posted_at,
        })
    return postings
