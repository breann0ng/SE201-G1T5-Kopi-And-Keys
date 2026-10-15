"""Strict labelled-text grammar: compare each statistic with its SQL field."""

import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from .contracts import CENT, SQLPriceResult


# Reject malformed grouping, shorthand (600k), signs, percentages and exponents.
NUMBER = r"(?:[1-9]\d{0,2}(?:,\d{3})+|[1-9]\d*|0)(?:\.\d{1,2})?"
INTEGER = r"(?:[1-9]\d{0,2}(?:,\d{3})+|[1-9]\d*|0)"


def money(group: str) -> str:
    return rf"(?:SGD\s*|S\$\s*|\$\s*)?(?P<{group}>{NUMBER})"


PATTERNS = {
    name: re.compile(rf"{name}:\s*{money(name)}\s*\.?", re.IGNORECASE)
    for name in ("mean", "median", "iqr")
}
PATTERNS["range"] = re.compile(
    rf"range:\s*{money('minimum')}\s*(?:to|-|\u2013)\s*{money('maximum')}\s*\.?",
    re.IGNORECASE,
)
PATTERNS["volume"] = re.compile(
    rf"volume:\s*(?P<volume>{INTEGER})\s+transactions?\s*\.?", re.IGNORECASE,
)


@dataclass(frozen=True)
class NumericVerification:
    passed: bool
    errors: tuple[str, ...]


def verify_generated_numbers(text: str, sql: SQLPriceResult) -> NumericVerification:
    """Money is compared at documented cent precision; volume must match exactly.

    Every non-empty line must match one allowed label in full. This prevents
    unsupported trailing amounts and swapped statistic labels from slipping
    through a loose numeric-membership test. No user/profile numbers are allowed
    in the model draft; the final header is rendered separately from SQL filters.
    """
    if sql.volume == 0:
        return NumericVerification(False, ("No transactions support a generated benchmark.",))
    errors = []
    seen = set()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for label, pattern in PATTERNS.items():
            match = pattern.fullmatch(line)
            if match is None:
                continue
            if label in seen:
                errors.append(f"Duplicate statistic label: {label}.")
            seen.add(label)
            for field, token in match.groupdict().items():
                actual = Decimal(token.replace(",", ""))
                expected = Decimal(sql.volume) if field == "volume" else getattr(sql, field).quantize(
                    CENT, rounding=ROUND_HALF_UP,
                )
                if actual != expected:
                    errors.append(f"{field}: generated {actual}, SQL requires {expected}.")
            break
        else:
            errors.append("Unrecognised output line; use only the five allowed statistic lines.")
    for missing in sorted(set(PATTERNS) - seen):
        errors.append(f"Missing statistic label: {missing}.")
    return NumericVerification(not errors, tuple(errors))
