"""Session-only packaging/audit helper; does not call models or change app files."""
import collections
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from kopi_keys.evaluation.compare import answer_outcomes
from kopi_keys.evaluation.dataset import load_questions

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / '.local/reports/final-dev-20261110'
RESULTS = ROOT / 'data/evaluation-data/results'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


setup = read(REPORTS / 'run-setup.json')
commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
changes = subprocess.check_output(['git', 'diff', '--name-only', 'HEAD'], cwd=ROOT, text=True).splitlines()
hash_changes = [name for name, expected in {**setup['data_sha256'], **setup['source_sha256']}.items()
                if not (ROOT / name).exists() or sha(ROOT / name) != expected]
db_changed = sha(ROOT / 'data/processed/hdb_prices.db') != setup['database']['sha256']
assert commit == setup['commit'] and not changes and not hash_changes and not db_changed

metas = [read(p) for p in sorted(REPORTS.glob('*-attempt-*.meta.json'))]
assert all(m['status'] == 'finished' for m in metas), 'A step is still running'
destination = REPORTS / 'results'
destination.mkdir(exist_ok=True)
new_names = sorted({name for m in metas for name in m.get('new_result_files', [])})
for name in new_names:
    assert Path(name).name == name
    shutil.copy2(RESULTS / name, destination / name)

questions = load_questions('dev')
baseline_runs = []
for name in new_names:
    if not name.endswith('_dev_metrics.json'):
        continue
    metrics = read(RESULTS / name)
    rows = [json.loads(line) for line in (RESULTS / metrics['responses_file']).read_text(encoding='utf-8').splitlines()]
    infrastructure = [r['id'] for r in rows if r['response'].get('error') or
                      'engine_unavailable' in json.dumps(r['response'].get('trace', []))]
    assert len(rows) == metrics['questions']
    pop = questions[:metrics['questions']]
    outcomes = answer_outcomes(metrics, pop)
    baseline_runs.append({'file': name, 'system': metrics['system'], 'questions': len(rows),
        'statuses': dict(collections.Counter(r['response'].get('status', 'error') for r in rows)),
        'mean_latency_s': metrics['mean_latency_s'], 'errors': metrics['errors'],
        'infrastructure_error_ids': infrastructure,
        'fixed_population_scores': {key: {'success': sum(v.values()), 'total': len(v)} for key, v in outcomes.items()},
        'over_abstention_ids': [r['id'] for r in metrics['cases'] if r.get('over_abstained')],
        'unsafe_ids': [r['id'] for r in metrics['cases'] if r.get('unsafe')],
        'staleness_screen_ids': [r['id'] for r in metrics['cases'] if r.get('stale')],
        'uncited_answers': metrics['uncited_answers']})

review = read(REPORTS / 'dev-review.json')
review_issues = []
for row in review['cases']:
    response = row['response']
    if response.get('status') != 'answered' or any(a.get('verification_errors') for a in row.get('attempts', [])):
        review_issues.append({'id': row['id'], 'status': response.get('status'), 'error': response.get('error'),
            'trace': response.get('trace', []),
            'attempts': [{'verification_errors': a.get('verification_errors'),
                          'synthesis_errors': a.get('synthesis_errors'),
                          'relevance_scores': a.get('relevance_scores'),
                          'retrieved_ids': a.get('retrieved_ids')} for a in row.get('attempts', [])]})

full_runs = [r for r in baseline_runs if r['system'] == 'full' and r['questions'] == 50]
variation = None
if len(full_runs) == 2:
    data = []
    for run in full_runs:
        metrics = read(RESULTS / run['file'])
        data.append({r['id']: r['response'] for r in [json.loads(line) for line in
                    (RESULTS / metrics['responses_file']).read_text(encoding='utf-8').splitlines()]})
    variation = {key: [qid for qid in data[0] if data[0][qid].get(key) != data[1][qid].get(key)]
                 for key in ('status', 'route', 'message', 'price_result')}

audit = {'created_at_utc': datetime.now(timezone.utc).isoformat(), 'commit': commit,
    'integrity': {'tracked_changes': changes, 'input_or_source_hash_changes': hash_changes,
                  'database_changed': db_changed},
    'steps': metas, 'result_files': new_names, 'baseline_runs': baseline_runs,
    'full_repeat_differences': variation,
    'dev_review': {'completed': review['completed'], 'cases': len(review['cases']),
                   'metrics': {k: v for k, v in review['metrics'].items() if k != 'cases'},
                   'issues': review_issues, 'independent_human_review': 'pending'},
    'interpretation_limits': [
        'answers_answerable means not abstained; it includes clarifying responses. See status counts.',
        'price_correct uses the fixed 21 expected-price cases; price_figures in original output is conditional on returned figures.',
        'Baselines do not emit router labels; their zero routing score is not a comparison of intent classifiers.',
        'Staleness is a literal string screen, including dated qualifications; cohort/context review remains pending.',
        'Citation presence is not proof of relevance or factual correctness; human semantic review remains pending.',
        'Safety results cover finite synthetic development probes, not a guarantee against all attacks.',
        'Latency is end-to-end with laptop retrieval and SSH overhead; no controlled CPU-versus-GPU experiment was run.',
        'Held-out data and cloud judge were not accessed; no tuning, production code edits, commits or pushes.']}
(REPORTS / 'session-audit.json').write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'integrity': 'PASS', 'completed_steps': len(metas), 'copied_result_files': len(new_names),
                  'baseline_runs': len(baseline_runs), 'full_repeat_differences': variation,
                  'dev_review_cases': len(review['cases']),
                  'infrastructure_error_count': sum(len(r['infrastructure_error_ids']) for r in baseline_runs)}))
