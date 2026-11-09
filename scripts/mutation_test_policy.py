"""Curated policy/verifier fault injection, offline and standard-library only.

Run from the repository root with its Python environment. Mutates private copies,
never the working source. This measures the listed fault scenarios, not every
possible mutation, security risk or model response. No GPU or held-out data.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = "backend/kopi_keys/components/"
TESTS = ["test_synthesiser_verifier.py", "test_policy_finals.py", "test_policy_safety.py",
         "test_profile_scope.py", "test_graph.py", "test_verifier_relevance_wording.py", "test_finals_context_relevance.py"]
# One documented fault per case. Exact anchors make code drift fail visibly.
SPECS = [
    ("Missing citation accepted", COMPONENTS + "verifier.py",
     'if not citation_ids:', 'if False:'),
    ("Unknown citation accepted", COMPONENTS + "verifier.py",
     'errors.append(f"Unknown citation: {source_id}")', 'pass'),
    ("Superseded source accepted", COMPONENTS + "verifier.py",
     'errors.append(f"Superseded source: {source_id}")', 'pass'),
    ("Quote need not occur in source", COMPONENTS + "verifier.py",
     'if not any(quote in _comparable(p.text) for p in cited):', 'if False:'),
    ("Displayed wording may change the quote", COMPONENTS + "verifier.py",
     'if _comparable(claim.text) != _comparable(scope_label(claim.supporting_quote)):', 'if False:'),
    ("Assistant-control output allowed", COMPONENTS + "verifier.py",
     'if contains_model_instruction(claim.text) or contains_model_instruction(claim.supporting_quote or ""):', 'if False:'),
    ("Low-relevance quote accepted", COMPONENTS + "verifier.py",
     'if score["score"] < minimum and not table_row_answers_question(question, claims[score["claim_index"]]):',
     'if False:'),
    ("Table-row relevance rule accepts any row", COMPONENTS + "verifier.py",
     '    return criterion.strip().casefold() == "citizenship" and any(aspects.shows_aspect(aspect, criterion) for aspect in asked)',
     '    return True'),
    ("Named-scheme table rescue enabled", COMPONENTS + "verifier.py",
     'if requested_grants(question) or "loan" in asked:', 'if False:'),
    ("Multi-grant coverage check removed", COMPONENTS + "verifier.py",
     'errors.extend(grant_coverage_errors(question, draft.claims, sources))', 'pass'),
    ("Household scope check removed", COMPONENTS + "verifier.py",
     'errors.extend(household_scope_errors(state, sources))', 'pass'),
    ("Missing-evidence errors discarded", COMPONENTS + "verifier.py",
     'errors = list(state.synthesis_errors)', 'errors = []'),
    ("SQL value comparison removed", COMPONENTS + "verifier.py",
     'if actual != expected:', 'if False:'),
    ("Trailing numeric text accepted", COMPONENTS + "verifier.py",
     'match = pattern.fullmatch(line)', 'match = pattern.match(line)'),
    ("Duplicate statistic accepted", COMPONENTS + "verifier.py",
     'if label in seen:', 'if False:'),
    ("Missing statistic accepted", COMPONENTS + "verifier.py",
     'for missing in sorted(set(PATTERNS) - seen):', 'for missing in []:'),
    ("Second-timer EHG scope gate removed", COMPONENTS + "profile_context.py",
     'if state.subsidy_status == "second_timer":', 'if False:'),
    ("Mixed/single profile conflict ignored", COMPONENTS + "profile_context.py",
     'if profile.subsidy_status == "mixed" and (profile.household_type == "single" or profile.citizenship == "SC_single"):', 'if False:'),
    ("Specialised PDF scope ignored", COMPONENTS + "policy_guardrails.py",
     'if personal_question(question):', 'if False:'),
    ("Retry allowance exceeds proposal", "backend/kopi_keys/graph.py",
     'MAX_REPAIRS = 1', 'MAX_REPAIRS = 2'),
    ("Prompt text leaked to model trace", "backend/kopi_keys/llm.py",
     'return {"message_count": len(inputs.get("messages", [])), "content_redacted": True}',
     'return {"messages": inputs.get("messages", []), "content_redacted": False}'),
    ("Answer text leaked to model trace", "backend/kopi_keys/llm.py",
     'return {"usage": clean, "content_redacted": True}',
     'return {"usage": clean, "answer": getattr(output, "text", ""), "content_redacted": False}'),
]


def plan(root: Path = ROOT) -> list[dict]:
    result = []
    for index, (name, file, before, after) in enumerate(SPECS, 1):
        source = (root / file).read_text(encoding="utf-8")
        if source.count(before) != 1:
            raise ValueError(f"Mutation anchor changed or is ambiguous: {name} ({file})")
        ast.parse(source.replace(before, after, 1))
        result.append({"id": f"POL-MUT-{index:02d}", "name": name, "file": file,
                       "line": source[:source.index(before)].count("\n") + 1,
                       "before": before, "after": after})
    return result


def child_environment(work: Path) -> dict[str, str]:
    # Do not copy API keys, cloud credentials, proxy credentials or .env files.
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP",
               "LANG", "LC_ALL", "VIRTUAL_ENV"}
    env = {k: v for k, v in os.environ.items() if k.upper() in allowed}
    env.update(PYTHONPATH=str(work / "backend"), PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
               PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", LANGSMITH_TRACING="false",
               LANGCHAIN_TRACING_V2="false", KOPI_WARM_UP="0", KOPI_HELDOUT_DIR="",
               KOPI_OLLAMA_BASE_URL="http://127.0.0.1:1", KOPI_EMBED_BASE_URL="http://127.0.0.1:1")
    return env


def classify(code: int, junit: Path, expected_tests: int | None = None, *, network_attempted: bool = False) -> dict:
    if network_attempted:
        return {"status": "error", "detail": "Live HTTP attempted inside isolation; not counted as mutation detection"}
    if code not in (0, 1) or not junit.is_file():
        return {"status": "error", "detail": f"pytest exit {code}; no valid assertion result"}
    try:
        root = ET.parse(junit).getroot()
        cases = list(root.iter("testcase"))
        errors = list(root.iter("error"))
        failures = list(root.iter("failure"))
        skipped = list(root.iter("skipped"))
    except (ET.ParseError, OSError) as error:
        return {"status": "error", "detail": f"Invalid pytest report: {type(error).__name__}"}
    if errors or skipped or not cases or (expected_tests is not None and len(cases) != expected_tests):
        return {"status": "error", "detail": "Collection/setup error, skipped tests or changed test count"}
    failed = []
    for case in cases:
        failure = case.find("failure")
        if failure is None:
            continue
        reason = failure.get("message", "")
        failed.append({"test": f"{case.get('classname')}::{case.get('name')}", "reason": reason[:500],
                       "assertion_failure": reason.startswith(("assert ", "AssertionError", "Failed:"))})
    if code == 1 and failures and any(f["assertion_failure"] for f in failed):
        return {"status": "killed", "tests": len(cases), "failures": failed,
                "runtime_exception_failures": sum(not f["assertion_failure"] for f in failed)}
    if code == 1 and failures:
        return {"status": "error", "detail": "Only runtime exceptions; no assertion demonstrated detection", "failures": failed}
    if code == 0 and not failures:
        return {"status": "survived", "tests": len(cases), "failures": []}
    return {"status": "error", "detail": "Exit status and pytest report disagree"}


def execute(root: Path, parent: Path, mutation: dict | None, timeout: int, expected_tests=None) -> dict:
    parent = parent.resolve()
    with tempfile.TemporaryDirectory(prefix="case-", dir=parent) as temporary:
        work = Path(temporary).resolve()
        if not work.is_relative_to(parent):
            raise ValueError("Mutation workspace escaped its designated directory")
        shutil.copytree(root / "backend", work / "backend",
                        ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
        (work / "tests").mkdir()
        for name in [*TESTS, "fakes.py", "conftest.py"]:
            shutil.copy2(root / "tests" / name, work / "tests" / name)
        shutil.copytree(root / "tests/fixtures", work / "tests/fixtures")
        for name in ("schema", "topic_cards"):
            shutil.copytree(root / "data" / name, work / "data" / name)
        (work / "data/policy_snapshots").mkdir()
        shutil.copy2(root / "data/policy_snapshots/ACTIVE", work / "data/policy_snapshots/ACTIVE")
        active = (root / "data/policy_snapshots/ACTIVE").read_text().strip()
        if date.fromisoformat(active).isoformat() != active:
            raise ValueError("Invalid ACTIVE snapshot date")
        shutil.copytree(root / "data/policy_chunks" / active, work / "data/policy_chunks" / active)
        # Verify the child imported the private copy. Real HTTP transports are denied;
        # existing MockTransport/ASGI tests remain usable. No source/user data is fetched.
        with (work / "tests/conftest.py").open("a", encoding="utf-8") as handle:
            handle.write('''
import pytest
from pathlib import Path
import httpx
@pytest.fixture(autouse=True)
def _mutation_isolation(monkeypatch):
    from kopi_keys.components import verifier
    assert Path(verifier.__file__).resolve().is_relative_to(Path(__file__).resolve().parents[1])
    def deny(*args, **kwargs):
        (Path(__file__).resolve().parents[1] / "live-http-attempted").touch()
        raise RuntimeError("Live HTTP is disabled in policy mutation tests")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", deny)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", deny)
''')
        if mutation:
            target = work / mutation["file"]
            source = target.read_text(encoding="utf-8")
            target.write_text(source.replace(mutation["before"], mutation["after"], 1), encoding="utf-8")
        junit = work / "results.xml"
        command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                   f"--junitxml={junit}", *[f"tests/{name}" for name in TESTS]]
        try:
            done = subprocess.run(command, cwd=work, env=child_environment(work), timeout=timeout,
                                  capture_output=True, text=True, encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            if (work / "live-http-attempted").exists():
                return classify(-1, junit, network_attempted=True)
            return {"status": "timeout", "detail": f"Exceeded {timeout}s; not counted as killed"}
        result = classify(done.returncode, junit, expected_tests,
                          network_attempted=(work / "live-http-attempted").exists())
        if result["status"] == "error":
            result["diagnostic"] = (done.stdout + done.stderr)[-2500:]
        return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--jobs", type=int, choices=range(1, 5), default=2)
    ap.add_argument("--timeout", type=int, choices=range(1, 301), default=60)
    ap.add_argument("--json", type=Path, default=ROOT / ".local/reports/policy-mutations.json")
    args = ap.parse_args(argv)
    mutations = plan()
    if args.list:
        for item in mutations:
            print(f"{item['id']} {item['name']} ({item['file']}:{item['line']})")
        return 0
    output = args.json.resolve()
    if not output.is_relative_to(ROOT.resolve()):
        ap.error("Keep mutation reports inside this checkout")
    parent = ROOT / ".local/policy-mutation-work"
    parent.mkdir(parents=True, exist_ok=True)
    baseline = execute(ROOT, parent, None, args.timeout)
    baseline["status"] = "passed" if baseline["status"] == "survived" else "failed"
    report = {"scope": f"{len(mutations)} curated verifier/profile/trace fault scenarios; not a whole-project score",
              "generated_at": datetime.now(timezone.utc).isoformat(), "python": sys.version,
              "tests": TESTS, "baseline": baseline, "mutations": [],
              "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "test_sha256": {name: hashlib.sha256((ROOT / "tests" / name).read_bytes()).hexdigest()
                              for name in [*TESTS, "fakes.py", "conftest.py"]},
              "active_snapshot": (ROOT / "data/policy_snapshots/ACTIVE").read_text().strip(),
              "source_sha256": {file: hashlib.sha256((ROOT / file).read_bytes()).hexdigest()
                                for file in sorted({m['file'] for m in mutations})}}
    if baseline["status"] == "passed":
        print(f"Baseline: {baseline['tests']} tests passed", flush=True)
        def run(item):
            result = {**item, **execute(ROOT, parent, item, args.timeout, baseline["tests"])}
            print(f"{item['id']}: {result['status']} - {item['name']}", flush=True)
            return result
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            report["mutations"] = list(pool.map(run, mutations))
    killed = sum(m["status"] == "killed" for m in report["mutations"])
    survived = sum(m["status"] == "survived" for m in report["mutations"])
    errors = sum(m["status"] in {"error", "timeout"} for m in report["mutations"])
    report["summary"] = {"planned": len(mutations), "executed": len(report["mutations"]),
                         "killed": killed, "survived": survived, "errors_or_timeouts": errors,
                         "score": killed / (killed + survived) if killed + survived else None,
                         "complete": len(report["mutations"]) == len(mutations) and errors == 0}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2), flush=True)
    if baseline["status"] != "passed" or errors or not report["summary"]["complete"]:
        return 2
    return 1 if survived else 0


if __name__ == "__main__":
    raise SystemExit(main())
