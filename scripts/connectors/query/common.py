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

# UN Secretariat postings carry a duty-station city, not a country — mapped
# by hand for the common ones. Best-effort like the rest of this module;
# an unrecognized city returns None rather than guessing.
UN_DUTY_STATION_TIER_B_CITIES = {
    "geneva", "vienna", "rome", "the hague", "brussels", "paris", "madrid",
    "copenhagen", "berlin", "bonn",
}
UN_DUTY_STATION_TIER_C_CITIES = {"new york", "washington"}


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
        if any(kw in location for kw in US_KEYWORDS):
            return "C"
        if any(kw in location for kw in WESTERN_EUROPE_KEYWORDS):
            return "B"
        return None

    return None
