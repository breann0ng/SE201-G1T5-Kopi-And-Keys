"""Appendix E metrics, computed deterministically from labelled questions.

Targets from the proposal:
- routing_accuracy            >= 90%
- retrieval_recall_at_5       >= 85% of policy questions
- discovery precision/recall  >= 80% / >= 70%
- unsafe answering            <= 5%;  over-abstention <= 10%
- uncited answers             0;      staleness error rate 0%
Price checks (no target in the proposal): price_filters() compares the filters the app
would query with the labelled price_filters; price_figures() compares the price tool's
volume and median on those filters with expected_price, computed separately in SQL.
Not computed here (need a judge model or manual review): citation faithfulness,
answer relevance, framing compliance. end_to_end() exports a Ragas-format file
for those.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from ..topic_cards import load_cards, match_cards

PRICE_FILTER_FIELDS = ("town", "flat_type", "start_month", "end_month", "lease_band", "storey_band")


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f}% ({n}/{d})" if d else "n/a"


def discovery(questions: Iterable[dict]) -> dict:
    """Card matcher vs expected_cards on discovery questions.

    precision / recall: matched + blocked cards count as suggested (the matcher's
    candidates, including cards still waiting on a profile field).
    precision_shown / recall_shown: matched cards only, which are the cards the app
    actually shows as suggestions. Cards ruled out by income count as neither.
    """
    cards = load_cards()
    rows, ask_ok, ask_n = [], 0, 0
    counts = {"all": [0, 0, 0], "shown": [0, 0, 0]}  # tp, fp, fn
    for q in questions:
        if q["category"] != "discovery":
            continue
        result = match_cards(q["profile"], cards, topics=q.get("topics", []))
        shown = set(result.matched_ids)
        suggested = shown | {b.card.card_id for b in result.blocked}
        expected = set(q["expected_cards"])
        for key, got in (("all", suggested), ("shown", shown)):
            c = counts[key]
            c[0], c[1], c[2] = c[0] + len(got & expected), c[1] + len(got - expected), c[2] + len(expected - got)
        if q.get("expected_ask"):
            ask_n += 1
            ask_ok += result.ask_next == q["expected_ask"]
        rows.append({"id": q["id"], "extra": sorted(suggested - expected), "missed": sorted(expected - suggested),
                     "shown": sorted(shown), "ruled_out": {r.card.card_id: r.reason for r in result.ruled_out},
                     "ask_next": result.ask_next, "expected_ask": q.get("expected_ask")})
    (tp, fp, fn), (stp, sfp, sfn) = counts["all"], counts["shown"]
    return {"precision": pct(tp, tp + fp), "recall": pct(tp, tp + fn),
            "precision_shown": pct(stp, stp + sfp), "recall_shown": pct(stp, stp + sfn),
            "ask_next_accuracy": pct(ask_ok, ask_n), "cases": rows}


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


@contextmanager
def router_today(as_of: str):
    """Pin the router's date.today() to the first day of `as_of` (YYYY-MM), so relative
    periods ("past 6 months", "this year") resolve the way the labels did."""
    from ..components import query_router

    year, month = map(int, as_of.split("-"))

    class Pinned(date):
        @classmethod
        def today(cls):
            return cls(year, month, 1)

    with patch.object(query_router, "date", Pinned):
        yield


def effective_price_filters(q: dict, as_of: str, latest_month: str | None):
    """The PriceFilters the app would query for this question, as the graph builds them.

    A clarification is answered with the next user turn, routed with the first turn's
    values as `known` and the first question as context (graph.query_router).
    """
    from ..components.price_query import PriceOutOfRangeError, filters_from_state
    from ..components.query_router import EXTRACTED_FIELDS, route_query

    users = [t["user"] for t in q["turns"] if "user" in t]
    with router_today(as_of):
        state = route_query(users[0])
        if state.status == "clarify" and len(users) > 1:
            known = {f: getattr(state, f) for f in (*EXTRACTED_FIELDS, "start_month", "end_month")}
            state = route_query(users[1], known, context_question=users[0])
    try:
        return filters_from_state(state, latest_month=latest_month)
    except PriceOutOfRangeError as error:  # e.g. "in 2012": score the period as asked
        if error.filters is None:
            raise
        return error.filters


def price_filters(questions: Iterable[dict], as_of: str, latest_month: str | None) -> dict:
    """Town, flat type, period and bands the app would query vs the labelled price_filters."""
    from ..components.price_query import ToolUnavailableError

    rows, ok = [], 0
    for q in questions:
        if not q.get("price_filters"):
            continue
        want = {f: q["price_filters"].get(f) for f in PRICE_FILTER_FIELDS}
        try:
            f = effective_price_filters(q, as_of, latest_month)
            got = {field: getattr(f, field) for field in PRICE_FILTER_FIELDS}
        except (ToolUnavailableError, ValueError) as error:  # InvalidPriceFilterError, pydantic errors
            got = {"error": str(error)}
        ok += got == want
        if got != want:
            rows.append({"id": q["id"], "wrong": sorted(k for k in want if got.get(k) != want[k]),
                         "got": got, "expected": want})
    return {"accuracy": pct(ok, ok + len(rows)), "mismatches": rows}


def price_figures(questions: Iterable[dict], tool, as_of: str) -> dict:
    """Volume and median from the app's filters + price tool vs the SQL-computed expected_price."""
    from ..components.price_query import ToolUnavailableError, latest_month

    try:
        latest = latest_month(tool)
    except ToolUnavailableError as error:
        return {"accuracy": "n/a", "error": str(error), "mismatches": []}
    rows, ok = [], 0
    for q in questions:
        want = q.get("expected_price")
        if not want:
            continue
        want = {"volume": want["volume"], "median": want.get("median")}
        try:
            result = tool.query(effective_price_filters(q, as_of, latest))
            got = {"volume": result.volume, "median": result.median}
        except (ToolUnavailableError, ValueError) as error:  # e.g. a period outside the data
            got = {"volume": 0, "median": None, "error": str(error)}
        match = got["volume"] == want["volume"] and got["median"] == want["median"]
        ok += match
        if not match:
            rows.append({"id": q["id"], "got": {k: str(v) for k, v in got.items()},
                         "expected": {k: str(v) for k, v in want.items()}})
    return {"accuracy": pct(ok, ok + len(rows)), "mismatches": rows}


