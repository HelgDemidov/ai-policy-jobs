"""Tests for scripts/relevance_filter.py — see
docs/tech_specs/relevance-filtering/spec.md for the design rationale."""
import relevance_filter


def _filters(**overrides):
    base = {"org_blocklist": [], "title_require_any": [], "title_exclude_any": []}
    base.update(overrides)
    return base


def test_org_blocklist_rejects_regardless_of_title():
    filters = _filters(org_blocklist=["acme staffing"])
    result = relevance_filter.evaluate("Acme Staffing Inc", "Senior Policy Analyst", filters)
    assert result.passed is False
    assert "org_blocklist" in result.reason


def test_org_blocklist_is_case_insensitive():
    filters = _filters(org_blocklist=["acme staffing"])
    result = relevance_filter.evaluate("ACME STAFFING INC", "Policy Analyst", filters)
    assert result.passed is False


def test_title_missing_require_term_is_rejected():
    filters = _filters(title_require_any=["policy", "governance"])
    result = relevance_filter.evaluate("Think Tank", "Office Manager", filters)
    assert result.passed is False
    assert "title_require_any" in result.reason


def test_title_with_require_term_and_no_exclude_term_passes():
    filters = _filters(title_require_any=["policy"], title_exclude_any=["intern"])
    result = relevance_filter.evaluate("Think Tank", "Senior Policy Analyst", filters)
    assert result.passed is True
    assert result.reason is None


def test_title_exclude_term_rejects_even_with_require_term_present():
    filters = _filters(title_require_any=["policy"], title_exclude_any=["intern"])
    result = relevance_filter.evaluate("Think Tank", "Policy Intern", filters)
    assert result.passed is False
    assert "title_exclude_any" in result.reason


def test_no_require_list_means_no_positive_requirement():
    filters = _filters(title_require_any=[])
    result = relevance_filter.evaluate("Think Tank", "Anything At All", filters)
    assert result.passed is True


def test_load_filters_missing_file_returns_empty_permissive_config(tmp_path):
    filters = relevance_filter.load_filters(tmp_path / "does-not-exist.yaml")
    assert filters == {"org_blocklist": [], "title_require_any": [], "title_exclude_any": []}


def test_load_filters_lowercases_everything(tmp_path):
    path = tmp_path / "filters.yaml"
    path.write_text("org_blocklist: [ACME]\ntitle_require_any: [POLICY]\ntitle_exclude_any: [INTERN]\n")
    filters = relevance_filter.load_filters(path)
    assert filters == {
        "org_blocklist": ["acme"],
        "title_require_any": ["policy"],
        "title_exclude_any": ["intern"],
    }


def test_load_filters_handles_empty_yaml_file(tmp_path):
    path = tmp_path / "filters.yaml"
    path.write_text("")
    filters = relevance_filter.load_filters(path)
    assert filters == {"org_blocklist": [], "title_require_any": [], "title_exclude_any": []}


# --- known-gap regression case (2026-08-21 diagnosis) -----------------------
# Documents the filter's known blind spot deliberately, not a hidden bug: a
# corporate AI-governance role at an unrelated employer matches the same
# require-list term as a real think-tank role with an identical title.
# Resolving this needs org-identity knowledge the keyword filter doesn't
# have — see docs/tech_specs/triage-and-autonomy/spec.md.


def test_known_gap_generic_corporate_title_with_no_exclude_hit_still_passes():
    filters = _filters(title_require_any=["governance"], title_exclude_any=["compliance"])
    result = relevance_filter.evaluate("Progressive Leasing", "AI Governance Lead", filters)
    assert result.passed is True  # known gap, not desired behavior


# --- live-calibration regression cases (first backfill run, 2026-08-21) ----
# config/filters.yaml's real org_blocklist/title_exclude_any additions,
# pinned against the actual filters they were added for.


def test_calibration_org_blocklist_catches_recruitment_agencies():
    filters = relevance_filter.load_filters()
    result = relevance_filter.evaluate("Harnham - Data & Analytics Recruitment", "Research Manager", filters)
    assert result.passed is False


def test_calibration_title_exclude_catches_medicaid():
    filters = relevance_filter.load_filters()
    result = relevance_filter.evaluate("BerryDunn", "Medicaid Policy Director", filters)
    assert result.passed is False


# --- second calibration round (2026-08-21, post Himalayas/jobspy_indeed
# --- removal) — wrong policy *domain*, not wrong institution ---------------


def test_calibration_org_blocklist_catches_non_target_orgs():
    filters = relevance_filter.load_filters()
    for org in ("Consultancy.uk", "The Health Foundation", "Lewisham Council", "Youth Employment UK"):
        result = relevance_filter.evaluate(org, "Policy Officer", filters)
        assert result.passed is False, org


def test_calibration_title_exclude_catches_wrong_domain_terms():
    filters = relevance_filter.load_filters()
    cases = [
        ("Bevan Foundation", "Head of Policy (Poverty)"),
        ("FTI Consulting", "Senior Consultant, Energy & Natural Resources"),
        ("Historic England", "Policy Adviser - Devolution, Housing and Investment"),
        ("BioCatch", "Fraud Intelligence Research Analyst"),
        ("Mondrian Alpha", "Equity Research Analyst - Hedge Fund"),
    ]
    for org, title in cases:
        result = relevance_filter.evaluate(org, title, filters)
        assert result.passed is False, f"{org} / {title}"
