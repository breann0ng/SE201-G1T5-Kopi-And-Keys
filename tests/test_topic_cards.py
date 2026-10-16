import json

import pytest

from kopi_keys.topic_cards import TopicCardError, load_cards, match_cards


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
    card = json.loads((load_cards.__defaults__[0] / "card_ehg.json").read_text(encoding="utf-8"))
    card["trigger_conditions"] = {"citizenship": ["Martian"]}
    (tmp_path / "card_bad.json").write_text(json.dumps(card), encoding="utf-8")
    with pytest.raises(TopicCardError, match="not in vocab"):
        load_cards(cards_dir=tmp_path)
