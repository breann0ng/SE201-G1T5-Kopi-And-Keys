"""Build topic cards (data/topic_cards/*.json) from chunks.jsonl (no network).

Usage: python build_cards.py [YYYY-MM-DD]   (default: date in data/policy_snapshots/ACTIVE)

Each card's supporting chunks are SELECTED BY RULE (source pages + a phrase the
chunk must contain), so chunk IDs are traceable and rebuild deterministically.
Tier-1 (hdb.gov.sg / CPF scheme pages / HDB PDFs) chunks come first, per the
2026-10-15 decision to cite HDB where sources differ. Low-priority (thin-page)
chunks are never used. question_template must not contain policy figures.
"""
from __future__ import annotations

import json
import re
import sys

from fetch import ROOT

SNAPS = ROOT / "data" / "policy_snapshots"
MAX_CHUNKS = 6

# card_id -> spec. "sources": regexes on source_slug; "must": regex the chunk content must match;
# "cover": regexes (or [slug_regex, content_regex]) that must each be represented by at
# least one supporting chunk (key evidence).
CARDS = {
    "CARD_EHG": {
        "cover": [["ehg-amount-families$", "Not more than"], ["ehg-amount-singles$", "Not more than"],
                  "non-resident spouse"],
        "topic_name": "Enhanced CPF Housing Grant (EHG)",
        "trigger_conditions": {"first_timer": ["true"],
                               "citizenship": ["SC/SC", "SC/SPR", "SC/NR", "SC_single"]},
        "required_fields": ["citizenship", "household_type", "first_timer", "age", "household_income"],
        "sources": [r"^hdb-grant-(family|singles)-ehg$", r"^hdb-pdf-ehg-amount-"],
        "must": r"income|EHG amount|Not more than",
        "question_template": ("For a {household_type} household with citizenship {citizenship}, first-timer status "
                              "{first_timer}, youngest applicant aged {age} and average gross monthly household income "
                              "of {household_income}, is the household eligible for the Enhanced CPF Housing Grant, "
                              "and which EHG amount applies?"),
    },
    "CARD_FAMILY_GRANT": {
        "cover": ["SC/ ?SPR", "income"],
        "topic_name": "CPF Housing Grant for Resale Flats (Families)",
        "trigger_conditions": {"household_type": ["couple_family", "fiance"],
                               "citizenship": ["SC/SC", "SC/SPR"]},
        "required_fields": ["citizenship", "household_type", "first_timer", "household_income", "flat_type"],
        "sources": [r"^hdb-grant-family-cpf-housing-grants$"],
        "must": r"\$|income|SC/ ?S",
        "question_template": ("For a {household_type} household with citizenship {citizenship}, first-timer status "
                              "{first_timer} and average gross monthly household income of {household_income}, buying "
                              "a {flat_type} resale flat, does the CPF Housing Grant for Resale Flats (Families) "
                              "apply, and what amount is stated for this citizenship and flat type?"),
    },
    "CARD_PHG": {
        "cover": ["live with", "live near|within 4"],
        "topic_name": "Proximity Housing Grant (PHG)",
        "trigger_conditions": {"citizenship": ["SC/SC", "SC/SPR", "SC_single"]},
        "required_fields": ["citizenship", "household_type", "lives_with_or_near_parents_or_child",
                            "distance_to_parents_or_child"],
        "sources": [r"^hdb-grant-family-phg$", r"singles-proximity-housing-grant$"],
        "must": r"live (with|near)|within",
        "question_template": ("For a {household_type} household with citizenship {citizenship} that will "
                              "{lives_with_or_near_parents_or_child} their parents/ child, at a distance of "
                              "{distance_to_parents_or_child}, does the Proximity Housing Grant apply, and which "
                              "amount is stated?"),
    },
    "CARD_LEASE_ELIGIBILITY": {
        "cover": ["95", "remaining lease"],
        "topic_name": "Remaining lease, CPF usage and HDB loan for older resale flats",
        "trigger_conditions": {},
        "required_fields": ["remaining_lease", "age", "intends_to_use_cpf", "loan_type"],
        "sources": [r"^hdb-resale-mode-of-financing$", r"^cpf-how-much-cpf-for-home-purchase$"],
        "must": r"remaining lease|age (of )?95",
        "question_template": ("For a resale flat with remaining lease of {remaining_lease}, where the youngest buyer is "
                              "aged {age}, using CPF: {intends_to_use_cpf}, with a {loan_type} loan, how much CPF can "
                              "be used and does the remaining lease cover the youngest buyer as required?"),
    },
    "CARD_INCOME_CEILING": {
        "cover": ["extended", "must not exceed"],
        "topic_name": "Income Ceiling Check",
        "trigger_conditions": {},
        "required_fields": ["household_type", "household_income", "scheme_of_interest"],
        "sources": [r"^hdb-grant-(family|singles)-cpf-housing-grant", r"^hdb-pdf-income-ceiling-extended-family$",
                    r"housing-loan-from-hdb$", r"hfe-letter-inc$"],
        "must": r"income ceiling|must not exceed|average gross monthly",
        "question_template": ("For a {household_type} household with average gross monthly household income of "
                              "{household_income}, which income ceiling applies to {scheme_of_interest}, and is the "
                              "household within it?"),
    },
    "CARD_SINGLES_GRANT": {
        "topic_name": "CPF Housing Grant for Resale Flats (Singles)",
        "trigger_conditions": {"household_type": ["single"], "citizenship": ["SC_single", "SC/NR"]},
        "required_fields": ["citizenship", "age", "first_timer", "household_income", "flat_type"],
        "sources": [r"^hdb-grant-singles-cpf-housing-grant$"],
        "must": r"\$|income|aged",
        "question_template": ("For a single applicant with citizenship {citizenship}, aged {age}, first-timer status "
                              "{first_timer} and average gross monthly income of {household_income}, buying a "
                              "{flat_type} resale flat, does the Singles Grant apply, and what amount is stated?"),
    },
    "CARD_HFE_LETTER": {
        "cover": ["valid"],
        "topic_name": "HDB Flat Eligibility (HFE) letter",
        "trigger_conditions": {},
        "required_fields": ["household_type", "citizenship"],
        "sources": [r"^hdb-hfe-letter$"],
        "must": r"HFE letter",
        "question_template": ("For a {household_type} household with citizenship {citizenship}, what does the HFE "
                              "letter assess, when must it be obtained, and how long is it valid?"),
    },
    "CARD_HDB_LOAN": {
        "topic_name": "HDB housing loan eligibility",
        "trigger_conditions": {},
        "required_fields": ["citizenship", "household_type", "household_income", "age"],
        "sources": [r"housing-loan-from-hdb$"],
        "must": r"income|citizen|loan",
        "question_template": ("For a {household_type} household with citizenship {citizenship}, average gross monthly "
                              "household income of {household_income} and average applicant age {age}, is the "
                              "household eligible for an HDB housing loan, and what loan tenure and amount rules "
                              "apply?"),
    },
    "CARD_NON_CITIZEN_ELIGIBILITY": {
        "cover": ["Be an SC or SPR", "SPR household", "non-resident spouse", "Long Term Visit Pass"],
        "topic_name": "Eligibility for PR and non-citizen households",
        "trigger_conditions": {"citizenship": ["SC/SPR", "SPR/SPR", "SC/NR", "foreigner_only"]},
        "required_fields": ["citizenship", "household_type", "age", "spouse_pass_type"],
        "sources": [r"^hdb-elig-couples-families$", r"^hdb-elig-singles$"],
        "must": r"\bSPR\b|non-resident|Permanent Resident",
        "question_template": ("For a {household_type} household with citizenship {citizenship}, applicant aged {age}, "
                              "and (if applicable) a non-resident spouse holding {spouse_pass_type}, can the household "
                              "buy a resale flat, and which conditions apply?"),
    },
    "CARD_EIP_SPR_QUOTA": {
        "topic_name": "Ethnic Integration Policy (EIP) and SPR quota",
        "trigger_conditions": {"citizenship": ["SC/SPR", "SPR/SPR"]},
        "required_fields": ["citizenship", "ethnic_group", "town", "block"],
        "sources": [r"eip-and-spr-quota$"],
        "must": r"quota|EIP",
        "question_template": ("For a household with citizenship {citizenship} and ethnic group {ethnic_group}, buying "
                              "a resale flat in block {block}, {town}, do the EIP and SPR quotas allow the purchase?"),
    },
    "CARD_RESALE_OTP_DEPOSIT": {
        "cover": ["Option Fee", "Option Exercise Fee"],
        "topic_name": "Resale Option to Purchase (OTP) and deposit",
        "trigger_conditions": {},
        "required_fields": ["has_hfe_letter", "stage_of_purchase"],
        "sources": [r"^hdb-resale-mode-of-financing$", r"option-to-purchase$", r"^hdb-pdf-otp-important-notes$"],
        "must": r"Option Fee|Option Exercise Fee",
        "question_template": ("At the {stage_of_purchase} stage of buying a resale flat (HFE letter obtained: "
                              "{has_hfe_letter}), what are the Option Fee and Option Exercise Fee rules and what "
                              "happens next?"),
    },
    "CARD_STEPUP_GRANT": {
        "topic_name": "Step-Up CPF Housing Grant",
        "trigger_conditions": {"first_timer": ["false"], "household_type": ["couple_family"]},
        "required_fields": ["citizenship", "household_type", "first_timer", "household_income", "current_flat_type"],
        "sources": [r"stepup-cpf-housing-grant$"],
        "must": r"\$|income|Step-Up",
        "question_template": ("For a {household_type} household with citizenship {citizenship}, first-timer status "
                              "{first_timer}, average gross monthly household income of {household_income}, "
                              "currently owning a {current_flat_type}, does the Step-Up CPF Housing Grant apply?"),
    },
}


