"""Collect final-run setup and assert the runbook's frozen inputs; no cloud calls."""
import hashlib
import inspect
import json
import os
import platform
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import httpx
from kopi_keys.components import policy_index
from kopi_keys.llm import OllamaEngine

root = Path(__file__).resolve().parents[1]
reports = root / '.local/reports/final-dev-20261110'
reports.mkdir(parents=True, exist_ok=True)
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
assert commit == '1c4d87c0ad8afc0ecc3bb2afed942eec1fd159eb'
assert Path(inspect.getfile(OllamaEngine)).resolve().is_relative_to(root / 'backend')
dev_hash = sha(root / 'data/evaluation-data/development/dev_set_questions.jsonl')
assert dev_hash.upper().startswith('F64FE3ABF1023821')
snapshot = (root / 'data/policy_snapshots/ACTIVE').read_text().strip()
assert snapshot == '2026-10-15'
chunks = [json.loads(line) for line in (root / f'data/policy_chunks/{snapshot}/chunks.jsonl').read_text(encoding='utf-8').splitlines()]
collection = policy_index.open_collection(snapshot)
assert len(chunks) == collection.count() == 898
assert set(collection.get(include=['metadatas'])['ids']) == {c['chunk_id'] for c in chunks}

db_path = root / 'data/processed/hdb_prices.db'
with sqlite3.connect(db_path.resolve().as_uri() + '?mode=ro', uri=True) as connection:
    db = dict(zip(('rows', 'min_month', 'max_month', 'source_sha256', 'downloaded_on'),
        connection.execute('SELECT row_count,min_month,max_month,source_sha256,downloaded_on FROM import_metadata').fetchone()))
    actual_count = connection.execute('SELECT count(*) FROM transactions').fetchone()[0]
assert db['rows'] == actual_count == 242737 and db['min_month'] == '2017-01' and db['max_month'] == '2026-10'
assert db['source_sha256'].startswith('248694f3cf7cc07e') and db['downloaded_on'] == '2026-10-14'
with httpx.Client(trust_env=False, timeout=10) as client:
    embed_tags = client.get('http://127.0.0.1:11434/api/tags').raise_for_status().json()['models']
    embed_model = next(m for m in embed_tags if m['name'] == 'embeddinggemma:latest')
    local_version = client.get('http://127.0.0.1:11434/api/version').raise_for_status().json()['version']
    gpu_version = client.get('http://127.0.0.1:11437/api/version').raise_for_status().json()['version']
assert embed_model['digest'].startswith('85462619ee72')
engine = OllamaEngine().for_policy({})
engine.warm_up()
loaded = engine.verify_gpu_loaded()
assert loaded['name'] == 'qwen2.5:3b' and loaded['digest'].startswith('357c53fb659c')
assert loaded['size'] == loaded['size_vram'] > 0
tracked_changes = subprocess.check_output(['git', 'diff', '--name-only', 'HEAD'], cwd=root, text=True).splitlines()
assert not tracked_changes, tracked_changes
packages = json.loads(subprocess.check_output([sys.executable, '-m', 'pip', 'list', '--format=json'], text=True))
data_files = [root / 'data/evaluation-data/development/dev_set_questions.jsonl',
              root / 'data/policy_snapshots/ACTIVE', root / f'data/policy_chunks/{snapshot}/chunks.jsonl',
              root / f'data/policy_index/{snapshot}/vectors.json', root / f'data/policy_index/{snapshot}/vectors.f32',
              *sorted((root / f'data/topic_cards/{snapshot}').glob('*.json'))]
report = {'commit': commit, 'collected_at_utc': datetime.now(timezone.utc).isoformat(),
    'runner': 'Nisha; assisted execution', 'python': sys.version, 'platform': platform.platform(),
    'logical_cpus': os.cpu_count(), 'packages': packages, 'python_module': inspect.getfile(OllamaEngine),
    'gpu_job': '360625', 'compute_host': 'block', 'allocated_gpu': 'MIG-992565c1-1e43-5cf5-bc6f-af258abd8b75',
    'gpu_ollama_version': gpu_version, 'gpu_loaded_model': loaded,
    'local_ollama_version': local_version, 'embedding_model': {k: embed_model[k] for k in ('name','digest','size')},
    'database': {**db, 'sha256': sha(db_path)}, 'snapshot': snapshot, 'index_count': collection.count(),
    'data_sha256': {str(p.relative_to(root)): sha(p) for p in data_files},
    'source_sha256': {str(p.relative_to(root)): sha(p) for p in sorted((root / 'backend/kopi_keys').rglob('*.py'))},
    'configuration': {k: os.environ.get(k) for k in ('KOPI_OLLAMA_BASE_URL','KOPI_EMBED_BASE_URL',
        'KOPI_OLLAMA_MODEL','KOPI_POLICY_MODEL','KOPI_ROUTER_MODEL','KOPI_OLLAMA_DEVICE',
        'KOPI_ASPECT_CHECK','KOPI_ASPECT_LABEL','KOPI_POLICY_MIN_RELEVANCE','LANGSMITH_TRACING','LANGCHAIN_TRACING_V2')},
    'sampling': {'temperature': 0, 'seed': 42},
    'notes': ['Existing Python environment reused with explicit pinned backend path; no dependency updates.',
        'GPU tunnel uses local port 11437 to avoid obsolete tunnels.',
        'Only this session output folder and its explicit result manifest will be packaged.',
        'Held-out not accessed; optional cloud judge not selected.']}
(reports / 'run-setup.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'setup': 'PASS', 'commit': commit, 'db_rows': actual_count, 'snapshot': snapshot,
    'index_count': collection.count(), 'model': loaded['name'], 'digest': loaded['digest'],
    'size': loaded['size'], 'size_vram': loaded['size_vram'], 'ollama_version': gpu_version}))
