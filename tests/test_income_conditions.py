"""Added 2026-10-17: the ceiling variants in rules/income_ceilings.json are HDB's own
wording. Each condition must appear verbatim on the cited page in the ACTIVE snapshot."""
import json
from pathlib import Path

from kopi_keys.rules import check_income_ceiling

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "backend/kopi_keys/rules/income_ceilings.json").read_text(encoding="utf-8"))
SNAPSHOT = ROOT / "data/policy_snapshots" / (ROOT / "data/policy_snapshots/ACTIVE").read_text(encoding="utf-8").strip()
PAGES = {
    "cpf_housing_grant_family": "hdb-grant-family-cpf-housing-grants.md",
    "cpf_housing_grant_single": "hdb-grant-singles-cpf-housing-grant.md",
    "enhanced_cpf_housing_grant_family": "hdb-grant-family-ehg.md",
    "enhanced_cpf_housing_grant_single": "hdb-grant-singles-ehg.md",
}


def test_every_condition_is_verbatim_on_its_hdb_page():
    for scheme, rule in CONFIG["schemes"].items():
        for condition in rule.get("conditions", []):
            page = (SNAPSHOT / "clean" / PAGES[scheme]).read_text(encoding="utf-8")
            assert condition in page, (scheme, condition)


def test_conditions_reach_the_check_and_its_message():
    check = check_income_ceiling("cpf_housing_grant_family", 20000)
    assert not check.within_ceiling
    assert any("$24,000" in c for c in check.conditions)
    assert "Different ceilings apply in some situations" in check.message
