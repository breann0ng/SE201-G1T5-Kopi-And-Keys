"""Deterministic relevance and grant-coverage checks, not an eligibility engine.

Scores measure lexical topic coverage, not the probability that an answer is
correct. Policy values always come from the supplied, dated passages.
"""

import re
import html
from dataclasses import dataclass

from .policy_retrieval import policy_tokens


GRANTS = {
    "ehg": r"\behg\b|\benhanced\s+(?:cpf\s+)?(?:housing\s+)?grant\b",
    "phg": r"\bphg\b|\bproximity\s+(?:housing\s+)?grant\b",
    "family_grant": r"\bfamily\s+grant\b|\bcpf\s+housing\s+grants?\s+for\s+resale\s+flats?\b",
}
_COMBINE = re.compile(r"\b(?:stack\w*|combin\w*|together|alongside|both|also|as well as)\b", re.I)
_DEPENDENCY = re.compile(r"\b(?:must\s+first\s+qualify|before\s+you\s+may\s+be\s+eligible)\b", re.I)
_GENERIC = set("hdb flat resale buy buying housing singapore grant cpf policy condition rule eligible eligibility explain demo".split())
_FACETS = {
    "income": r"\bincome\b|\bearn\w*\b|\bsalary\b",
    "employment": r"\bemploy\w*\b|\bwork(?:ed|ing)?\b",
    "citizenship": r"\bcitizen\w*\b|\bspr\b|\bpr\b|permanent resident",
    "distance": r"\bdistance\b|\bwithin\b.{0,12}\bkm\b|\bnear\b|\bliv(?:e|ing)\s+with\b",
    "amount": r"\bamount\b|\bhow much\b|\bmaximum\b|\bup to\b|\$\s*\d",
}


def mentioned_grants(text: str) -> set[str]:
    text = re.sub(r"</?(?:strong|b|em|i|u)>", "", text, flags=re.I).replace("**", "")
    found = {key for key, pattern in GRANTS.items() if re.search(pattern, text, re.I)}
    # The standalone CPF Housing Grant is distinct from the Enhanced CPF Housing
    # Grant. Mask the full EHG name before recognising that common shorthand.
    without_ehg = re.sub(GRANTS["ehg"], " ", text, flags=re.I)
    if re.search(r"\bcpf housing grant\b(?!s)", without_ehg, re.I):
        found.add("family_grant")
    return found


def requested_grants(question: str) -> set[str]:
    return mentioned_grants(question)


def combination_question(question: str) -> bool:
    return len(requested_grants(question)) > 1 and bool(_COMBINE.search(question))


def has_combination_rule(text: str, grants: set[str]) -> bool:
    """One continuous source excerpt must state the connection, not just a list."""
    return grants <= mentioned_grants(text) and bool(_COMBINE.search(text))


def prerequisite_sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text)
            if _DEPENDENCY.search(sentence) and "ehg" in mentioned_grants(sentence)]


def normalized_policy_text(text: str) -> str:
    """Ignore presentational emphasis only; never discard words or list content."""
    text = html.unescape(re.sub(r"</?(?:strong|b|em|i|u)>", "", text, flags=re.I))
    text = text.replace("**", "").replace("__", "")
    return re.sub(r"-\s+(?=\w)", "-", " ".join(text.split()))


def _terms(text: str) -> set[str]:
    return {t for t in policy_tokens(text) if len(t) > 1 and t not in _GENERIC and not t.isdigit()}


@dataclass(frozen=True)
class RelevanceScore:
    score: float
    matched_terms: tuple[str, ...]
    requested_grants: tuple[str, ...]
    covered_grants: tuple[str, ...]
    reason: str


