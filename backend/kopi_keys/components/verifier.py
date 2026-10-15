"""Verifier: deterministic checks on the Synthesiser's draft.

Diagram box: "Verifier (deterministic script)". `verify(state)` returns a list
of errors; an empty list means the draft may be shown. The graph sends the
first failure back to the Synthesiser with these errors, and a second failure
becomes an abstention.

Checks:
- Citations: every policy claim is cited; every cited ID was retrieved; no
  cited source is superseded.
- Numbers: the price lines match the executed SQL result to the cent, using a
  strict labelled-line grammar (`verify_generated_numbers`).
- Price provenance: the result's filters match the filters the user asked for.
- Suggestions: every suggestion uses a matched topic card and a retrieved,
  current citation.

These are structural checks. Whether a claim's wording is faithful to its
source still needs manual review (Citation Faithfulness metric).
"""

import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from ..schemas import CENT, PriceResult
from ..state import GraphState


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


def verify_generated_numbers(text: str, sql: PriceResult) -> NumericVerification:
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


def _citation_errors(citation_ids: list[str], sources: dict, what: str) -> list[str]:
    errors = []
    if not citation_ids:
        errors.append(f"A {what} has no citation.")
    for source_id in citation_ids:
        source = sources.get(source_id)
        if source is None:
            errors.append(f"Unknown citation: {source_id}")
        elif source.superseded:
            errors.append(f"Superseded source: {source_id}")
    return errors


def verify(state: GraphState) -> list[str]:
    draft = state.draft
    if draft is None:
        return ["No draft was provided."]
    if draft.kind == "clarify":
        return []

    errors = []
    sources = {passage.id: passage for passage in state.passages}
    price = state.price_result
    has_price = price is not None and price.volume > 0
    if not draft.claims and not has_price:
        errors.append("An answer requires cited claims or an executed price result.")

    for claim in draft.claims:
        errors.extend(_citation_errors(claim.citation_ids, sources, "policy claim"))

    if has_price:
        if draft.price_text is None:
            errors.append("The executed price result was not summarised.")
        else:
            errors.extend(verify_generated_numbers(draft.price_text, price).errors)
        requested = (state.town, state.flat_type, state.start_month, state.end_month)
        returned = price.filters
        if requested[0] is not None and (returned.town, returned.flat_type) != requested[:2]:
            errors.append("Price result does not match the requested town and flat type.")
        if requested[2] is not None and (returned.start_month, returned.end_month) != requested[2:]:
            errors.append("Price result does not match the requested month range.")
    elif draft.price_text:
        errors.append("Price figures were drafted without an executed price result.")

    allowed_cards = set(state.candidate_card_ids)
    for suggestion in draft.suggestions:
        if suggestion.card_id not in allowed_cards:
            errors.append(f"Unknown topic card: {suggestion.card_id}")
        errors.extend(_citation_errors(suggestion.citation_ids, sources, "suggestion"))
    return errors
