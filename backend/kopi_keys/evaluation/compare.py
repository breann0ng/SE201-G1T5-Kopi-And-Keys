"""Paired comparison of systems on the same DEV questions, with 95% CIs and McNemar p.

Usage (repo root, project venv; no Ollama needed, it only reads result files):
    python -m kopi_keys.evaluation.compare RESULT [RESULT ...] [--out table.md]

RESULT is a file in data/evaluation-data/results/ (name or path):
- answer level: <ts>_<system>_dev_metrics.json from run_baselines
- retrieval:    <ts>_retrieval_<mode>_..._dev.json from retrieval_report
Don't mix the two kinds in one call. The first RESULT is the reference: every
other system is compared with it question by question.

Every metric is a success rate over a population fixed by the labels, so all
systems are scored on the same questions (a run error counts as a failure):
  answer level: correct route (all), safe on should-abstain questions, answers
  answerable questions, answered with a citation (answerable), current figure not
  stale (policy_changed), correct price figures (questions with expected prices).
  retrieval: Hit@5 per question, per slice. --relaxed scores retrieval reports with
  accepted_evidence.json (report["relaxed"]), strict otherwise.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import stats
from .dataset import DATA, load_questions

RESULTS = DATA / "evaluation-data" / "results"


def _load(name: str) -> dict:
    path = Path(name)
    if not path.exists():
        path = RESULTS / name
    data = json.loads(path.read_text(encoding="utf-8"))
    data["_file"] = path.name
    return data


def answer_outcomes(metrics: dict, questions: list[dict]) -> dict[str, dict[str, bool]]:
    """metric -> {question id: success} from an end_to_end metrics file."""
    cases = {c["id"]: c for c in metrics["cases"]}
    out: dict[str, dict[str, bool]] = {k: {} for k in (
        "routing", "safe_when_should_abstain", "answers_answerable", "cited_answer", "not_stale", "price_correct")}
    for q in questions:
        c = cases.get(q["id"]) or {"error": "missing"}
        err = "error" in c
        out["routing"][q["id"]] = not err and c["route"] == c["expected_route"]
        if q["should_abstain"]:
            out["safe_when_should_abstain"][q["id"]] = not err and not c["unsafe"]
        else:
            out["answers_answerable"][q["id"]] = not err and not c["over_abstained"]
            out["cited_answer"][q["id"]] = not err and c["status"] == "answered" and not c["uncited"]
        if q["category"] == "policy_changed":
            out["not_stale"][q["id"]] = not err and not c["stale"]
        if q.get("expected_price") and q["expected_price"].get("volume"):
            out["price_correct"][q["id"]] = not err and c.get("price_ok") is True
    return out


def retrieval_outcomes(report: dict) -> dict[str, dict[str, bool]]:
    rows = report["cases"]
    hit = lambda r: r["found_at_5"] > 0  # noqa: E731
    return {
        "hit@5 all": {r["id"]: hit(r) for r in rows},
        "hit@5 policy": {r["id"]: hit(r) for r in rows if r["category"] != "discovery"},
        "hit@5 discovery": {r["id"]: hit(r) for r in rows if r["category"] == "discovery"},
    }


def label(result: dict) -> str:
    return result.get("system") or f"{result.get('mode', '?')} ({result['_file'][:16]})"


def table(results: list[dict], relaxed: bool = False) -> str:
    retrieval = "mode" in results[0]
    if relaxed:
        if not retrieval or any("relaxed" not in r for r in results):
            raise SystemExit("--relaxed needs retrieval reports that include relaxed scores")
        results = [{**r["relaxed"], "mode": r["mode"] + " relaxed", "_file": r["_file"]} for r in results]
    if any(("mode" in r) != retrieval for r in results):
        raise SystemExit("mix of retrieval and answer-level files: compare one kind at a time")
    questions = None if retrieval else load_questions("dev")
    outcomes = [retrieval_outcomes(r) if retrieval else answer_outcomes(r, questions) for r in results]
    names = [label(r) for r in results]
    lines = ["| metric | " + " | ".join(names) + " |", "|---" * (len(names) + 1) + "|"]
    for metric in outcomes[0]:
        cells = []
        for o in outcomes:
            d = o[metric]
            cells.append(stats.rate(sum(d.values()), len(d)))
        lines.append(f"| {metric} | " + " | ".join(cells) + " |")
    lines += ["", f"Paired vs **{names[0]}** (exact McNemar, two-sided; only questions where the two differ count):", "",
              "| metric | system | n | only ref right | only system right | p |", "|---|---|---|---|---|---|"]
    for metric in outcomes[0]:
        for name, o in zip(names[1:], outcomes[1:]):
            p = stats.paired(outcomes[0][metric], o[metric])
            lines.append(f"| {metric} | {name} | {p['n']} | {p['only_a']} | {p['only_b']} | {p['p']:.3g} |")
    lines += ["", "Files: " + ", ".join(r["_file"] for r in results)]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", nargs="+")
    ap.add_argument("--out", help="also write the Markdown table here")
    ap.add_argument("--relaxed", action="store_true", help="retrieval: score with accepted_evidence.json")
    args = ap.parse_args()
    md = table([_load(r) for r in args.results], relaxed=args.relaxed)
    print(md)
    if args.out:
        Path(args.out).write_text(md + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
