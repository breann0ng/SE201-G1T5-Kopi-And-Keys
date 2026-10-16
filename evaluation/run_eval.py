"""Deterministic evaluation for Kopi & Keys (proposal §4, Appendix E).

Usage (from the repo root, project venv):
  python evaluation/run_eval.py                         # dev split: discovery + BM25 baseline retrieval
  python evaluation/run_eval.py --retriever pkg.mod:fn  # your retriever: fn(query: str, k: int) -> list[chunk_id]
  python evaluation/run_eval.py --api http://127.0.0.1:8000   # also run end-to-end against POST /chat
  python evaluation/run_eval.py --split heldout --final # held-out: only for reported final results

Metrics (targets from proposal Appendix E):
  discovery precision / recall (>= 80% / >= 70%) and ask-next accuracy   [topic_cards.match_cards]
  retrieval Recall@5 (>= 85%)                                             [policy, mixed, policy_changed]
  end-to-end (--api): routing accuracy (>= 90%), unsafe answering (<= 5%), over-abstention (<= 10%),
                      uncited answers (0), staleness errors (0%)
Routing is inferred from the response trace ("retrieval:" -> policy, "price:" -> price) until the
backend returns an explicit route.

LLM-judged metrics (faithfulness, answer relevance) need a judge model: --api also writes a
Ragas-format JSONL (question, answer, contexts, ground_truth) for scoring later with Ragas/TruLens.
"""
from __future__ import annotations

import argparse
import importlib
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from kopi_keys.topic_cards import load_cards, match_cards  # noqa: E402

HERE = Path(__file__).resolve().parent
PROFILE_FIELDS = ("citizenship", "age", "household_income", "first_timer")  # BuyerProfile today
TOKEN = re.compile(r"[a-z0-9$%]+(?:[.,][0-9]+)*")


def load_items(split: str) -> list[dict]:
    path = HERE / "eval_set.jsonl"
    if not path.exists():
        raise SystemExit("Run evaluation/build_eval_set.py first.")
    items = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines()]
    return [i for i in items if split == "all" or i["split"] == split]


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f}% ({n}/{d})" if d else "n/a"


# ---------------- discovery ----------------

def eval_discovery(items: list[dict]) -> dict:
    cards = load_cards()
    rows, tp, fp, fn, ask_ok, ask_n = [], 0, 0, 0, 0, 0
    for it in items:
        if it["category"] != "discovery":
            continue
        result = match_cards(it["profile"], cards, topics=it.get("topics", []))
        suggested = set(result.matched_ids) | {b.card.card_id for b in result.blocked}
        expected = set(it["expected_cards"])
        tp += len(suggested & expected)
        fp += len(suggested - expected)
        fn += len(expected - suggested)
        if it.get("expected_ask"):
            ask_n += 1
            ask_ok += result.ask_next == it["expected_ask"]
        rows.append({"id": it["id"], "suggested": sorted(suggested), "expected": sorted(expected),
                     "extra": sorted(suggested - expected), "missed": sorted(expected - suggested),
                     "ask_next": result.ask_next, "expected_ask": it.get("expected_ask")})
    return {"precision": pct(tp, tp + fp), "recall": pct(tp, tp + fn), "ask_next_accuracy": pct(ask_ok, ask_n),
            "cases": rows}


# ---------------- retrieval ----------------

class BM25:
    """Plain BM25 over heading + content: a baseline that shows the eval set is answerable."""

    def __init__(self, chunks: list[dict], k1: float = 1.5, b: float = 0.75):
        self.ids = [c["chunk_id"] for c in chunks]
        self.docs = [Counter(TOKEN.findall((c["section_heading"] + " " + c["content"]).lower())) for c in chunks]
        self.lens = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.lens) / len(self.lens)
        df = Counter(t for d in self.docs for t in d)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.k1, self.b = k1, b

    def __call__(self, query: str, k: int = 5) -> list[str]:
        terms = TOKEN.findall(query.lower())
        scores = []
        for i, d in enumerate(self.docs):
            s = 0.0
            for t in terms:
                if t in d:
                    tf = d[t]
                    s += self.idf[t] * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * self.lens[i] / self.avg))
            scores.append((s, i))
        scores.sort(reverse=True)
        return [self.ids[i] for s, i in scores[:k] if s > 0]


def get_retriever(spec: str | None, chunks: list[dict]):
    if not spec or spec == "bm25":
        return BM25([c for c in chunks if not c["superseded"]]), "bm25-baseline"
    module, _, fn = spec.partition(":")
    return getattr(importlib.import_module(module), fn), spec


def eval_retrieval(items: list[dict], retriever, k: int = 5) -> dict:
    rows, hits = [], 0
    for it in items:
        if not it.get("expected_chunk_ids"):
            continue
        got = retriever(it["question"], k)
        hit = bool(set(got[:k]) & set(it["expected_chunk_ids"]))
        hits += hit
        rows.append({"id": it["id"], "hit": hit, "retrieved": got[:k], "expected": it["expected_chunk_ids"]})
    return {"recall_at_5": pct(hits, len(rows)), "misses": [r for r in rows if not r["hit"]]}


