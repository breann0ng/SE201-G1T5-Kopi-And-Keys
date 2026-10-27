"""CPU/GPU model comparison with fixed evidence; never reads the held-out dataset.

python -m kopi_keys.evaluation.synthesis_benchmark --models qwen2.5:3b qwen3:4b
"""

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from ..components.policy_retrieval import KeywordPolicyRetriever
from ..components.policy_synthesis import PolicySummariser
from ..components.verifier import policy_relevance_scores, verified_claim_subset, verify
from ..llm import ModelEngineError, OllamaEngine, OllamaSettings
from ..schemas import Draft
from ..state import GraphState


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CASES = ROOT / "data" / "benchmarks" / "synthesis_cases.json"


def load_cases(path: Path = DEFAULT_CASES):
    data = json.loads(path.read_text(encoding="utf-8"))
    retriever = KeywordPolicyRetriever()
    if data["snapshot_id"] != retriever.snapshot:
        raise ValueError("Benchmark labels need review against the ACTIVE snapshot before running.")
    seen, cases = set(), []
    for row in data["cases"]:
        if row["id"] in seen:
            raise ValueError("Duplicate synthesis case ID.")
        seen.add(row["id"])
        passages = retriever.get(row["chunk_ids"])
        if {p.id for p in passages} != set(row["chunk_ids"]):
            raise ValueError(f"Missing benchmark source for {row['id']}")
        if row["expected"] not in {"answered", "abstained"}:
            raise ValueError("Expected outcome must be answered or abstained.")
        for alternatives in row["required_quote_groups"]:
            if not alternatives or not any(any(_normal(q) in _normal(p.text) for p in passages) for q in alternatives):
                raise ValueError(f"Gold quote group does not occur in evidence: {row['id']}")
        cases.append((row, GraphState(message=row["question"], route="policy", passages=passages, **row["profile"])))
    if not cases:
        raise ValueError("The synthesis benchmark needs at least one labelled case.")
    return data, cases


def _normal(text):
    return " ".join(text.split()).casefold()


def run_case(row: dict, state: GraphState, summariser: PolicySummariser, max_repairs=1):
    started, attempts, final = perf_counter(), [], state
    for attempt in range(max_repairs + 1):
        try:
            claims, generation, validation_errors = summariser.generate(final)
        except ModelEngineError as error:
            attempts.append({"usage": {}, "raw_output": None, "verification_errors": [str(error)],
                             "relevance_scores": [], "engine_error": str(error)})
            return {"case_id": row["id"], "category": row["category"], "expected": row["expected"],
                    "status": "engine_error", "error": str(error), "quality_pass": False,
                    "elapsed_seconds": round(perf_counter() - started, 3), "attempts": attempts}
        final = final.model_copy(update={"draft": Draft(kind="answer", claims=claims),
                                         "synthesis_errors": validation_errors})
        errors = verify(final)
        original_errors, dropped = list(errors), 0
        if errors:
            trimmed = verified_claim_subset(final)
            if trimmed is not None:
                dropped = len(final.draft.claims) - len(trimmed.claims)
                final = final.model_copy(update={"draft": trimmed})
                errors = verify(final)
        attempts.append({"model": generation.model, "usage": generation.usage, "raw_output": generation.text,
                         "verification_errors": errors, "original_verification_errors": original_errors,
                         "claims_dropped": dropped, "relevance_scores": policy_relevance_scores(final)})
        final = final.model_copy(update={"verification_errors": errors})
        if not errors:
            break
    status = "answered" if not errors else "abstained"
    quotes = "\n".join(c.supporting_quote or "" for c in final.draft.claims) if status == "answered" else ""
    group_matches = [any(_normal(q) in _normal(quotes) for q in group) for group in row["required_quote_groups"]]
    quality_pass = status == row["expected"] and (status != "answered" or all(group_matches))
    return {"case_id": row["id"], "category": row["category"], "expected": row["expected"], "status": status,
            "quality_pass": quality_pass, "required_quote_groups_matched": group_matches,
            "elapsed_seconds": round(perf_counter() - started, 3), "attempts": attempts,
            "answer": "\n\n".join(f"{c.text} [{', '.join(c.citation_ids)}]" for c in final.draft.claims)
                      if status == "answered" else "",
            "human_review": {"condition_scope_0_to_2": None, "grant_logic_0_to_2": None,
                             "relevance_0_to_2": None, "clarity_0_to_2": None, "notes": ""}}


