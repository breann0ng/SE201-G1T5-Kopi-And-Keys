"""Build a session-only, checksum-verified evaluation handoff. No uploads."""
import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSION = ROOT / '.local/reports/final-dev-20261110'
DELIVERY = Path('C:/wamp64/www/SE201-G1T5-Kopi-And-Keys/.local/reports')
DELIVERY.mkdir(parents=True, exist_ok=True)


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


audit = read(SESSION / 'session-audit.json')
setup = read(SESSION / 'run-setup.json')
front = read(SESSION / 'frontend-checks.json')
safety = read(SESSION / 'policy-safety-live.json')
synthesis = read(SESSION / 'synthesis-final.json')
prices = read(SESSION / 'synthetic-price-live.json')
hybrid = read(SESSION / '14-fallback-hybrid.json')
rules = read(SESSION / '15-fallback-rules.json')
full = [r for r in audit['baseline_runs'] if r['system'] == 'full' and r['questions'] == 50]
assert len(full) == 2
assert not any(r['infrastructure_error_ids'] or r['errors'] for r in audit['baseline_runs'])
assert all(c['exit_code'] == 0 for c in front['checks'])
assert safety['completed'] and synthesis['completed']
assert len(audit['steps']) == 22 and all(m['exit_code'] == 0 for m in audit['steps'])
assert len(safety['records']) == 16 and len(synthesis['records']) == 12
assert len(prices['results']) == 6
required = [f'{n:02}' for n in range(1, 16)]
assert all(any(m['step'].startswith(n + '-') for m in audit['steps']) for n in required)

reproduce = SESSION / 'reproduce'
reproduce.mkdir(exist_ok=True)
for name in ['final-env.ps1', 'final-step.ps1', 'final-run-plan.json', 'collect_setup.py',
             'audit_final.py', 'package_final.py']:
    shutil.copy2(ROOT / '.local' / name, reproduce / name)

