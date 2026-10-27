"""The benchmark isolates synthesis and separates coverage from human quality."""

import json

import pytest

from kopi_keys.components.policy_synthesis import PolicySummariser
from kopi_keys.evaluation.synthesis_benchmark import DEFAULT_CASES, load_cases, main, run_case, summarize
from kopi_keys.llm import Generation, ModelEngineError


class Engine:
    def __init__(self, *outputs): self.outputs = iter(outputs)
    def complete(self, messages):
        result = next(self.outputs)
        if isinstance(result, Exception): raise result
        return Generation(result, "fixture", {"output_tokens": 12})


def test_all_development_gold_quotes_resolve_against_fixed_evidence():
    data, cases = load_cases()
    assert len(cases) == 12
    assert "held-out" in data["purpose"]
    assert all(row["id"].startswith("SYN-") for row, _ in cases)
    assert main(["--validate-only"]) == 0


def test_benchmark_rejects_stale_snapshot_and_unresolvable_labels(tmp_path):
    data = json.loads(DEFAULT_CASES.read_text(encoding="utf-8"))
    path = tmp_path / "cases.json"
    data["snapshot_id"] = "old-snapshot"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="ACTIVE"): load_cases(path)
    data["snapshot_id"] = "2026-10-15"
    data["cases"][0]["required_quote_groups"] = [["An invented gold statement."]]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="Gold quote"): load_cases(path)


def test_a_verified_answer_can_fail_the_independent_coverage_label():
    _, cases = load_cases()
    row, state = next((r, s) for r, s in cases if r["id"] == "SYN-12")
    quote = "Have worked continuously for at least 12 months"
    result = run_case(row, state, PolicySummariser(Engine(json.dumps({"claims": [{
        "citation_id": "CHUNK_GRANTS_04", "supporting_quote": quote}]}))))
    assert result["status"] == "answered"
    assert not result["quality_pass"]  # Missing "working at the time" condition.
    assert result["human_review"]["condition_scope_0_to_2"] is None


def test_empty_answer_and_invented_citation_are_never_benchmark_successes():
    _, cases = load_cases()
    row, state = cases[0]
    result = run_case(row, state, PolicySummariser(Engine('{"claims": []}', '{"claims": []}')))
    assert result["status"] == "abstained" and not result["quality_pass"]
    assert len(result["attempts"]) == 2


def test_expected_abstention_and_engine_error_are_distinct():
    _, cases = load_cases()
    row, state = next((r, s) for r, s in cases if r["id"] == "SYN-10")
    refusal = '{"claims": [], "missing_evidence": ["EHG income rules"]}'
    good = run_case(row, state, PolicySummariser(Engine(refusal, refusal)))
    broken = run_case(row, state, PolicySummariser(Engine(ModelEngineError("offline"))))
    assert good["quality_pass"] and good["status"] == "abstained"
    assert not broken["quality_pass"] and broken["status"] == "engine_error"
    summary = summarize([{**r, "model": "fixture"} for r in (good, broken)])["fixture"]
    assert summary["cases"] == 2 and summary["quality_passes"] == 1
    assert summary["engine_errors"] == 1 and summary["model_calls"] == 3
    assert "not factual accuracy" in summary["human_quality_review"]


def test_cli_records_planned_runs_and_unloads_models_between_batches(monkeypatch, tmp_path):
    from kopi_keys.evaluation import synthesis_benchmark as benchmark
    events = []
    class LocalEngine:
        def __init__(self, settings): self.settings = settings
        def inspect(self):
            return {"installed_models": ["qwen2.5:3b", "qwen3:4b"], "version": "fixture"}
        def for_policy(self, schema, model_override=None): return self
        def warm_up(self): events.append(("warm", self.settings.model))
        def unload(self): events.append(("unload", self.settings.model))
        def complete(self, messages):
            return Generation('{"claims": [], "missing_evidence": ["No combination rule"]}', self.settings.model)
    monkeypatch.setattr(benchmark, "OllamaEngine", LocalEngine)
    path = tmp_path / "report.json"
    assert main(["--case-ids", "SYN-09", "--output", str(path)]) == 0
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["completed"] and report["planned_case_ids"] == ["SYN-09"]
    assert len(report["records"]) == 2 and all(r["quality_pass"] for r in report["records"])
    assert events[:2] == [("unload", "qwen3:4b"), ("warm", "qwen2.5:3b")]
    assert events[-1] == ("unload", "qwen3:4b")


def test_gpu_benchmark_stops_before_generation_when_runtime_falls_back_to_cpu(monkeypatch, tmp_path):
    from kopi_keys.evaluation import synthesis_benchmark as benchmark
    class CpuFallback:
        def __init__(self, settings): self.settings = settings
        def inspect(self): return {"installed_models": ["qwen2.5:3b"], "version": "fixture"}
        def for_policy(self, schema, model_override=None): return self
        def warm_up(self): pass
        def verify_gpu_loaded(self): raise ModelEngineError("No allocated GPU")
        def unload(self): pass
        def complete(self, messages): pytest.fail("GPU timing must not silently run on CPU")
    monkeypatch.setattr(benchmark, "OllamaEngine", CpuFallback)
    path = tmp_path / "gpu.json"
    assert main(["--models", "qwen2.5:3b", "--device", "gpu", "--output", str(path)]) == 1
    report = json.loads(path.read_text(encoding="utf-8"))
    assert not report["completed"] and report["setup_error"] == "No allocated GPU"
    assert report["records"] == []


def test_gpu_benchmark_records_real_offload_preflight(monkeypatch, tmp_path):
    from kopi_keys.evaluation import synthesis_benchmark as benchmark
    class Gpu:
        def __init__(self, settings): self.settings = settings
        def inspect(self): return {"installed_models": ["qwen2.5:3b"], "version": "fixture"}
        def for_policy(self, schema, model_override=None): return self
        def warm_up(self): pass
        def unload(self): pass
        def verify_gpu_loaded(self): return {"name": "qwen2.5:3b", "size_vram": 2000, "size": 2100}
        def complete(self, messages): return Generation('{"claims": []}', self.settings.model)
    monkeypatch.setattr(benchmark, "OllamaEngine", Gpu)
    path = tmp_path / "gpu.json"
    assert main(["--models", "qwen2.5:3b", "--device", "gpu", "--case-ids", "SYN-09", "--output", str(path)]) == 0
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["completed"] and report["settings"]["device"] == "gpu"
    assert report["gpu_load_checks"][0]["loaded_model"]["size_vram"] == 2000
