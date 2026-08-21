"""Shared tier-derivation heuristic for query-centric connectors (spec §4).

Deterministic by source/spec — never parses a posting's own free-text
location (unreliable, e.g. "London & San Francisco"). Errors here are
visible at a glance in the Streamlit cards (missing/wrong tier chip) and
aren't fatal — good enough for this tool's scale.
"""

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
        if any(kw in location for kw in US_KEYWORDS):
            return "C"
        if any(kw in location for kw in WESTERN_EUROPE_KEYWORDS):
            return "B"
        return None

    return None
