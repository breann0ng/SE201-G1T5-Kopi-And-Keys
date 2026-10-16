"""Deterministic policy rules (no model calls)."""

from .income import IncomeCheck, IncomeRuleError, check_all_schemes, check_income_ceiling, load_ceilings

__all__ = ["IncomeCheck", "IncomeRuleError", "check_all_schemes", "check_income_ceiling", "load_ceilings"]
