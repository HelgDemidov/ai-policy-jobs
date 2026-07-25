"""Tests for the tier-derivation heuristic (scripts/query_common.py)."""
import query_common


def test_himalayas_is_always_tier_a():
    assert query_common.derive_tier("himalayas", {}, {}) == "A"


def test_adzuna_western_europe_country_is_tier_b():
    assert query_common.derive_tier("adzuna", {"country": "gb"}, {}) == "B"
    assert query_common.derive_tier("adzuna", {"country": "be"}, {}) == "B"


def test_adzuna_us_is_tier_c():
    assert query_common.derive_tier("adzuna", {"country": "us"}, {}) == "C"


def test_adzuna_unknown_country_is_none():
    assert query_common.derive_tier("adzuna", {"country": "cn"}, {}) is None
    assert query_common.derive_tier("adzuna", {}, {}) is None


def test_jobspy_remote_posting_is_tier_a_regardless_of_spec_location():
    posting = {"workplace_type": "remote"}
    assert query_common.derive_tier("jobspy_linkedin", {"location": "United States"}, posting) == "A"
    assert query_common.derive_tier("jobspy_indeed", {}, posting) == "A"


def test_jobspy_non_remote_uses_spec_location_not_posting_location():
    posting = {"workplace_type": None, "location": "London & San Francisco"}  # unreliable free text
    assert query_common.derive_tier("jobspy_linkedin", {"location": "United Kingdom"}, posting) == "B"


def test_jobspy_us_location_is_tier_c():
    posting = {"workplace_type": None}
    assert query_common.derive_tier("jobspy_indeed", {"location": "United States"}, posting) == "C"


def test_jobspy_unknown_location_is_none():
    posting = {"workplace_type": None}
    assert query_common.derive_tier("jobspy_linkedin", {"location": "Japan"}, posting) is None
    assert query_common.derive_tier("jobspy_linkedin", {}, posting) is None


def test_unknown_source_is_none():
    assert query_common.derive_tier("some_future_source", {}, {}) is None
