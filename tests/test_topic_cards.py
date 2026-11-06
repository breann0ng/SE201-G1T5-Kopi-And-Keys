import json

import pytest

from kopi_keys.topic_cards import TopicCardError, load_cards, match_cards, snapshot_cards_dir


@pytest.fixture(scope="module")
def cards():
    return load_cards()


def by_id(result):
    return {b.card.card_id: set(b.missing_fields) for b in result.blocked}


def test_repo_cards_load_and_validate(cards):
    assert len(cards) == 12
    assert len({c.card_id for c in cards}) == 12


def test_empty_profile_matches_nothing_and_asks_for_citizenship_first(cards):
    result = match_cards({}, cards)
    assert result.matched == []
    # Cards without triggers are never suggested from the profile alone.
    assert "CARD_HDB_LOAN" not in by_id(result)
    assert result.ask_next == "citizenship"


def test_first_timer_sc_spr_couple_with_details_matches_ehg(cards):
    profile = {
        "citizenship": "SC/SPR",
        "household_type": "couple_family",
        "first_timer": True,  # booleans are compared as vocab strings
        "age": 30,
        "household_income": 7200,
    }
    result = match_cards(profile, cards)
    assert "CARD_EHG" in result.matched_ids
    blocked = by_id(result)
    assert blocked["CARD_FAMILY_GRANT"] == {"flat_type"}
    assert "CARD_SINGLES_GRANT" not in blocked  # single-only trigger rules it out
    assert "CARD_STEPUP_GRANT" not in blocked  # second-timer trigger rules it out


def test_value_outside_triggers_rules_card_out(cards):
    result = match_cards({"citizenship": "SPR/SPR", "first_timer": True}, cards)
    assert "CARD_EHG" not in result.matched_ids
    assert "CARD_EHG" not in by_id(result)
    assert "CARD_EIP_SPR_QUOTA" in by_id(result)


def test_foreigner_routes_to_non_citizen_card(cards):
    result = match_cards({"citizenship": "foreigner_only"}, cards)
    blocked = by_id(result)
    assert "CARD_NON_CITIZEN_ELIGIBILITY" in blocked
    # Every card whose citizenship trigger excludes foreigners is ruled out.
    for card_id in ("CARD_EHG", "CARD_FAMILY_GRANT", "CARD_PHG", "CARD_SINGLES_GRANT", "CARD_EIP_SPR_QUOTA"):
        assert card_id not in blocked
    # The captured Step-Up page states no citizenship rule, so code cannot rule it out
    # (no trigger is invented without a source); it stays blocked on other fields.
    assert "citizenship" not in blocked.get("CARD_STEPUP_GRANT", set())


def test_topics_bring_in_trigger_free_cards(cards):
    profile = {"remaining_lease": "60 years", "age": 30, "intends_to_use_cpf": "yes", "loan_type": "HDB"}
    result = match_cards(profile, cards, topics=["CARD_LEASE_ELIGIBILITY"])
    assert "CARD_LEASE_ELIGIBILITY" in result.matched_ids


def test_exclude_removes_already_answered_cards(cards):
    profile = {"citizenship": "SC/SC", "household_type": "couple_family", "first_timer": "true",
               "age": 30, "household_income": 5000}
    result = match_cards(profile, cards, exclude=["CARD_EHG"])
    assert "CARD_EHG" not in result.matched_ids


def test_ask_next_is_the_field_unblocking_most_cards(cards):
    result = match_cards({"citizenship": "SC/SC"}, cards)
    counts = {}
    for b in result.blocked:
        for f in b.missing_fields:
            counts[f] = counts.get(f, 0) + 1
    assert counts[result.ask_next] == max(counts.values())


def test_loader_rejects_values_outside_vocab(tmp_path):
    card = json.loads((snapshot_cards_dir() / "card_ehg.json").read_text(encoding="utf-8"))
    card["trigger_conditions"] = {"citizenship": ["Martian"]}
    (tmp_path / "card_bad.json").write_text(json.dumps(card), encoding="utf-8")
    with pytest.raises(TopicCardError, match="not in vocab"):
        load_cards(cards_dir=tmp_path)


