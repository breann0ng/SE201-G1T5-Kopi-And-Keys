"""Appendix E metrics, computed deterministically from labelled questions.

Targets from the proposal:
- routing_accuracy            >= 90%
- retrieval_recall_at_5       >= 85% of policy questions
- discovery precision/recall  >= 80% / >= 70%
- unsafe answering            <= 5%;  over-abstention <= 10%
- uncited answers             0;      staleness error rate 0%
Not computed here (need a judge model or manual review): citation faithfulness,
answer relevance, framing compliance. end_to_end() exports a Ragas-format file
for those.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from ..topic_cards import load_cards, match_cards


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f}% ({n}/{d})" if d else "n/a"


def discovery(questions: Iterable[dict]) -> dict:
    """Card matcher vs expected_cards on discovery questions (matched + blocked count as suggested)."""
    cards = load_cards()
    rows, tp, fp, fn, ask_ok, ask_n = [], 0, 0, 0, 0, 0
    for q in questions:
        if q["category"] != "discovery":
            continue
        result = match_cards(q["profile"], cards, topics=q.get("topics", []))
        suggested = set(result.matched_ids) | {b.card.card_id for b in result.blocked}
        expected = set(q["expected_cards"])
        tp, fp, fn = tp + len(suggested & expected), fp + len(suggested - expected), fn + len(expected - suggested)
        if q.get("expected_ask"):
            ask_n += 1
            ask_ok += result.ask_next == q["expected_ask"]
        rows.append({"id": q["id"], "extra": sorted(suggested - expected), "missed": sorted(expected - suggested),
                     "ask_next": result.ask_next, "expected_ask": q.get("expected_ask")})
    return {"precision": pct(tp, tp + fp), "recall": pct(tp, tp + fn), "ask_next_accuracy": pct(ask_ok, ask_n),
            "cases": rows}


def retrieval_recall_at_k(questions: Iterable[dict], search: Callable[[str, int], list[str]], k: int = 5) -> dict:
    """Share of questions with evidence whose expected chunk appears in the top k retrieved."""
    rows, hits = [], 0
    for q in questions:
        if not q.get("expected_chunk_ids"):
            continue
        got = search(q["question"], k)[:k]
        hit = bool(set(got) & set(q["expected_chunk_ids"]))
        hits += hit
        rows.append({"id": q["id"], "hit": hit, "retrieved": got, "expected": q["expected_chunk_ids"]})
    return {f"recall_at_{k}": pct(hits, len(rows)), "misses": [r for r in rows if not r["hit"]]}


def stage1_routing(questions: list[dict]) -> dict:
    """Router intent, route, status and missing fields vs the Stage 1 labels (no model calls)."""
    from ..components.query_router import route_query

    rows, ok = [], 0
    for q in questions:
        out = route_query(q["turns"][0]["user"])
        got = {"intent": out.intent, "route": out.route, "status": out.status, "missing": out.missing_fields}
        want = {"intent": q["expected_intent"], "route": q["expected_route"], "status": q["expected_status"],
                "missing": q["expected_missing_fields"]}
        ok += got == want
        if got != want:
            rows.append({"id": q["id"], "got": got, "expected": want})
    return {"routing_accuracy": pct(ok, len(questions)), "mismatches": rows}


def end_to_end(questions: list[dict], responses: dict[str, dict]) -> dict:
    """Score /chat responses (keyed by question id) against the labels."""
    rows, ragas = [], []
    for q in questions:
        resp = responses.get(q["id"])
        if resp is None or "error" in resp:
            rows.append({"id": q["id"], "error": (resp or {}).get("error", "no response")})
            continue
        abstained = resp["status"] == "abstained"
        text = resp.get("message", "")
        rows.append({
            "id": q["id"], "category": q["category"], "status": resp["status"],
            "route": resp.get("route"), "expected_route": q["expected_route"],
            "unsafe": q["should_abstain"] and not abstained,
            "over_abstained": not q["should_abstain"] and abstained,
            "uncited": resp["status"] == "answered" and not resp.get("citations") and not resp.get("price_result"),
            "stale": bool(q.get("superseded_value")) and q["superseded_value"] in text,
            "has_current": (q["current_value"] in text) if q.get("current_value") else None,
        })
        if resp["status"] == "answered":
            ragas.append({"id": q["id"], "question": q["question"], "answer": text,
                          "contexts": [c.get("text", "") for c in resp.get("citations", [])],
                          "ground_truth": q.get("expected_answer", "")})
    ok = [r for r in rows if "error" not in r]
    should_abstain = [r for q, r in zip(questions, rows) if "error" not in r and q["should_abstain"]]
    answerable = [r for q, r in zip(questions, rows) if "error" not in r and not q["should_abstain"]]
    changed = [r for r in ok if r["category"] == "policy_changed"]
    return {
        "routing_accuracy": pct(sum(r["route"] == r["expected_route"] for r in ok), len(ok)),
        "unsafe_answering": pct(sum(r["unsafe"] for r in should_abstain), len(should_abstain)),
        "over_abstention": pct(sum(r["over_abstained"] for r in answerable), len(answerable)),
        "uncited_answers": sum(r["uncited"] for r in ok),
        "staleness_errors": pct(sum(r["stale"] for r in changed), len(changed)),
        "errors": len(rows) - len(ok),
        "cases": rows,
        "ragas": ragas,
    }
