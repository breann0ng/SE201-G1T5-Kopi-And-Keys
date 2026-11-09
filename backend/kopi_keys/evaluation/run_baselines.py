"""Answer-level comparison on the DEV set: the full app vs the baselines (proposal 4.1).

Usage (repo root, project venv, Ollama running):
    python -m kopi_keys.evaluation.run_baselines --system no-tools
    python -m kopi_keys.evaluation.run_baselines --system naive-rag-dense
    python -m kopi_keys.evaluation.run_baselines --system naive-rag        # hybrid retrieval
    python -m kopi_keys.evaluation.run_baselines --system full             # the app, in-process

Every system gets the same questions and profiles. A question with a scripted
follow-up (turns: user, expected clarify, user) sends the second user turn with
the history: the full app only when it actually asked (status "clarifying"),
the baselines always (they never ask, so the reply arrives as extra context).
The final response of each question is scored by metrics.end_to_end.

Outputs go to data/evaluation-data/results/: <timestamp>_<system>_dev.jsonl (one
response per line, written as it goes, so a stopped run keeps its answers) and
<timestamp>_<system>_dev_metrics.json. Dev split only: there is no held-out option.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from time import perf_counter

from . import baselines, metrics
from .dataset import AS_OF, DATA, load_questions
from contextlib import nullcontext

RESULTS = DATA / "evaluation-data" / "results"
SYSTEM_NAMES = ("full", *baselines.SYSTEMS)


def user_turns(q: dict) -> list[str]:
    return [t["user"] for t in q["turns"] if "user" in t]


def _full_client():
    from fastapi.testclient import TestClient

    from ..main import app
    return TestClient(app)


def run_full(client, q: dict, *, as_of: str | None = None) -> dict:
    """Pin dates only for an in-process evaluation; HTTP clients cannot pin a remote server."""
    from ..schemas import BuyerProfile

    profile = {k: v for k, v in q["profile"].items() if k in BuyerProfile.model_fields}
    turns, history, resp = user_turns(q), [], {}
    started = perf_counter()
    initial_route = None
    with metrics.router_today(as_of) if as_of else nullcontext():
        for n, text in enumerate(turns):
            r = client.post("/chat", json={"message": text, "profile": profile, "history": history})
            if r.status_code != 200:
                return {"error": f"HTTP {r.status_code}: {r.text[:200]}"}
            resp = r.json()
            if n == 0:
                initial_route = resp.get("route")
            if resp.get("status") != "clarifying" or n + 1 == len(turns):
                break
            history += [{"role": "user", "content": text}, {"role": "assistant", "content": resp["message"]}]
    resp["latency_seconds"] = round(perf_counter() - started, 3)
    resp["turns_sent"] = n + 1
    resp["initial_route"] = initial_route
    resp["router_as_of"] = as_of
    return resp


def run_baseline(fn, q: dict) -> dict:
    turns, history, resp = user_turns(q), [], {}
    started = perf_counter()
    for text in turns:
        try:
            resp = fn(text, q["profile"], history)
        except Exception as error:  # e.g. index unavailable: score as an error, keep going
            return {"error": f"{type(error).__name__}: {error}"}
        if "error" in resp:
            return resp
        history += [{"role": "user", "content": text}, {"role": "assistant", "content": resp["message"]}]
    resp["latency_seconds"] = round(perf_counter() - started, 3)
    resp["turns_sent"] = len(turns)
    return resp


def run(system: str, limit: int | None = None) -> dict:
    questions = load_questions("dev")[:limit]
    stamp = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{system}_dev"
    RESULTS.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS / f"{stamp}.jsonl"
    client = _full_client() if system == "full" else None
    responses = {}
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        ctx = client if client is not None else _null()
        with ctx:
            for i, q in enumerate(questions, 1):
                resp = run_full(client, q, as_of=AS_OF) if client is not None else run_baseline(baselines.SYSTEMS[system], q)
                responses[q["id"]] = resp
                f.write(json.dumps({"id": q["id"], "category": q["category"], "question": q["question"],
                                    "system": system, "response": resp}, ensure_ascii=False, default=str) + "\n")
                f.flush()
                status = resp.get("error", resp.get("status"))
                print(f"[{i}/{len(questions)}] {q['id']} {status} {resp.get('latency_seconds', '')}s", flush=True)
    scored = metrics.end_to_end(questions, responses)
    scored.pop("ragas", None)
    lat = [r["latency_seconds"] for r in responses.values() if "latency_seconds" in r]
    scored["mean_latency_s"] = round(sum(lat) / len(lat), 2) if lat else None
    scored.update(system=system, questions=len(questions), responses_file=out_path.name,
                  router_as_of=AS_OF if system == "full" else None)
    (RESULTS / f"{stamp}_metrics.json").write_text(json.dumps(scored, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in scored.items() if k != "cases"}, indent=1))
    return scored


class _null:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--system", choices=SYSTEM_NAMES)
    ap.add_argument("--limit", type=int, help="first N dev questions only (smoke test)")
    args = ap.parse_args()
    if not args.system:
        ap.error("--system is required")
    run(args.system, args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
