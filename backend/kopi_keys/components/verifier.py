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
- Model-written policy summaries: their supporting quotes occur in the cited
  passages, and each written number occurs in the supporting quote.

Relevance scores and multi-grant coverage add conservative checks on topic and
scope. They are heuristics, not proof of policy correctness; citation faithfulness
and eligibility interpretation still need manual review.
"""

import re
import os
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from ..schemas import CENT, PriceResult
from ..state import GraphState
from .policy_guardrails import grant_coverage_errors, household_scope_errors, normalized_policy_text, score_relevance


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


def _comparable(text: str) -> str:
    """Text for verbatim comparison: whitespace collapsed, and a word split across lines after a
    hyphen (HDB PDFs: "first-\ntimer") joined back, on both the quote and the source."""
    return normalized_policy_text(text)


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


def verified_claim_subset(state: GraphState):
    """Share production's conservative claim salvage with the synthesis benchmark.

    Every retained claim must pass on its own AND the trimmed answer must pass
    in full. Completeness failures and explicit missing evidence cannot be hidden.
    """
    if state.draft is None or not state.draft.claims:
        return None
    kept = [claim for claim in state.draft.claims
            if not verify(state.model_copy(update={"draft": state.draft.model_copy(update={"claims": [claim]})}))]
    if kept and len(kept) < len(state.draft.claims):
        trimmed = state.draft.model_copy(update={"claims": kept})
        if not verify(state.model_copy(update={"draft": trimmed})):
            return trimmed
    return None


def policy_relevance_scores(state: GraphState) -> list[dict]:
    """Inspect the same per-claim scores used by verify; no extra model call."""
    sources = {p.id: p for p in state.passages}
    question = state.followup_question or state.message
    scores = []
    for index, claim in enumerate(state.draft.claims if state.draft else []):
        if claim.supporting_quote is None:
            continue  # Legacy/offline extractive fixtures have no model-selected quote.
        cited = [sources[c] for c in claim.citation_ids if c in sources and not sources[c].superseded]
        best = max((score_relevance(question, claim.supporting_quote, p.title,
                                    claim.source_criterion or "") for p in cited),
                   key=lambda s: s.score, default=score_relevance(question, claim.supporting_quote))
        scores.append({"claim_index": index, "score": best.score, "reason": best.reason,
                       "matched_terms": list(best.matched_terms),
                       "requested_grants": list(best.requested_grants),
                       "covered_grants": list(best.covered_grants)})
    return scores


def verify(state: GraphState) -> list[str]:
    draft = state.draft
    if draft is None:
        return ["No draft was provided."]
    if draft.kind == "clarify":
        return []

    errors = list(state.synthesis_errors)
    sources = {passage.id: passage for passage in state.passages}
    price = state.price_result
    has_price = price is not None and price.volume > 0
    if not draft.claims and not has_price:
        errors.append("An answer requires cited claims or an executed price result.")
    elif state.passages and state.route in {"policy", "mixed", "discovery"} and not draft.claims:
        errors.append("The policy question requires a cited policy summary.")

    question = state.followup_question or state.message
    minimum = float(os.getenv("KOPI_POLICY_MIN_RELEVANCE", "0.20"))
    if not 0 < minimum <= 1:
        raise ValueError("KOPI_POLICY_MIN_RELEVANCE must be greater than 0 and at most 1.")
    for score in policy_relevance_scores(state):
        if score["score"] < minimum:
            errors.append(f"Low policy relevance for claim {score['claim_index'] + 1}: "
                          f"{score['score']:.2f} < {minimum:.2f} ({score['reason']}). "
                          "Select a quote addressing the question, or abstain if the evidence is missing.")
    errors.extend(grant_coverage_errors(question, draft.claims, sources))
    errors.extend(household_scope_errors(state, sources))
    for claim in draft.claims:
        errors.extend(_citation_errors(claim.citation_ids, sources, "policy claim"))
        if claim.supporting_quote is not None:
            quote = _comparable(claim.supporting_quote)
            cited = [sources[c] for c in claim.citation_ids if c in sources]
            if not any(quote in _comparable(p.text) for p in cited):
                errors.append("A policy supporting quote is not present in its cited source.")
            if quote.rstrip().endswith(":"):
                # Lead-ins such as "... is calculated as follows:" never state the condition itself.
                errors.append("A supporting quote ends with ':' (an introduction); quote the condition that follows it.")
            numbers = {Decimal(n.replace(",", "")) for n in re.findall(r"\b\d[\d,]*(?:\.\d+)?\b", claim.text)}
            supported = {Decimal(n.replace(",", "")) for n in re.findall(r"\b\d[\d,]*(?:\.\d+)?\b", quote)}
            if claim.source_scope is not None:
                from .policy_synthesis import table_claim

                canonical = [table_claim(p, claim.supporting_quote, question) for p in cited]
                if not any(c is not None and c.text == claim.text and c.source_scope == claim.source_scope
                           and c.source_criterion == claim.source_criterion for c in canonical):
                    errors.append("A table claim does not preserve its source column and cell.")
                else:
                    context = claim.source_scope + " " + (claim.source_criterion or "")
                    supported |= {Decimal(n.replace(",", "")) for n in re.findall(r"\b\d[\d,]*(?:\.\d+)?\b", context)}
            if numbers - supported:
                errors.append("A policy claim contains numbers absent from its supporting quote.")

    if (re.search(r"\b(?:pr|spr)\b|permanent resident", question, re.I)
            and re.search(r"\bbuy\b|resale", question, re.I)):
        from .policy_synthesis import model_evidence, scope_label

        scopes = {scope_label(r["column"]).replace(" Resale ", " / Resale ") for p in state.passages
                  for r in model_evidence(p, question).get("table_rows", [])
                  if r["criterion"].lower() == "citizenship"}
        standard = {s for s in scopes if "standard" in s.lower() or "unclassified" in s.lower()}
        prime = {s for s in scopes if "prime" in s.lower() or "plus" in s.lower()}
        used = {c.source_scope for c in draft.claims}
        if standard and prime and (not used & standard or not used & prime):
            errors.append("A PR resale answer must cover Standard/unclassified and Plus/Prime citizenship conditions separately, using quotes from BOTH table columns.")

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

    for item in state.overview:
        source = sources.get(item.citation_id)
        if source is None or source.superseded:
            errors.append(f"Overview row {item.card_id} cites a missing or superseded source.")
        elif item.quote not in source.text:
            errors.append(f"Overview row {item.card_id} is not verbatim in its source.")

    allowed_cards = set(state.candidate_card_ids)
    for suggestion in draft.suggestions:
        if suggestion.card_id not in allowed_cards:
            errors.append(f"Unknown topic card: {suggestion.card_id}")
        errors.extend(_citation_errors(suggestion.citation_ids, sources, "suggestion"))
    return errors