# One verbatim sentence per card for the overview table shown on broad questions
# ("what grants are there?"). Hand-picked for being the clearest official summary;
# each quote must appear word for word in its chunk, or the build stops.
OVERVIEW = {
    "CARD_EHG": ("CHUNK_EHG_05", "From 20 August 2024, first-timer families may qualify for an EHG of up to "
                 "$120,000, while a couple comprising a first-timer and second-timer may qualify for an EHG "
                 "(Singles) of up to $60,000."),
    "CARD_FAMILY_GRANT": ("CHUNK_FAMILY_01", "Under the CPF Housing Grant Scheme, you may qualify for a housing "
                          "subsidy of up to $80,000 to help with the purchase of a resale flat."),
    "CARD_SINGLES_GRANT": ("CHUNK_SINGLES_01", "If you are a first-timer Singapore Citizen (SC) and buying a "
                           "resale flat on your own, you may qualify for a Singles Grant of $40,000 for the "
                           "purchase of a 2- to 4- room resale flat or $25,000 for a 5-room resale flat."),
    "CARD_PHG": ("CHUNK_PHG_01", "$30,000 to live with your parents/ child\n- $20,000 to live near your "
                 "parents/ child (within 4km)"),
    "CARD_STEPUP_GRANT": ("CHUNK_STEPUP_01", "If you and your family are second-timer applicants, you may apply "
                          "for the Step-Up CPF Housing Grant of $15,000 to help with your new or resale flat "
                          "purchase."),
    "CARD_HDB_LOAN": ("CHUNK_LOAN_26", "If you need financing to buy or take over the ownership of a flat, you "
                      "may apply for a housing loan from HDB or the financial institutions (FI)."),
    "CARD_INCOME_CEILING": ("CHUNK_FAMILY_04", "Your average gross monthly household income must not exceed: "
                            "$16,000"),
    "CARD_LEASE_ELIGIBILITY": ("CHUNK_LEASE_11", "The total amount of CPF savings that can be used for your flat "
                               "purchase and/ or paying monthly mortgage instalments will depend on the extent "
                               "the remaining lease of the flat can cover the youngest buyer up to the age of 95."),
    "CARD_HFE_LETTER": ("CHUNK_HFE_01", "You need an HFE letter before you can buy an HDB flat."),
    "CARD_NON_CITIZEN_ELIGIBILITY": ("CHUNK_ELIG_62", "Long Term Visit Pass or Work Pass of at least 6 months"),
    "CARD_EIP_SPR_QUOTA": ("CHUNK_EIP_01", "When buying an HDB resale flat, you must ensure your household is "
                           "within the EIP quota for the block and neighbourhood, and if applicable, the SPR "
                           "quota as well."),
    "CARD_RESALE_OTP_DEPOSIT": ("CHUNK_RESALE_41", "You must pay flat sellers an Option Fee when they grant you "
                                "an OTP, and an Option Exercise Fee when you exercise the OTP."),
}


