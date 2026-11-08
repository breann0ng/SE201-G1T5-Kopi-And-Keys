"""Which part of the question each policy quote answers (answers_aspect).

score_relevance compares words: a quote that shares the question's words but answers a
different part of it can pass. This check works out which aspects the question asks
(from a fixed list) and requires each quote to address one of them, for example a
duration when the question asks "how long".

Who names the aspect (KOPI_ASPECT_LABEL):
  code   (default) code finds the asked aspects the quote (or its table criterion) shows.
         Generation is unchanged.
  model  the Synthesiser also returns answers_aspect for each claim, from the asked aspects
         plus "other", and code checks that the quote shows it. Measured 2026-11-08 on the
         synthesis benchmark with qwen2.5:3b: the extra field made its quotes long and
         non-verbatim (quality passes 10 -> 5 of 12, over-abstentions 2 -> 7), so it is
         only for a larger model.

Mode (KOPI_ASPECT_CHECK):
  off      no check (the behaviour before 2026-11-08)
  shadow   (default) checked and recorded in relevance_scores, never blocks
  enforce  a failing claim is a verification error; claim salvage can still drop only it
Shadow until the check is measured against the LangSmith relevance judge and the
over-abstention target.
"""

from __future__ import annotations

import os
import re

from .policy_guardrails import GRANTS, policy_focus

# name: (asked in the question, shown in a quote). Question patterns lean broad, because an
# extra asked aspect only allows one more label; a missed one would reject a good quote.
ASPECTS: dict[str, tuple[str, str]] = {
    "income": (r"\bincome\b|\bearn\w*\b|\bsalary\b|\bceiling\b",
               r"\bincome\b|\bceiling\b|\$\s?\d"),
    "citizenship": (r"\bcitizen\w*\b|\bs?pr\b|permanent resident|\bforeign\w*\b|non-?resident|\bpass\b|\bnationality\b",
                    r"\bcitizen\w*\b|\bs?pr\b|permanent resident|non-?resident|\bforeign\w*\b|\bpass\b"),
    "age": (r"\bminimum age\b|\bage (?:limit|requirement|criteri\w+)\b|\bhow old\b|\bturning \d{2}\b"
            r"|\b(?:at least|above|below|under|over) \d{2}\b",
            r"\baged?\b|\byears? (?:of age|old)\b|\b\d{2} years\b"),
    "employment": (r"\bemploy\w*\b|\bwork(?:ed|ing)?\b|\bjob\b",
                   r"\bemploy\w*\b|\bwork(?:ed|ing)?\b"),
    "distance": (r"\bnear\b|\bclose by\b|\bproximity\b|\bwithin\b.{0,12}\bkm\b|\bliv(?:e|ing) (?:with|near)\b",  # not "PHG": a grant name is a topic
                 r"\bwithin\b.{0,12}\bkm\b|\bproximity\b|\bliv(?:e|ing)\s+(?:with|near)\b|\bnear\b"),
    "amount": (r"\bhow much\b|\bamount\b|\bmaximum\b|\bmost\b|\bup to\b",
               r"\$\s?\d|\bup to\b|\bamount\b|\bmaximum\b|\b\d+\s?%"),
    "lease": (r"\blease\b|\bolder flat\b|\bold flat\b|\bage of the flat\b|\b\d+[- ]year[- ]old\b|\byears? left\b",
              r"\blease\b"),
    "cpf": (r"\bcpf\b", r"\bcpf\b"),
    "loan": (r"\bloans?\b|\bmortgage\b|\bborrow\w*\b|\bltv\b|loan-to-value|\bdown ?payment\b|\bupfront\b|\binterest\b",
             r"\bloans?\b|\bmortgage\b|loan-to-value|\bltv\b|\bdown ?payment\b|\b\d+\s?%|\binterest\b"),
    "timing": (r"\bhow long\b|\bvalid\w*\b|\bwait[- ]?out\b|\bminimum occupation\b|\bmop\b"
               r"|\bwhen (?:can|do|should|must)\b|\bdeadline\b|\bexpir\w*\b",
               # a duration, not just "valid" or "period": "you need a valid HFE letter" says nothing about how long
               r"\b(?:\d+|one|two|three|five|six|nine|twelve)\s+(?:months?|years?|days?|weeks?)\b"
               r"|\bminimum occupation period\b|\bwait[- ]?out period\b"),
    "quota": (r"\bethnic\w*\b|\bquota\b|\beip\b|\bfull\b|\bchinese\b|\bmalay\b|\bindian\b",
              r"\bethnic\w*\b|\bquota\b|\beip\b|\bchinese\b|\bmalay\b|\bindian\b"),
    "process": (r"\boption to purchase\b|\botp\b|\boption fee\b|\bexercise fee\b|\bsteps?\b(?!-up)|\bprocess\b"
                # what the question asks, not its topic nouns: "HFE letter" alone is a topic
                r"|\bsign\w*\b|\bpay the seller\b|\bhow (?:do|can) (?:i|we) (?:apply|get)\b|\bdocuments?\b|\bpaperwork\b",
                r"\boption\b|\botp\b|\bfee\b|\bsteps?\b|\bprocess\b|\bsign\w*\b|\bhfe\b|\bapply\b"
                r"|\bapplication\b|\bdocuments?\b|\bsubmit\w*\b"),
}
OTHER = "other"

