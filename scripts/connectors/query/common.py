"""Shared tier-derivation heuristic for connectors whose postings can't
carry one fixed tier per org (spec §4). Originally query-centric only;
also used by org-centric connectors covering a global board (e.g. UNDP's
oracle_fusion_hcm) where config/orgs.yaml deliberately leaves `tier` null
— see run.py's `_run_org_connectors`.

Deterministic by source/spec — never parses a posting's own free-text
location (unreliable, e.g. "London & San Francisco"), except where a
connector's location field is already a clean single duty-station/city
string (un_secretariat, recruitee, oracle_fusion_hcm). Errors here are
visible at a glance in the web GUI (missing/wrong tier chip) and aren't
fatal — good enough for this tool's scale.
"""
import re

ADZUNA_TIER_B_COUNTRIES = {
    "gb", "be", "de", "fr", "nl", "ch", "at", "it", "es",
    "ie", "se", "dk", "no", "fi", "pt", "lu",
}
ADZUNA_TIER_C_COUNTRIES = {"us"}

WESTERN_EUROPE_KEYWORDS = (
    "united kingdom", "uk", "germany", "france", "netherlands", "belgium",
    "switzerland", "austria", "italy", "spain", "ireland", "sweden",
    "denmark", "norway", "finland", "portugal", "luxembourg",
)
US_KEYWORDS = ("united states", "usa")

# UN Secretariat postings carry a duty-station city, not a country — mapped
# by hand for the common ones. Best-effort like the rest of this module;
# an unrecognized city returns None rather than guessing.
UN_DUTY_STATION_TIER_B_CITIES = {
    "geneva", "vienna", "rome", "the hague", "brussels", "paris", "madrid",
    "copenhagen", "berlin", "bonn",
}
UN_DUTY_STATION_TIER_C_CITIES = {"new york", "washington"}


def _matches_any(text: str, keywords: tuple[str, ...]) -> bool:
    """Word-boundary keyword match — plain substring search false-positives
    on short keywords inside unrelated place names (e.g. "uk" inside
    "Ukraine", "usa" inside "Lusaka" or "Jerusalem"; live-observed
    2026-08-21 backfilling UNDP's globally diverse locations)."""
    return any(re.search(rf"\b{re.escape(kw)}\b", text) for kw in keywords)


def derive_tier(source: str, spec: dict, posting: dict) -> str | None:
    if source == "adzuna":
        country = (spec.get("country") or "").lower()
        if country in ADZUNA_TIER_B_COUNTRIES:
            return "B"
        if country in ADZUNA_TIER_C_COUNTRIES:
            return "C"
        return None

    if source == "jobspy_linkedin":
        if posting.get("workplace_type") == "remote":
            return "A"
        location = (spec.get("location") or "").lower()
        if _matches_any(location, US_KEYWORDS):
            return "C"
        if _matches_any(location, WESTERN_EUROPE_KEYWORDS):
            return "B"
        return None

    if source == "un_secretariat":
        city = (posting.get("location") or "").strip().lower()
        if city in UN_DUTY_STATION_TIER_B_CITIES:
            return "B"
        if city in UN_DUTY_STATION_TIER_C_CITIES:
            return "C"
        return None

    if source == "recruitee":
        if posting.get("workplace_type") == "remote":
            return "A"
        location = (posting.get("location") or "").lower()
        if _matches_any(location, US_KEYWORDS):
            return "C"
        if _matches_any(location, WESTERN_EUROPE_KEYWORDS):
            return "B"
        return None

    if source == "oracle_fusion_hcm":
        # UNDP's global board (config/orgs.yaml leaves `tier` null — no
        # single fixed tier fits a worldwide requisition list). `location`
        # is a clean "City, Country" string (live-observed 2026-08-21), so
        # the same keyword match as recruitee/jobspy_linkedin applies.
        if (posting.get("workplace_type") or "").lower() == "remote":
            return "A"
        location = (posting.get("location") or "").lower()
        if _matches_any(location, US_KEYWORDS):
            return "C"
        if _matches_any(location, WESTERN_EUROPE_KEYWORDS):
            return "B"
        return None

    return None