def test_graph_adapter_loads_repo_cards_and_maps_state_fields():
    # graph.py loads data/topic_cards/<ACTIVE>/ through components/topic_cards.py at startup.
    from kopi_keys.components import topic_cards as adapter
    from kopi_keys.state import GraphState

    repo_cards = adapter.load_cards()
    assert len(repo_cards) == 12
    state = GraphState(message="hi", citizenship="SC/SPR", first_timer=True, user_age=30, income=7200)
    result = adapter.match_profile(state, repo_cards)
    assert result.ask_next == "household_type"  # not collected by the router yet
    assert adapter.match_cards(state, repo_cards) == result.matched_ids
    assert "household_income" in adapter.required_fields(["CARD_EHG"], repo_cards)


# --- Income-aware matching (income_schemes -> rules/income_ceilings.json) ---

FIRST_TIMER_FAMILY = {"citizenship": "SC/SC", "household_type": "couple_family", "first_timer": True, "age": 30}


def ruled_out(result):
    return {r.card.card_id: r.reason for r in result.ruled_out}


def test_income_above_every_ehg_ceiling_rules_ehg_out_with_a_reason(cards):
    result = match_cards({**FIRST_TIMER_FAMILY, "household_income": 11000}, cards)
    assert "CARD_EHG" in ruled_out(result)
    assert "$9,000" in ruled_out(result)["CARD_EHG"]
    assert "CARD_EHG" not in result.matched_ids and "CARD_EHG" not in by_id(result)
    # The Family Grant's ceiling is higher ($16,000), so it stays.
    assert "CARD_FAMILY_GRANT" not in ruled_out(result)


def test_income_at_the_ceiling_keeps_the_card(cards):
    result = match_cards({**FIRST_TIMER_FAMILY, "household_income": 9000}, cards)
    assert "CARD_EHG" in result.matched_ids


def test_income_near_the_ceiling_keeps_the_card(cards):
    # Within 5% above $9,000: HDB's own assessment decides, so the card is not ruled out.
    result = match_cards({**FIRST_TIMER_FAMILY, "household_income": 9400}, cards)
    assert "CARD_EHG" not in ruled_out(result)


def test_a_higher_variant_ceiling_keeps_the_card(cards):
    # $20,000 is above the Family Grant's $16,000 but within its $24,000 extended-family variant.
    result = match_cards({**FIRST_TIMER_FAMILY, "household_income": 20000}, cards)
    assert "CARD_FAMILY_GRANT" not in ruled_out(result)
    assert "CARD_EHG" in ruled_out(result)


def test_income_above_every_variant_rules_the_family_grant_out(cards):
    result = match_cards({**FIRST_TIMER_FAMILY, "household_income": 30000}, cards)
    assert "CARD_FAMILY_GRANT" in ruled_out(result)


def test_unknown_or_invalid_income_never_rules_a_card_out(cards):
    for income in (None, "", "not a number"):
        assert ruled_out(match_cards({**FIRST_TIMER_FAMILY, "household_income": income}, cards)) == {}


def test_card_without_a_verified_ceiling_is_never_ruled_out_by_income(cards):
    # PHG has no income_schemes (its ceiling is unverified), so a high income does not rule it out.
    result = match_cards({**FIRST_TIMER_FAMILY, "household_income": 50000}, cards)
    assert "CARD_PHG" not in ruled_out(result)


def test_graph_income_notes_use_the_same_schemes_as_the_cards(cards):
    from kopi_keys.components.topic_cards import _CEILING_SCHEMES

    by = {c.card_id: c for c in cards}
    for card_id, schemes in _CEILING_SCHEMES.items():
        assert by[card_id].income_schemes == schemes, card_id