def score_relevance(question: str, quote: str, source_title: str = "", criterion: str = "") -> RelevanceScore:
    """Score an excerpt, using its heading only for topic/table-cell context.

    Generic housing words cannot make an unrelated quote relevant. If a question
    asks about a specific aspect (income, employment, etc.), the quoted text or
    table criterion must address an aspect too; a matching title alone is not enough.
    """
    # Price details in a mixed request are checked independently against SQL.
    question = re.split(r"\band\b(?=.{0,60}\b(?:median price|resale price|price of|price for)\b)", question,
                        maxsplit=1, flags=re.I)[0]
    question = re.sub(r"\b(?:without|do not|don't|never)\s+(?:adding|add|summing|sum|calculating|calculate)\b[^.?!;]*",
                      "", question, flags=re.I)
    needed = requested_grants(question)
    covered = mentioned_grants(quote + " " + source_title) & needed
    query_terms = _terms(question)
    quote_terms = _terms(quote + " " + criterion)
    heading_terms = _terms(source_title)
    matched = query_terms & quote_terms
    lexical = (len(matched) + 0.25 * len((query_terms & heading_terms) - matched)) / max(len(query_terms), 1)
    score = min(1.0, lexical)
    reason = "lexical topic coverage"
    if not query_terms and not needed:
        score, reason = 1.0, "no specific topic terms to score"
    if needed:
        score = 0.7 * len(covered) / len(needed) + 0.3 * score
        if not covered:
            score, reason = 0.0, "quote does not address a requested grant"
    facets = {name for name, pattern in _FACETS.items() if re.search(pattern, question, re.I)}
    addressed = {name for name, pattern in _FACETS.items() if re.search(pattern, quote + " " + criterion, re.I)}
    if facets and not facets & addressed:
        score, reason = 0.0, "quote does not address the requested policy aspect"
    return RelevanceScore(round(score, 4), tuple(sorted(matched)), tuple(sorted(needed)),
                          tuple(sorted(covered)), reason)


def grant_coverage_errors(question: str, claims, sources: dict) -> list[str]:
    needed = requested_grants(question)
    if len(needed) < 2:
        return []
    errors = []
    covered = set()
    quotes = []
    for claim in claims:
        # Never use an untrusted model paraphrase to establish coverage.
        quote = claim.supporting_quote or ""
        quotes.append(quote)
        for cid in claim.citation_ids:
            source = sources.get(cid)
            if source is not None and not source.superseded:
                covered |= mentioned_grants(quote + " " + source.title)
    missing = needed - covered
    if missing:
        errors.append("Missing requested grant coverage: " + ", ".join(sorted(missing)) + ".")
    if combination_question(question):
        new_flat = bool(re.search(r"\bbto\b|\bnew flat\b", question, re.I)) and not re.search(r"\bresale\b", question, re.I)
        excludes_other_grants = new_flat and any(
            "ehg" in mentioned_grants(q) and re.search(r"\bonly housing grant\b", q, re.I) for q in quotes)
        if not excludes_other_grants and not any(has_combination_rule(q, needed) for q in quotes):
            errors.append("Missing a cited combination rule connecting all requested grants; separate grants do not establish stacking.")
        dependencies = [sentence for source in sources.values() if not source.superseded
                        for sentence in prerequisite_sentences(source.text)]
        if not new_flat and dependencies and not any(normalized_policy_text(sentence) in normalized_policy_text(q)
                                                   for sentence in dependencies for q in quotes):
            errors.append("The resale EHG prerequisite is missing; quote the supplied qualification condition in full.")
    return errors


def household_scope_errors(state, sources: dict) -> list[str]:
    """Reject a clearly opposite household scope; ambiguous source layouts stay manual.

    A source covering both household types is not rejected. In particular, mixed
    first/second-timer couples can use EHG (Singles), so that case is not treated
    as an ordinary all-first-timer family question.
    """
    question = state.followup_question or state.message
    single = bool(re.search(r"\bsingles?\b", question, re.I))
    family = bool(re.search(r"\bcouples?\b|\bfamil(?:y|ies)\b", question, re.I))
    if single and family:
        return []  # Explicit comparison, not a household-specific request.
    if re.search(r"second[- ]timer|non[- ]resident spouse", question, re.I) or state.first_timer is False:
        return []
    expected = "single" if state.household_type == "single" or single else (
        "family" if state.household_type in {"couple_family", "fiance", "extended_family"} or family else None)
    errors = []
    for claim in state.draft.claims if state.draft else []:
        for cid in claim.citation_ids:
            source = sources.get(cid)
            if not source or source.superseded:
                continue
            text = (claim.supporting_quote or "") + " " + source.title
            has_single = bool(re.search(r"\bsingles?\b", text, re.I))
            has_family = bool(re.search(r"\bcouples?\b|\bfamil(?:y|ies)\b", text, re.I))
            # Some scraped chunks lost their opening subheading but retain an
            # unambiguous household label later in the text. Use that context
            # without guessing when the passage mentions both household types.
            source_text = source.title + " " + source.text
            source_single = bool(re.search(r"\bsingles?\b", source_text, re.I))
            source_family = bool(re.search(r"\bcouples?\b|\bfamil(?:y|ies)\b", source_text, re.I))
            if ((expected == "family" and ((has_single and not has_family) or (source_single and not source_family)))
                    or (expected == "single" and ((has_family and not has_single) or (source_family and not source_single)))):
                errors.append("A policy quote uses the opposite household scope; select the supplied conditions for this household.")
    return errors