# ---------------- end to end ----------------

def infer_route(resp: dict) -> str:
    trace = " ".join(resp.get("trace", []))
    policy, price = "retrieval:" in trace, "price:" in trace
    if policy and price:
        return "mixed"
    if price:
        return "price"
    if policy:
        return "policy"
    return "unsupported"


def eval_api(items: list[dict], api: str, out_stem: Path) -> dict:
    import httpx

    rows, ragas = [], []
    with httpx.Client(base_url=api, timeout=120) as client:
        for it in items:
            profile = {f: it["profile"].get(f) for f in PROFILE_FIELDS}
            body = {"message": it["question"], "profile": profile}
            r = client.post("/chat", json=body)
            if r.status_code != 200:
                rows.append({"id": it["id"], "error": f"HTTP {r.status_code}"})
                continue
            resp = r.json()
            abstained = resp["status"] == "abstained"
            text = resp.get("message", "")
            row = {
                "id": it["id"], "category": it["category"], "status": resp["status"],
                "route": infer_route(resp), "expected_route": it["expected_route"],
                "unsafe": it["should_abstain"] and not abstained,
                "over_abstained": not it["should_abstain"] and abstained,
                "uncited": resp["status"] == "answered" and not resp.get("citations") and not resp.get("price_result"),
                "stale": bool(it.get("superseded_value")) and it["superseded_value"] in text,
                "has_current": (it["current_value"] in text) if it.get("current_value") else None,
            }
            rows.append(row)
            if resp["status"] == "answered":
                ragas.append({"id": it["id"], "question": it["question"], "answer": text,
                              "contexts": [c.get("text", "") for c in resp.get("citations", [])],
                              "ground_truth": it.get("expected_answer", "")})
    ok = [r for r in rows if "error" not in r]
    should_abstain = [r for r in ok if r["expected_route"] == "unsupported"]
    answerable = [r for r in ok if r["expected_route"] != "unsupported"]
    changed = [r for r in ok if r["category"] == "policy_changed"]
    ragas_path = out_stem.with_name(out_stem.name + "_ragas.jsonl")
    ragas_path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in ragas), encoding="utf-8")
    return {
        "routing_accuracy": pct(sum(r["route"] == r["expected_route"] for r in ok), len(ok)),
        "unsafe_answering": pct(sum(r["unsafe"] for r in should_abstain), len(should_abstain)),
        "over_abstention": pct(sum(r["over_abstained"] for r in answerable), len(answerable)),
        "uncited_answers": sum(r["uncited"] for r in ok),
        "staleness_errors": pct(sum(r["stale"] for r in changed), len(changed)),
        "http_errors": len(rows) - len(ok),
        "ragas_export": str(ragas_path.relative_to(ROOT)),
        "cases": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=["dev", "heldout", "all"], default="dev")
    ap.add_argument("--final", action="store_true", help="required to run the held-out split")
    ap.add_argument("--retriever", help="'bm25' (default) or module:function")
    ap.add_argument("--api", help="base URL of the backend, e.g. http://127.0.0.1:8000")
    args = ap.parse_args()
    if args.split in ("heldout", "all") and not args.final:
        raise SystemExit("Held-out questions are for final reported results only; add --final to confirm.")

    items = load_items(args.split)
    active = (ROOT / "data" / "policy_snapshots" / "ACTIVE").read_text(encoding="utf-8").strip()
    chunks = [json.loads(ln) for ln in (ROOT / "data" / "policy_chunks" / active / "chunks.jsonl")
              .read_text(encoding="utf-8").splitlines()]
    retriever, retriever_name = get_retriever(args.retriever, chunks)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    out_stem = out_dir / f"{stamp}_{args.split}"

    report = {"split": args.split, "questions": len(items), "snapshot": active, "retriever": retriever_name,
              "discovery": eval_discovery(items), "retrieval": eval_retrieval(items, retriever)}
    if args.api:
        report["end_to_end"] = eval_api(items, args.api, out_stem)
    out_stem.with_suffix(".json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"split={args.split}  questions={len(items)}  snapshot={active}")
    print(f"Discovery   precision {report['discovery']['precision']}  recall {report['discovery']['recall']}  "
          f"ask-next {report['discovery']['ask_next_accuracy']}")
    print(f"Retrieval   Recall@5 {report['retrieval']['recall_at_5']}  ({retriever_name})")
    if args.api:
        e = report["end_to_end"]
        print(f"End-to-end  routing {e['routing_accuracy']}  unsafe {e['unsafe_answering']}  "
              f"over-abstain {e['over_abstention']}  uncited {e['uncited_answers']}  stale {e['staleness_errors']}"
              f"  http-errors {e['http_errors']}")
    print(f"Report: {out_stem.with_suffix('.json').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
