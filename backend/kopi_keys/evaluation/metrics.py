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
    from ..components.price_query import filters_from_state
    from ..components.query_router import EXTRACTED_FIELDS, route_query

    users = [t["user"] for t in q["turns"] if "user" in t]
    with router_today(as_of):
        state = route_query(users[0])
        if state.status == "clarify" and len(users) > 1:
            known = {f: getattr(state, f) for f in (*EXTRACTED_FIELDS, "start_month", "end_month")}
            state = route_query(users[1], known, context_question=users[0])
    return filters_from_state(state, latest_month=latest_month)


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