def main() -> None:
    date = sys.argv[1] if len(sys.argv) > 1 else (SNAPS / "ACTIVE").read_text(encoding="utf-8").strip()
    rows = [json.loads(ln) for ln in (ROOT / "data" / "policy_chunks" / date / "chunks.jsonl")
            .read_text(encoding="utf-8").splitlines()]
    out_dir = ROOT / "data" / "topic_cards"
    out_dir.mkdir(parents=True, exist_ok=True)
    for card_id, spec in CARDS.items():
        picked = [r for r in rows
                  if not r["low_priority"] and any(re.search(s, r["source_slug"]) for s in spec["sources"])
                  and re.search(spec["must"], r["content"])]
        picked.sort(key=lambda r: (r["source_tier"] or 9, rows.index(r)))
        if not picked:
            raise SystemExit(f"{card_id}: no supporting chunks matched")
        chosen: list[str] = []
        for item in spec.get("cover", []):
            slug_rx, pattern = item if isinstance(item, list) else (".", item)
            hit = next((r for r in picked
                        if re.search(slug_rx, r["source_slug"]) and re.search(pattern, r["content"])), None)
            if hit is None:
                raise SystemExit(f"{card_id}: no supporting chunk covers {pattern!r}")
            if hit["chunk_id"] not in chosen:
                chosen.append(hit["chunk_id"])
        for r in picked:
            if len(chosen) >= MAX_CHUNKS:
                break
            if r["chunk_id"] not in chosen:
                chosen.append(r["chunk_id"])
        card = {
            "card_id": card_id,
            "topic_name": spec["topic_name"],
            "trigger_conditions": spec["trigger_conditions"],
            "required_fields": spec["required_fields"],
            "supporting_chunk_ids": chosen,
            "question_template": spec["question_template"],
            "snapshot_date": date,
        }
        if card_id in OVERVIEW:
            chunk_id, quote = OVERVIEW[card_id]
            source = next((r for r in rows if r["chunk_id"] == chunk_id and not r["superseded"]), None)
            if source is None or quote not in source["content"]:
                raise SystemExit(f"{card_id}: overview quote not found verbatim in {chunk_id}")
            card["overview"] = {"chunk_id": chunk_id, "quote": quote}
        path = out_dir / f"{card_id.lower()}.json"
        path.write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{card_id}: {len(picked)} matching chunks, kept {len(chosen)}: "
              f"{card['supporting_chunk_ids']}")


if __name__ == "__main__":
    main()
