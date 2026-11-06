"""Profile consistency and assessment scope, without deciding grant eligibility."""

import re


def personal_question(question: str) -> bool:
    return bool(re.search(r"\b(?:am i|are we|do i qualify|do we qualify|can i|can we|for me|for us|"
                          r"like me|like us|my situation|our situation|my profile|our profile)\b", question, re.I))


def profile_issue(state) -> tuple[str, str] | None:
    question = state.followup_question or state.message
    if not personal_question(question):
        return None
    if state.citizenship == "SC_single" and state.household_type in {"couple_family", "fiance", "extended_family"}:
        return "clarify", ("Your profile combines Single Singapore Citizen with a family household. "
                           "Please correct Household citizenship or Household type in Your situation, then resend your question.")
    if state.subsidy_status == "mixed" and state.household_type == "single":
        return "clarify", ("A mixed first-/second-timer household needs more than one applicant. "
                           "Please check Household type and subsidy history in Your situation.")
    if not re.search(r"\behg\b|enhanced\s+(?:cpf\s+)?housing\s+grant", question, re.I):
        return None
    if state.first_timer is False and state.subsidy_status is None:
        return "clarify", ("Your profile says Second-timer. Please confirm the household subsidy history: "
                           "second-timer household or mixed first-/second-timer couple. These need different source conditions.")
    if state.subsidy_status == "second_timer":
        return "abstain", ("Your profile is set to Second-timer household. I cannot assess this profile using "
                           "first-timer EHG conditions or amount tables. If a co-applicant is a first-timer, "
                           "select Mixed first-/second-timer couple and ask again. Otherwise, check the applicable "
                           "HDB rules and HFE assessment; this is not an eligibility decision.")
    return None
