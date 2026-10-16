import json
from decimal import Decimal

import pytest

from kopi_keys.rules import IncomeRuleError, check_all_schemes, check_income_ceiling, load_ceilings


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "ceilings.json"
    path.write_text(json.dumps({"schemes": {
        "grant_a": {"label": "Grant A", "ceiling": 9000, "inclusive": True,
                    "source_url": "https://example.test/a", "checked_on": "2026-10-15", "verified": True},
        "grant_b": {"label": "Grant B", "ceiling": 9000, "inclusive": False,
                    "source_url": "https://example.test/b", "checked_on": "2026-10-15", "verified": False},
        "grant_c": {"label": "Grant C", "ceiling": None, "inclusive": True,
                    "source_url": "https://example.test/c", "checked_on": "2026-10-15", "verified": True},
    }}))
    load_ceilings.cache_clear()
    return path


@pytest.mark.parametrize("income, within", [(8999, True), (9000, True), ("9000.01", False), (15000, False), (0, True)])
def test_inclusive_ceiling_boundary(config, income, within):
    assert check_income_ceiling("grant_a", income, config=config).within_ceiling is within


def test_exclusive_ceiling_excludes_the_exact_figure(config):
    assert not check_income_ceiling("grant_b", 9000, config=config).within_ceiling
    assert check_income_ceiling("grant_b", "8999.99", config=config).within_ceiling


@pytest.mark.parametrize("income, near", [(8600, True), (9400, True), (8500, False), (9500, False)])
def test_near_boundary_is_within_five_percent(config, income, near):
    assert check_income_ceiling("grant_a", income, config=config).near_boundary is near


def test_margin_and_no_ceiling(config):
    assert check_income_ceiling("grant_a", 9500, config=config).margin == Decimal("-500")
    no_cap = check_income_ceiling("grant_c", 50000, config=config)
    assert no_cap.within_ceiling and no_cap.ceiling is None and no_cap.margin is None


def test_messages_never_claim_eligibility_and_flag_unverified(config):
    for check in check_all_schemes(9000, config=config):
        assert "you are eligible" not in check.message.lower()
        assert "HFE" in check.message
    assert "not yet verified" in check_income_ceiling("grant_b", 1, config=config).message


@pytest.mark.parametrize("income", [-1, "abc", "nan", "inf", None])
def test_invalid_income_is_rejected(config, income):
    with pytest.raises(IncomeRuleError):
        check_income_ceiling("grant_a", income, config=config)


def test_unknown_scheme_is_rejected(config):
    with pytest.raises(IncomeRuleError, match="Known: grant_a"):
        check_income_ceiling("grant_z", 1000, config=config)


def test_shipped_config_is_complete():
    load_ceilings.cache_clear()
    schemes = load_ceilings()
    assert {"cpf_housing_grant_family", "enhanced_cpf_housing_grant_family"} <= schemes.keys()
    for scheme in schemes.values():
        assert scheme["source_url"].startswith("https://")
