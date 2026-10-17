"""Income ceiling boundary checks for resale grants: pure Python, no model calls.

Ceilings live in ``income_ceilings.json`` with their source and dates, never in
this code. A check only compares income with a published ceiling. It never
states that a buyer *is eligible*: other criteria apply, and HDB's HFE letter
is the only confirmation. Callers should show ``verified`` and ``source_url``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

CONFIG = Path(__file__).with_name("income_ceilings.json")
# Within this fraction of a ceiling (either side) counts as "near the boundary".
NEAR_BOUNDARY_FRACTION = Decimal("0.05")


class IncomeRuleError(ValueError):
    """Bad input (unknown scheme, invalid income) or a malformed config file."""


@dataclass(frozen=True)
class IncomeCheck:
    scheme: str
    label: str
    income: Decimal
    ceiling: Decimal | None       # None: the scheme has no income ceiling
    within_ceiling: bool
    near_boundary: bool
    margin: Decimal | None        # ceiling - income; negative means above the ceiling
    source_url: str
    effective_from: str | None
    checked_on: str
    verified: bool                # False: figure not yet confirmed on an official page
    # Added 2026-10-17 (Sandra): HDB's ceiling variants, verbatim (e.g. $24,000 for extended families).
    conditions: tuple[str, ...] = ()

    @property
    def message(self) -> str:
        if self.ceiling is None:
            text = f"{self.label} has no income ceiling."
        elif self.within_ceiling:
            text = (f"An income of SGD {self.income:,.2f} is within the {self.label} "
                    f"ceiling of SGD {self.ceiling:,.2f}.")
        else:
            text = (f"An income of SGD {self.income:,.2f} is above the {self.label} "
                    f"ceiling of SGD {self.ceiling:,.2f}.")
        if self.conditions:
            text += " Different ceilings apply in some situations; see HDB's conditions."
        if self.near_boundary:
            text += " It is close to the ceiling, so HDB's own income assessment will decide."
        text += " Other conditions also apply; only HDB's HFE letter confirms eligibility."
        if not self.verified:
            text += " (Ceiling not yet verified against an official source.)"
        return text


def _decimal(value, name: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise IncomeRuleError(f"{name} is not a number: {value!r}") from None
    if not number.is_finite() or number < 0:
        raise IncomeRuleError(f"{name} must be a non-negative number: {value!r}")
    return number


@lru_cache(maxsize=4)
def load_ceilings(path: Path = CONFIG) -> dict:
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
        schemes = config["schemes"]
    except (OSError, json.JSONDecodeError, KeyError) as error:
        raise IncomeRuleError(f"Could not load income ceilings from {path}: {error}") from error
    required = {"label", "ceiling", "inclusive", "source_url", "checked_on", "verified"}
    for name, scheme in schemes.items():
        missing = required - scheme.keys()
        if missing:
            raise IncomeRuleError(f"Scheme {name!r} is missing {sorted(missing)}")
        if scheme["ceiling"] is not None:
            _decimal(scheme["ceiling"], f"{name}.ceiling")
    return schemes


def check_income_ceiling(scheme: str, monthly_household_income, *, config: Path = CONFIG) -> IncomeCheck:
    schemes = load_ceilings(config)
    if scheme not in schemes:
        raise IncomeRuleError(f"Unknown scheme {scheme!r}. Known: {', '.join(sorted(schemes))}")
    rule = schemes[scheme]
    income = _decimal(monthly_household_income, "monthly_household_income")
    ceiling = None if rule["ceiling"] is None else _decimal(rule["ceiling"], "ceiling")

    if ceiling is None:
        within, near, margin = True, False, None
    else:
        margin = ceiling - income
        within = income <= ceiling if rule["inclusive"] else income < ceiling
        near = abs(margin) <= ceiling * NEAR_BOUNDARY_FRACTION

    return IncomeCheck(
        scheme=scheme, label=rule["label"], income=income, ceiling=ceiling,
        within_ceiling=within, near_boundary=near, margin=margin,
        source_url=rule["source_url"], effective_from=rule.get("effective_from"),
        checked_on=rule["checked_on"], verified=bool(rule["verified"]),
        conditions=tuple(rule.get("conditions", ())),
    )


def check_all_schemes(monthly_household_income, *, config: Path = CONFIG) -> list[IncomeCheck]:
    return [check_income_ceiling(name, monthly_household_income, config=config)
            for name in load_ceilings(config)]