def summarize(records):
    result = {}
    for model in dict.fromkeys(r["model"] for r in records):
        rows = [r for r in records if r["model"] == model]
        latency = sorted(r["elapsed_seconds"] for r in rows)
        attempts = [a for r in rows for a in r["attempts"]]
        result[model] = {
            "cases": len(rows), "quality_passes": sum(r["quality_pass"] for r in rows),
            "answered": sum(r["status"] == "answered" for r in rows),
            "correct_abstentions": sum(r["expected"] == "abstained" and r["status"] == "abstained" for r in rows),
            "engine_errors": sum(r["status"] == "engine_error" for r in rows),
            "median_seconds": round(statistics.median(latency), 3),
            "p95_seconds": latency[max(0, math.ceil(len(latency) * 0.95) - 1)],
            "model_calls": len(attempts),
            "first_attempt_verifier_passes": sum(bool(r["attempts"]) and not r["attempts"][0]["verification_errors"] for r in rows),
            "raw_first_attempt_passes": sum(bool(r["attempts"]) and not r["attempts"][0].get(
                "original_verification_errors", r["attempts"][0]["verification_errors"]) for r in rows),
            "answers_after_claim_pruning": sum(r["status"] == "answered" and any(
                a.get("claims_dropped", 0) for a in r["attempts"]) for r in rows),
            "answerable_cases": sum(r["expected"] == "answered" for r in rows),
            "over_abstentions": sum(r["expected"] == "answered" and r["status"] == "abstained" for r in rows),
            "output_tokens": sum(a["usage"].get("output_tokens") or 0 for a in attempts),
            "human_quality_review": "pending; automatic quote coverage is not factual accuracy",
        }
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", default=["qwen2.5:3b", "qwen3:4b"])
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--case-ids", nargs="+")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--device", choices=["cpu", "gpu"], help="Override KOPI_OLLAMA_DEVICE; CPU remains the default.")
    parser.add_argument("--timeout", type=float, default=240)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    data, cases = load_cases(args.cases)
    if args.case_ids:
        unknown = set(args.case_ids) - {r["id"] for r, _ in cases}
        if unknown: parser.error("Unknown case IDs: " + ", ".join(sorted(unknown)))
        cases = [(r, s) for r, s in cases if r["id"] in args.case_ids]
    if args.validate_only:
        print(f"Validated {len(cases)} fixed-evidence synthesis development cases.")
        return 0
    # Benchmark prompts/evidence should remain local unless tracing is explicitly
    # enabled by the caller; do not load a developer's .env or hidden test data.
    settings = OllamaSettings.from_env()
    settings = replace(settings, num_threads=args.threads, timeout_seconds=args.timeout,
                       device=args.device or settings.device)
    inspector = OllamaEngine(settings)
    try:
        installation = inspector.inspect()
    except ModelEngineError as error:
        parser.error(str(error))
    missing = set(args.models) - set(installation["installed_models"])
    if missing: parser.error("Pull these models before benchmarking: " + ", ".join(sorted(missing)))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output or ROOT / ".local" / "reports" / f"{stamp}_synthesis_benchmark.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    records = []
    source_hash = hashlib.sha256(args.cases.read_bytes()).hexdigest()
    passages = {p.id: p.model_dump(mode="json") for _, s in cases for p in s.passages}
    evidence_hash = hashlib.sha256(json.dumps(passages, sort_keys=True).encode()).hexdigest()
    report = {"benchmark": data["name"], "scope": data["purpose"], "created_at_utc": stamp,
              "planned_models": args.models, "planned_case_ids": [r["id"] for r, _ in cases],
              "repeats": args.repeats, "completed": False,
              "snapshot_id": data["snapshot_id"], "cases_sha256": source_hash, "evidence_sha256": evidence_hash,
              "host": {"os": platform.platform(), "cpu": platform.processor(), "logical_cpus": os.cpu_count()},
              "settings": {**asdict(settings), "response_format": "request-specific citation enum",
                           "policy_context_size": 4096, "policy_output_token_cap": 850,
                           "num_gpu": 0 if settings.device == "cpu" else "automatic offload",
                           "temperature": 0, "seed": 42, "max_repairs": 1,
                           "minimum_relevance": float(os.getenv("KOPI_POLICY_MIN_RELEVANCE", "0.20")),
                           "memory_policy": "other compared models unloaded before each batch; active model unloaded after batch",
                           "warmup": "one unscored policy-budget load before each model batch"},
              "ollama_version": installation["version"], "gpu_load_checks": [], "records": records, "summary": {}}
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for repeat in range(args.repeats):
        # Reverse model order on alternate repeats to reduce order effects.
        for model in (args.models if repeat % 2 == 0 else list(reversed(args.models))):
            # A previous model's keep-alive must not consume RAM during the next
            # model's timings. This matters especially on laptops with shared RAM.
            for other in set(args.models) - {model}:
                OllamaEngine(replace(settings, model=other)).unload()
            engine = OllamaEngine(replace(settings, model=model))
            summariser = PolicySummariser(engine, model_override=model)
            print(f"Loading {model} on {settings.device.upper()} ({args.threads} CPU threads)...", flush=True)
            try:
                engine.for_policy({}, model_override=model).warm_up()
                if settings.device == "gpu":
                    report["gpu_load_checks"].append({"model": model, "repeat": repeat + 1,
                                                      "loaded_model": engine.verify_gpu_loaded()})
            except ModelEngineError as error:
                report["setup_error"] = str(error)
                try:
                    engine.unload()
                except ModelEngineError as cleanup_error:
                    report["cleanup_error"] = str(cleanup_error)
                output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                print(f"Setup failed: {error}", flush=True)
                return 1
            for row, state in cases:
                print(f"{model} / {row['id']} ...", flush=True)
                result = {"model": model, "repeat": repeat + 1, **run_case(row, state, summariser)}
                records.append(result)
                report["summary"] = summarize(records)
                output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                print(f"  {result['status']}, coverage check {'PASS' if result['quality_pass'] else 'FAIL'}, "
                      f"{result['elapsed_seconds']}s", flush=True)
            engine.unload()
    report["completed"] = True
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