latencies = ', '.join(str(r['mean_latency_s']) + ' s' for r in full)
synth = synthesis['summary']['qwen2.5:3b']
failed_synth = ', '.join(r['case_id'] for r in synthesis['records'] if not r['quality_pass'])
main_steps = [m for m in audit['steps'] if m['step'] in ('06-full-run-1', '07-full-run-2')]
durations = ', '.join(str(m['elapsed_seconds']) + ' s' for m in main_steps)
summary = f'''KOPI & KEYS - FINAL DEVELOPMENT EVALUATION
Completed: {datetime.now(timezone.utc).isoformat()} (UTC)
Frozen main commit: {setup['commit']}

Completed all 15 Part 4 checklist steps, plus setup/sanity checks and frontend
tests, lint and production build. Production code and frozen data are unchanged.
No commits or pushes. No held-out access. No cloud judge or LangSmith uploads.

SETUP
Model: qwen2.5:3b, Q4_K_M, digest {setup['gpu_loaded_model']['digest']}
GPU Ollama: {setup['gpu_ollama_version']}; full GPU offload verified before and
after evaluation. Job 360625 on block; 24,192 MiB allocated MIG slice.
The user requested retaining the running allocation for the team's next test.
The private server remains running; the model has been unloaded from GPU memory.
Embeddings: local embeddinggemma, digest {setup['embedding_model']['digest']}
Snapshot: {setup['snapshot']}; complete index: 898/898 IDs matched.
Database: 242,737 rows, Jan 2017 to Oct 2026. Source data and DB hashes verified.
Sampling: temperature 0, seed 42. Evaluation router date pinned to October 2026.
Existing Python environment and matching-lockfile frontend package cache reused;
versions are recorded in run-setup.json and frontend-checks.json.

AUTOMATED CHECKS
Backend: 1100 passed (one expected missing-index warning).
Frontend: 32 passed; lint exit 0 (four React Refresh warnings); build exit 0
(existing large-bundle warning). No browser interaction/visual QA in this session.
Snapshot/card validation passed. Freshness: 6/6 passed on real date 10 Nov 2026.
Price fixtures: 6/6 input-validation checks and 6/6 live checks passed.
All 22 recorded command steps completed with exit 0, no transport retries.
Benchmark quality failures below are preserved even where a CLI exits 0.

FULL SYSTEM - TWO RUNS ON ALL 50 DEV QUESTIONS
Both runs: final route 47/50 (94%); initial route 49/50 (98%).
Both runs: 30 completed answers, 11 refusals and 1 clarification on the
42 answerable cases; all 8 should-abstain cases refused. Zero uncited answers.
Both runs: correct returned figures on 18/21 expected-price questions (85.7%).
Both runs: no run errors or engine-unavailable results.
Mean end-to-end latency: {latencies}; whole command durations: {durations}.
Status, route and price-result fields matched on all 50 questions. One displayed
answer (POL-04) differed in quote coverage; headline metric outcomes were identical.

BASELINES - SAME MODEL, GPU AND 50 DEV QUESTIONS
No tools: 26/42 answerable cases answered; 1/8 out-of-scope cases answered;
27 uncited answers; 0/21 correct price cases; mean latency 0.38 s.
Naive dense RAG: 26/42 answerable cases answered; 1/8 out-of-scope cases answered;
0 uncited answers; 0/21 correct price cases; mean latency 1.01 s.
See system-comparison.md for paired results and confidence intervals.
Baselines have no route output: their printed routing=0 is not an intent test.

RETRIEVAL / CARDS / SQL
Policy Recall@5 (22 policy questions): hybrid 74.2% strict / 83.3% relaxed;
BM25 53.0% strict; dense 67.4% strict. Hybrid still below the 85% Recall target.
Policy Hit@5 is different: hybrid 81.8% strict / 90.9% relaxed.
All required gold IDs exist in the complete index; poor rank/selection remains.
Component rules routing: 50/50. Price filters and SQL figures: each 23/23.
Suggested-card precision 14/26 (54%), recall 14/15 (93%). Shown-only 2/2 precision
has only 2/15 recall and must not be presented as overall precision.

SAFETY / SYNTHESIS / ROUTER FALLBACK
Synthetic safety suite: {safety['summary']['passes']}/16 passed; no availability
errors. Positive controls: 3/3. Answerable probes answered: 7/8; some cases allow
a safe refusal. This finite probe set is not a comprehensive security guarantee.
Fixed-evidence synthesis: {synth['quality_passes']}/12 automatic coverage/outcome
checks passed; failures: {failed_synth}. All three are refusals on answerable
cases. No engine errors. Median synthesis latency {synth['median_seconds']} s.
Hybrid router fallback: {sum(r['ok'] for r in hybrid['cases'])}/{len(hybrid['cases'])};
rules only: {sum(r['ok'] for r in rules['cases'])}/{len(rules['cases'])}.
Hybrid failures: FB-C02 (vague question routed as policy), FB-F01 (HDB opening
hours not declined). All 9 rescue cases and 10 rule-decline cases passed.

GAPS / REVIEW REQUIRED
Three current-policy questions (CHG-05/06/07) receive historical-only excerpts.
Source matching does not establish temporal applicability. Inspect the original
answers, not only the literal staleness score. This remains an unresolved concern.
Eleven answerable refusals include quote-matching and/or relevance failures.
SYN-03 misses singles grant-stacking coverage; SYN-06 and SYN-07 fail source-quote
matching. See dev-review.json, synthesis-final.json and REVIEW-NOTES.txt.
Human semantic review, held-out evaluation, and optional cloud judge remain undone.
Optional long mutation campaigns were not selected and were not run in this session.
No tuning or fixes were made in response to these results.

METRIC CAVEATS
answers_answerable=31/42 in the compare tool includes 1 clarification; completed
answers are 30/42. Raw price_figures=18/18 is conditional: overall is 18/21.
Staleness is a literal string screen, not an independently validated accuracy rate.
Citation presence does not establish correctness, relevance or complete conditions.
Latencies include laptop retrieval and SSH overhead; no controlled CPU/GPU speedup
comparison was performed. Small dev denominators limit generalisation.

FILES
Raw session results: results/ (only the 13 files produced by this session).
Diagnostics: dev-review.json; synthesis-final.json; policy-safety-live.json.
Comparisons: system-comparison*.md; retrieval-comparison*.md.
Reproducibility: run-setup.json; session-audit.json; per-step logs/metadata;
reproduce/ operational scripts. Source/data integrity: PASS, no tracked edits.
MANIFEST.json records every other packaged file's byte length and SHA-256.
This ZIP was created locally; it has not been sent to anyone or committed.
'''
(SESSION / 'SUMMARY.txt').write_text(summary, encoding='utf-8')
shutil.copy2(SESSION / 'SUMMARY.txt', DELIVERY / 'final-dev-20261110-summary.txt')

files = [p for p in sorted(SESSION.rglob('*')) if p.is_file() and p.name != 'MANIFEST.json']
for p in files:
    assert not p.is_symlink() and p.resolve().is_relative_to(SESSION.resolve())
    assert p.suffix.lower() in {'.json', '.jsonl', '.txt', '.xml', '.md', '.ps1', '.py'}
manifest = {'commit': setup['commit'], 'scope': 'development only; session outputs; no secrets or databases',
            'files': [{'path': p.relative_to(SESSION).as_posix(), 'bytes': p.stat().st_size,
                       'sha256': digest(p)} for p in files]}
(SESSION / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
archive = DELIVERY / 'final-dev-20261110-results.zip'
assert not archive.exists(), 'Preserve an existing delivery ZIP rather than overwriting it'
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
    for p in [*files, SESSION / 'MANIFEST.json']:
        z.write(p, p.relative_to(SESSION).as_posix())
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for entry in manifest['files']:
        assert hashlib.sha256(z.read(entry['path'])).hexdigest() == entry['sha256']
(DELIVERY / 'final-dev-20261110-results.zip.sha256').write_text(digest(archive) + '  ' + archive.name + '\n', encoding='utf-8')
print(json.dumps({'zip': str(archive), 'files': len(files) + 1, 'bytes': archive.stat().st_size,
                  'sha256': digest(archive), 'archive_verification': 'PASS',
                  'summary': str(DELIVERY / 'final-dev-20261110-summary.txt')}))
