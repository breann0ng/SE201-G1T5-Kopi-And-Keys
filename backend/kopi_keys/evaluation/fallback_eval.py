"""Score the router's LLM fallback on questions written for it (needs Ollama).

Usage (repo root, project venv):
    python -m kopi_keys.evaluation.fallback_eval              # rules + LLM fallback
    python -m kopi_keys.evaluation.fallback_eval --rules-only # the "before" picture

Questions: data/evaluation-data/fallback/fallback_questions.jsonl, kept apart from the dev
set because the router was tuned on the dev set. Groups:
  rescue        in scope, no rule matches: the fallback should route it
  decline       out of scope, no rule matches: must still be declined
  vague         should get a clarifying question, not a decline
  rule_decline  declined by a rule: the fallback must never be asked

Router only (no retrieval or answer), so a run takes about a minute on CPU.
Report: .local/reports/<time>_fallback.json (gitignored).
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from time import perf_counter

from ..components.intent_fallback import SCHEMA, LLMIntentClassifier
from ..components.query_router import route_query
from ..llm import OllamaEngine
from .dataset import DATA, ROOT
from .metrics import pct

FALLBACK_FILE = DATA / "evaluation-data" / "fallback" / "fallback_questions.jsonl"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rules-only", action="store_true", help="skip the LLM (no_match stays declined)")
    args = ap.parse_args()
    classifier = None if args.rules_only else LLMIntentClassifier(OllamaEngine().for_router(SCHEMA))
    questions = [json.loads(line) for line in FALLBACK_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]

    rows, by_group, seconds = [], defaultdict(list), []
    for q in questions:
        routed = route_query(q["question"], {})
        called = classifier is not None and routed.intent_source == "no_match"
        if called:
            started = perf_counter()
            decision = classifier.classify(q["question"])
            seconds.append(perf_counter() - started)
            routed = route_query(q["question"], {}, fallback=decision)
        ok = routed.route in q["accept_routes"]
        if q["group"] == "rule_decline":
            ok = ok and not called
        row = {"id": q["id"], "group": q["group"], "route": routed.route, "source": routed.intent_source,
               "accept": q["accept_routes"], "ok": ok}
        rows.append(row)
        by_group[q["group"]].append(ok)
        print(f"{'ok  ' if ok else 'FAIL'} {q['id']} {routed.route:8} {routed.intent_source:10} {q['question']}")

    summary = {group: pct(sum(oks), len(oks)) for group, oks in by_group.items()}
    report = {"mode": "rules-only" if args.rules_only else "hybrid", "summary": summary,
              "llm_calls": len(seconds),
              "llm_seconds_mean": round(sum(seconds) / len(seconds), 2) if seconds else None,
              "llm_seconds_max": round(max(seconds), 2) if seconds else None, "cases": rows}
    reports = ROOT / ".local" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    path = reports / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_fallback.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\n" + "  ".join(f"{group} {score}" for group, score in summary.items()))
    if seconds:
        print(f"LLM calls {len(seconds)}  mean {report['llm_seconds_mean']}s  max {report['llm_seconds_max']}s")
    print(f"Report: {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
