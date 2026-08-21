"""Deterministic relevance filter — a keyword-based gate applied between a
connector's fetch() and store.py's upsert, so topically irrelevant postings
never reach the database (docs/tech_specs/relevance-filtering/spec.md).

Known structural limit, accepted by design: matching on org+title can't tell
a policy role at a think tank apart from a same-titled corporate-compliance
role at an unrelated employer ("AI Governance Lead" at a real think tank vs
at an insurer) — that class of case needs org-identity knowledge this module
doesn't have, deferred to the LLM-based judgment in
docs/tech_specs/triage-and-autonomy/spec.md.
"""
from dataclasses import dataclass
from pathlib import Path

import yaml

FILTERS_PATH = Path(__file__).resolve().parent.parent / "config" / "filters.yaml"

_EMPTY_FILTERS: dict[str, list[str]] = {"org_blocklist": [], "title_require_any": [], "title_exclude_any": []}


@dataclass(frozen=True)
class FilterResult:
    passed: bool
    reason: str | None = None


def load_filters(path: Path = FILTERS_PATH) -> dict:
    """Same "missing config -> empty, not an error" idiom run.py already
    uses for searches.yaml — lets tests point at a deliberately nonexistent
    path to get a no-op (accept-everything) filter instead of coupling to
    the real repo config/filters.yaml."""
    if not path.exists():
        return dict(_EMPTY_FILTERS)
    data = yaml.safe_load(path.read_text()) or {}
    return {
        "org_blocklist": [str(s).lower() for s in data.get("org_blocklist") or []],
        "title_require_any": [str(s).lower() for s in data.get("title_require_any") or []],
        "title_exclude_any": [str(s).lower() for s in data.get("title_exclude_any") or []],
    }


def evaluate(org: str, title: str, filters: dict) -> FilterResult:
    """Pure judgment on one org+title pair — no I/O, no knowledge of which
    source it came from. Checked in order: org blocklist, then title
    must-contain-at-least-one, then title must-not-contain-any — the first
    failing condition determines `reason`. Matches only org+title, not
    description: some sources (jobspy_linkedin) never populate it, and
    consistency across sources matters more than the extra signal."""
    org_l = (org or "").lower()
    title_l = (title or "").lower()

    for blocked in filters["org_blocklist"]:
        if blocked in org_l:
            return FilterResult(False, f"org_blocklist: {blocked!r}")

    require = filters["title_require_any"]
    if require and not any(term in title_l for term in require):
        return FilterResult(False, "title_require_any: no match")

    for excluded in filters["title_exclude_any"]:
        if excluded in title_l:
            return FilterResult(False, f"title_exclude_any: {excluded!r}")

    return FilterResult(True)
