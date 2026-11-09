"""Profile consistency and assessment scope, without deciding grant eligibility."""

import re


def personal_question(question: str) -> bool:
    return bool(re.search(r"\b(?:am i|are we|do i qualify|do we qualify|can i|can we|for me|for us|"
                          r"like me|like us|my situation|our situation|(?:my|our) (?:sidebar )?profile)\b", question, re.I))


def profile_issue(state) -> tuple[str, str] | None:
    question = state.followup_question or state.message
    from .query_router import classify_intent

    # Pure transaction-price queries do not need household eligibility details.
    if classify_intent(question) in {"price", "unanswerable"}:
        return None
    conflict = profile_conflict(state)
    if conflict:
        return "clarify", conflict
    if not personal_question(question):
        return None
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


def profile_conflict(profile) -> str | None:
    """Structural selector conflicts, not age/income/eligibility decisions."""
    if profile.citizenship == "SC_single" and profile.household_type in {"couple_family", "fiance", "extended_family"}:
        return ("Your profile combines Single Singapore Citizen with a family household. "
                           "Please correct Household citizenship or Household type in Your situation, then resend your question.")
    if profile.household_type == "single" and profile.citizenship in {"SC/SC", "SC/SPR", "SPR/SPR"}:
        return ("Your profile combines a two-person citizenship household with Single. "
                "Please correct Household citizenship or Household type in Your situation, then resend your question.")
    if profile.subsidy_status == "mixed" and (profile.household_type == "single" or profile.citizenship == "SC_single"):
        return ("A mixed first-/second-timer household needs more than one applicant. "
                           "Please check Household type and subsidy history in Your situation.")
    return None


def policy_profile_note(profile, question: str, response) -> str | None:
    if response.status != "answered" or response.route not in {"policy", "mixed"}:
        return None
    if not (personal_question(question) or re.search(r"eligib|qualif|grants?|\behg\b|\bphg\b", question, re.I)):
        return None
    citizenship = {"SC_single": "Single Singapore Citizen", "SC/SC": "Two Singapore Citizens",
                   "SC/SPR": "Singapore Citizen with Singapore Permanent Resident",
                   "SPR/SPR": "Singapore Permanent Residents only",
                   "SC/NR": "Singapore Citizen with non-resident spouse/family"}.get(profile.citizenship, profile.citizenship)
    household = {"single": "Single", "couple_family": "Couple/family", "fiance": "Fiancé/fiancée",
                 "extended_family": "Extended family", "senior": "Senior household"}.get(profile.household_type)
    status = profile.subsidy_status
    if status is None and profile.first_timer is not None:
        status = "first_timer" if profile.first_timer else "second_timer"
    subsidy = {"first_timer": "First-timer household", "second_timer": "Second-timer household",
               "mixed": "Mixed first-/second-timer couple"}.get(status)
    selected = [value for value in (citizenship, household, subsidy) if value]
    if not selected:
        return None
    missing = []
    if profile.age is None:
        missing.append("age")
    if profile.subsidy_status is None and profile.first_timer is None:
        missing.append("subsidy history")
    note = "Profile supplied with this question: " + "; ".join(selected) + ". "
    if missing:
        note += "Not supplied in sidebar: " + ", ".join(missing) + ". "
    note += "These are source conditions, not an eligibility decision."
    if status == "second_timer" and re.search(r"\behg\b|enhanced\s+(?:cpf\s+)?housing\s+grant", question, re.I):
        note += (" The EHG excerpts are general scheme information, not an assessment of this second-timer household. "
                 "If a co-applicant is a first-timer, use Mixed first-/second-timer couple and ask a profile-specific question.")
    return note