PROMPT = """Each claim also has answers_aspect: the part of the question its quote answers, one of
answer_requirements.asked_aspects. Use "other" only for a needed condition that answers none of
them. The application checks that the quote really addresses the aspect you name."""


def mode() -> str:
    value = os.getenv("KOPI_ASPECT_CHECK", "shadow").strip().lower()
    if value not in {"off", "shadow", "enforce"}:
        raise ValueError("KOPI_ASPECT_CHECK must be off, shadow or enforce.")
    return value


def asked_aspects(question: str) -> list[str]:
    # Grant names are topics, not asks: "Proximity Housing Grant" does not ask about distance,
    # "Enhanced CPF Housing Grant" does not ask about CPF.
    question = policy_focus(question)
    for pattern in GRANTS.values():
        question = re.sub(pattern, " ", question, flags=re.I)
    return [name for name, (asked, _) in ASPECTS.items() if re.search(asked, question, re.I)]


def shows_aspect(aspect: str, text: str) -> bool:
    return aspect in ASPECTS and bool(re.search(ASPECTS[aspect][1], text, re.I))


def label_mode() -> str:
    value = os.getenv("KOPI_ASPECT_LABEL", "code").strip().lower()
    if value not in {"code", "model"}:
        raise ValueError("KOPI_ASPECT_LABEL must be code or model.")
    return value


def model_labels() -> bool:
    """Whether the Synthesiser is asked for answers_aspect."""
    return mode() != "off" and label_mode() == "model"


def schema_choices(question: str) -> list[str]:
    return [*asked_aspects(question), OTHER]


def check_claim(question: str, claim) -> dict | None:
    """The aspect result for one claim, or None when there is nothing to check (no quote).

    With a model label, the label must be asked and shown by the quote. Without one, the
    quote must show at least one asked aspect, and the first one found is recorded.
    """
    if claim.supporting_quote is None:
        return None
    asked = asked_aspects(question)
    evidence = claim.supporting_quote + " " + (claim.source_criterion or "")
    label = getattr(claim, "answers_aspect", None)
    source = "model" if label is not None else "code"
    if label is None:
        label = next((a for a in asked if shows_aspect(a, evidence)), OTHER)
    result = {"aspect": label, "aspect_source": source, "asked_aspects": asked,
              "aspect_ok": True, "aspect_reason": "aspect addressed"}
    if not asked:
        result["aspect_reason"] = "question names no specific aspect"
    elif label == OTHER:
        result.update(aspect_ok=False, aspect_reason="quote answers none of the asked aspects")
    elif label not in asked:
        result.update(aspect_ok=False, aspect_reason=f"'{label}' was not asked")
    elif not shows_aspect(label, evidence):
        result.update(aspect_ok=False, aspect_reason=f"labelled '{label}' but the quote does not address it")
    return result


def aspect_error(index: int, result: dict) -> str:
    return (f"Claim {index + 1} does not answer the question: {result['aspect_reason']} "
            f"(asked: {', '.join(result['asked_aspects'])}). Select a quote that addresses an asked aspect, "
            "or abstain if the evidence is missing.")