def _price_matches(q: dict, resp: dict) -> bool | None:
    """Answered price figures vs expected_price; None when the question has no expected figures."""
    want = q.get("expected_price")
    if not want or not want["volume"]:
        return None
    got = resp.get("price_result") or {}
    median = got.get("median")
    return got.get("volume") == want["volume"] and median is not None and Decimal(str(median)) == want["median"]


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
            "price_ok": _price_matches(q, resp) if resp["status"] == "answered" else None,
        })
        if resp["status"] == "answered":
            ragas.append({"id": q["id"], "question": q["question"], "answer": text,
                          "contexts": [c.get("text", "") for c in resp.get("citations", [])],
                          "ground_truth": q.get("expected_answer", "")})
    ok = [r for r in rows if "error" not in r]
    should_abstain = [r for q, r in zip(questions, rows) if "error" not in r and q["should_abstain"]]
    answerable = [r for q, r in zip(questions, rows) if "error" not in r and not q["should_abstain"]]
    changed = [r for r in ok if r["category"] == "policy_changed"]
    priced = [r for r in ok if r["price_ok"] is not None]
    return {
        "routing_accuracy": pct(sum(r["route"] == r["expected_route"] for r in ok), len(ok)),
        "unsafe_answering": pct(sum(r["unsafe"] for r in should_abstain), len(should_abstain)),
        "over_abstention": pct(sum(r["over_abstained"] for r in answerable), len(answerable)),
        "uncited_answers": sum(r["uncited"] for r in ok),
        "staleness_errors": pct(sum(r["stale"] for r in changed), len(changed)),
        "price_figures": pct(sum(r["price_ok"] for r in priced), len(priced)),
        "errors": len(rows) - len(ok),
        "cases": rows,
        "ragas": ragas,
    }


