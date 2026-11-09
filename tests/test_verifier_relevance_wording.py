"""Relevance check: correct answers worded differently from the question are not rejected.

Found in testing on 9 Nov 2026: "My wife is PR and I'm Singaporean, can we buy resale?" got a
correct draft (the Citizenship row from both columns of HDB's couples table), but the verifier
rejected the Standard-column quote for low word overlap (0.17 < 0.20): the question says
"Singaporean", the table says "SC". The quotes and the passage below are copied from that trace.
"""

import pytest

from kopi_keys.components.policy_guardrails import score_relevance
from kopi_keys.components.verifier import table_row_answers_question, verify
from kopi_keys.schemas import Claim, Draft, PolicyPassage as Passage
from kopi_keys.state import GraphState

QUESTION = "My wife is PR and I’m Singaporean, can we buy resale?"
PASSAGE = Passage(**{'id': 'CHUNK_ELIG_44', 'snapshot_id': '2026-10-15', 'source_url': 'https://www.hdb.gov.sg/buying-a-flat/flat-grant-and-loan-eligibility/couples-and-families', 'superseded': False, 'text': '| Criteria | New Flats Resale Plus Flats Resale Prime <sup>\\[1\\]</sup> Flats | Resale Unclassified <sup>\\[2\\]</sup>/ Standard Flats | \n|---|---|---|\n| \\[1\\] Prime flats include Prime Location Public Housing (PLH) flats sold before October 2024 sales exercise. The eligibility criteria for resale Prime flats follow the prevailing BTO eligibility criteria. \\[2\\] Unclassified resale flats refer to flats sold before October 2024 sales exercise and not classified as Standard, Plus or Prime. |  |  | \n| **Flat type** | Up to a 3Gen flat | All flat types | \n| **Citizenship** | You must: Be a Singapore Citizen (SC) Include at least 1 other SC or Singapore Permanent Resident (SPR)<sup>@</sup> | You must: Be an SC or SPR Include at least 1 occupant who is an SC or SPR For SPR households (i.e., an SPR household with no SC applicant): All applicants and core occupiers must have SPR status for at least 3 years | \n| **Age** | At least 21 years old |  | \n| **Monthly household income ceiling** | Total income of all persons listed in the HFE letter application. 2-room Flexi flat (99-year lease): $8,000 3-room flat: $16,000 or $8,000, depending on project. Our press release on the sales launch will specify the income ceiling for each BTO project $24,000 if buying with extended or multi-generation family in projects with $16,000 income ceiling (refer to the guide for more details) 4- and 5-room flat: $16,000 $24,000 if buying with extended or multi-generation family (refer to the guide for more details) | No income ceiling **Note:** Income ceiling applies to qualify for CPF housing grants (excluding Proximity Housing Grant) and HDB housing loan. |', 'title': 'Flat eligibility (citizenship, household, age): Couples and Families > Eligibility conditions', 'verified_on': '2026-10-15'})
PLUS_PRIME = Claim(**{'citation_ids': ['CHUNK_ELIG_44'], 'source_criterion': 'Citizenship', 'source_scope': 'New Flats / Resale Plus Flats / Resale Prime Flats', 'supporting_quote': 'You must: Be a Singapore Citizen (SC) Include at least 1 other SC or Singapore Permanent Resident (SPR)<sup>@</sup>', 'text': '**New Flats / Resale Plus Flats / Resale Prime Flats**\nCitizenship: You must: Be a Singapore Citizen (SC); include at least 1 other SC or Singapore Permanent Resident (SPR)'})
STANDARD = Claim(**{'citation_ids': ['CHUNK_ELIG_44'], 'source_criterion': 'Citizenship', 'source_scope': 'Resale Unclassified / Standard Flats', 'supporting_quote': 'You must: Be an SC or SPR Include at least 1 occupant who is an SC or SPR For SPR households (i.e., an SPR household with no SC applicant): All applicants and core occupiers must have SPR status for at least 3 years', 'text': '**Resale Unclassified / Standard Flats**\nCitizenship: You must: Be an SC or SPR; include at least 1 occupant who is an SC or SPR. For SPR households (i.e., an SPR household with no SC applicant): All applicants and core occupiers must have SPR status for at least 3 years'})


def state(*claims, message=QUESTION):
    return GraphState(message=message, route="policy", intent="policy", passages=[PASSAGE],
                      draft=Draft(kind="answer", claims=list(claims)))


def test_the_correct_pr_spouse_answer_now_passes():
    assert verify(state(PLUS_PRIME, STANDARD)) == []


def test_singaporean_counts_as_sc_and_wife_as_spouse():
    before = 1 / 6  # only "spr" matched in the failing trace
    assert score_relevance(QUESTION, STANDARD.supporting_quote, PASSAGE.title,
                           "Resale Unclassified / Standard Flats Citizenship").score > before
    assert "spr" in score_relevance(QUESTION, STANDARD.supporting_quote).matched_terms
    assert "sc" in score_relevance(QUESTION, STANDARD.supporting_quote).matched_terms
    assert "spouse" in score_relevance("Can my husband and I apply?", "You and your spouse may apply").matched_terms


def test_a_table_row_counts_only_when_its_criterion_is_what_was_asked():
    assert table_row_answers_question(QUESTION, STANDARD)  # Citizenship row, citizenship asked
    age_row = STANDARD.model_copy(update={"source_criterion": "Age"})
    assert not table_row_answers_question(QUESTION, age_row)
    not_a_table = STANDARD.model_copy(update={"source_criterion": None})
    assert not table_row_answers_question(QUESTION, not_a_table)


def test_an_unrelated_quote_is_still_rejected():
    unrelated = Claim(text="Total income of all persons listed in the HFE letter application.",
                      citation_ids=["CHUNK_ELIG_44"],
                      supporting_quote="Total income of all persons listed in the HFE letter application.")
    errors = verify(state(PLUS_PRIME, STANDARD, unrelated, message="Can a Singaporean marry and get a flat with a PR?"))
    assert any("Low policy relevance" in e for e in errors)


def test_a_relevant_table_row_must_still_be_quoted_word_for_word():
    altered = STANDARD.model_copy(update={"supporting_quote": "You must: Be an SC or SPR, and you are eligible",
                                           "text": "You must: Be an SC or SPR, and you are eligible"})
    assert verify(state(PLUS_PRIME, altered))


def test_a_long_question_keeps_the_citizenship_row_through_the_table_rule():
    """Word overlap falls with question length: here the Standard-column row scores under the
    threshold even with SC/spouse folding. Its row label, Citizenship, is what was asked."""
    question = ("My wife is a permanent resident and I'm Singaporean. We want a 4-room near her parents in "
                "Tampines with our two kids. Can we buy resale, and what citizenship rules apply?")
    assert score_relevance(question, STANDARD.supporting_quote, PASSAGE.title,
                           "Resale Unclassified / Standard Flats Citizenship").score < 0.20
    assert verify(state(PLUS_PRIME, STANDARD, message=question)) == []