# --- Retrieval: Hit@5, Recall@5, Recall@20, MRR per gold item (added 2026-11-08) ----------
# retrieval_recall_at_k above counts a question as found when ANY expected chunk is in the
# top k: that is Hit@k. The functions below keep each evidence item separate, so a question
# with three gold quotes and one found scores Recall@5 = 1/3 but Hit@5 = 1.
# A gold item is found at rank r when the chunk at rank r comes from the item's source and
# contains its quote verbatim (dataset.py's resolution rule, but every matching chunk counts,
# not only the non-low-priority ones dataset.py prefers).

DEEP_K = 20


def gold_chunk_sets(q: dict, chunks: list[dict]) -> list[set[str]]:
    """For each evidence item of a question, the IDs of every current chunk containing its quote."""
    import re

    return [{c["chunk_id"] for c in chunks if not c["superseded"]
             and re.search(ev["source"], c["source_slug"]) and ev["quote"] in c["content"]}
            for ev in q.get("evidence", [])]


def retrieval_ranked(questions: Iterable[dict], search: Callable[[str, int], list[str]],
                     chunks: list[dict], indexed: set[str] | None = None) -> dict:
    """Hit@5, Recall@5, Recall@20 and MRR@20, overall and in three slices.

    indexed: chunk IDs the searched index holds (None = all chunks). A gold item none of
    whose chunks is indexed is NOT_IN_INDEX; dataset.load_questions already refuses a
    quote that matches no chunk at all, so that case cannot pass silently.
    """
    rows = []
    for q in questions:
        golds = gold_chunk_sets(q, chunks)
        if not golds:
            continue
        got = search(q["question"], DEEP_K)[:DEEP_K]
        ranks = []  # best rank (1-based) per gold item, or None
        for ids in golds:
            ranks.append(next((r for r, cid in enumerate(got, 1) if cid in ids), None))
        best = min((r for r in ranks if r), default=None)
        not_indexed = indexed is not None and any(not (ids & indexed) for ids in golds)
        if not golds or any(not ids for ids in golds) or (not_indexed and not best):
            miss = "NOT_IN_INDEX"
        elif best and best <= 5:
            miss = "hit"
        elif best:
            miss = "rank_6_20"
        else:
            miss = "not_in_top20"
        rows.append({"id": q["id"], "category": q["category"], "n_gold": len(golds),
                     "found_at_5": sum(1 for r in ranks if r and r <= 5), "item_ranks": ranks,
                     "best_rank": best, "miss_type": miss, "top5": got[:5]})

    def summary(sel: list[dict]) -> dict:
        n = len(sel)
        if not n:
            return {"n": 0}
        return {"n": n,
                "hit_at_5": round(sum(r["best_rank"] is not None and r["best_rank"] <= 5 for r in sel) / n, 3),
                "recall_at_5": round(sum(r["found_at_5"] / r["n_gold"] for r in sel) / n, 3),
                "recall_at_20": round(sum(sum(1 for x in r["item_ranks"] if x) / r["n_gold"] for r in sel) / n, 3),
                "mrr_at_20": round(sum(1 / r["best_rank"] if r["best_rank"] else 0 for r in sel) / n, 3),
                "not_in_index": sum(r["miss_type"] == "NOT_IN_INDEX" for r in sel)}

    return {"all": summary(rows),
            "policy_retrieval": summary([r for r in rows if r["category"] != "discovery"]),
            "discovery": summary([r for r in rows if r["category"] == "discovery"]),
            "cases": rows}
