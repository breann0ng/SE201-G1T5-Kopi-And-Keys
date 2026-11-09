"""Download and validate INACTIVE price candidates. Never activate an app database."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from . import resale_db

ROOT = resale_db.ROOT
API = 'https://api-open.data.gov.sg/v1/public/api/datasets/' + resale_db.DEFAULT_DATASET_ID
CANDIDATES = ROOT / '.local/price-refresh'
STATUS_REPORT = ROOT / '.local/reports/price-refresh-status.json'
MAX_BYTES = 64 * 1024 * 1024
POLL_SECONDS = 15  # Public API quota: avoid a tight retry loop.
SGT = timezone(timedelta(hours=8))
ISSUE_TITLE = '[Price refresh] Candidate data or source check needs review'
ISSUE_MARKER = '<!-- kopi-price-refresh-v1 -->'


class WatchError(RuntimeError):
    def __init__(self, status: str, message: str):
        self.status = status
        super().__init__(message)


def _response_ok(response: httpx.Response, stage: str):
    if response.status_code in (401, 403, 429):
        raise WatchError('blocked', f'{stage}: access denied or rate limited (HTTP {response.status_code}).')
    if not 200 <= response.status_code < 300:
        raise WatchError('failed', f'{stage}: HTTP {response.status_code}; redirects are not followed.')


def _api_data(client: httpx.Client, action: str) -> dict:
    try:
        response = client.get(API + '/' + action, follow_redirects=False)
        _response_ok(response, action)
        if len(response.content) > 1024 * 1024:
            raise WatchError('failed', 'Download API returned an oversized response.')
        result = response.json()
    except (ValueError, TypeError):
        raise WatchError('failed', 'Download API returned invalid JSON.') from None
    if not isinstance(result, dict) or result.get('code') != 0 or not isinstance(result.get('data'), dict):
        raise WatchError('failed', 'Download API did not report success.')
    return result['data']


def _download_url(value: str) -> str:
    """Only the verified production dataset's official export bucket; no arbitrary URLs."""
    if not isinstance(value, str):
        raise WatchError('failed', 'Download API did not supply a URL.')
    try:
        u = urlsplit(value)
        port = u.port
    except ValueError:
        raise WatchError('failed', 'Download API supplied an invalid URL.') from None
    prefix = '/table-downloads-ingest.data.gov.sg/' + resale_db.DEFAULT_DATASET_ID + '/'
    if (u.scheme != 'https' or u.hostname != 's3.ap-southeast-1.amazonaws.com'
            or u.username or u.password or u.fragment or port not in (None, 443)
            or not u.path.startswith(prefix)):
        raise WatchError('failed', 'Download destination is outside the approved dataset export location.')
    return value


def download_csv(client: httpx.Client, path: Path, *, sleep=time.sleep, polls: int = 5):
    _api_data(client, 'initiate-download')
    url = None
    for _ in range(polls):
        sleep(POLL_SECONDS)
        data = _api_data(client, 'poll-download')
        if data.get('status') == 'DOWNLOAD_SUCCESS':
            url = _download_url(data.get('url'))
            break
        if data.get('status') in {'DOWNLOAD_FAILED', 'FAILED'}:
            raise WatchError('failed', 'Official dataset export failed.')
    if url is None:
        raise WatchError('incomplete', 'Official dataset export was not ready within the bounded polling window.')
    partial = path.with_suffix('.part')
    try:
        with client.stream('GET', url, follow_redirects=False) as response:
            _response_ok(response, 'CSV download')
            size = 0
            with partial.open('xb') as f:
                for block in response.iter_bytes():
                    size += len(block)
                    if size > MAX_BYTES:
                        raise WatchError('incomplete', 'CSV exceeded the candidate download size limit.')
                    f.write(block)
        if size == 0:
            raise WatchError('incomplete', 'Downloaded CSV was empty.')
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)


def _content_hash(rows: Counter) -> str:
    """Normalised row multiset; row reordering is not a change. Duplicates still count."""
    digest = hashlib.sha256()
    for row, count in sorted(rows.items()):
        digest.update(json.dumps([row, count], ensure_ascii=False, separators=(',', ':')).encode())
        digest.update(b'\n')
    return digest.hexdigest()


def _stats(rows: Counter) -> dict:
    months = Counter()
    for row, count in rows.items():
        months[row[0]] += count
    return {'row_count': sum(rows.values()), 'duplicate_rows': sum(n - 1 for n in rows.values()),
            'min_month': min(months), 'max_month': max(months), 'rows_by_month': dict(sorted(months.items())),
            'content_sha256': _content_hash(rows)}


def watch(client: httpx.Client, *, baseline_csv: Path = resale_db.DEFAULT_CSV,
          candidate_root: Path = CANDIDATES, now: datetime | None = None, sleep=time.sleep) -> dict:
    now = (now or datetime.now(SGT)).astimezone(SGT)
    candidate_id = now.strftime('%Y%m%dT%H%M%S') + '-' + uuid4().hex[:8]
    folder = Path(candidate_root).resolve() / candidate_id
    folder.mkdir(parents=True, exist_ok=False)  # Never overwrite a pending candidate.
    report = {'version': 1, 'outcome': 'failed', 'checked_at': now.isoformat(),
              'dataset_id': resale_db.DEFAULT_DATASET_ID, 'source_url': resale_db.DEFAULT_SOURCE_URL,
              'candidate_id': candidate_id, 'candidate_directory': str(folder),
              'activation': 'manual_review_required', 'active_data_modified': False}
    try:
        baseline_csv = Path(baseline_csv).resolve()
        baseline = Counter(resale_db.read_rows(baseline_csv, now.date()))
        report['baseline'] = {**_stats(baseline), 'file_sha256': resale_db.sha256(baseline_csv)}
        csv_path = folder / 'resale.csv'
        download_csv(client, csv_path, sleep=sleep)
        candidate = Counter(resale_db.read_rows(csv_path, now.date()))
        report['candidate'] = {**_stats(candidate), 'file_sha256': resale_db.sha256(csv_path),
                               'downloaded_on': now.date().isoformat()}
        old, new = report['baseline'], report['candidate']
        if new['min_month'] != old['min_month'] or new['max_month'] < old['max_month']:
            raise WatchError('incomplete', 'Candidate coverage regressed; investigate a partial or wrong export.')
        report['comparison'] = {'added_rows': sum((candidate - baseline).values()),
                                'removed_rows': sum((baseline - candidate).values()),
                                'note': 'No unit identifier: corrections cannot reliably be distinguished from removals/additions.'}
        db_path = folder / 'hdb_prices.db'
        metadata = resale_db.build(csv_path, db_path, downloaded_on=now.date(), today=now.date())
        with sqlite3.connect(db_path.resolve().as_uri() + '?mode=ro', uri=True) as db:
            integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
            count = db.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
        if integrity != 'ok' or count != metadata['row_count']:
            raise WatchError('incomplete', 'Candidate database integrity or row count check failed.')
        report['candidate_database'] = {'integrity': integrity, 'row_count': count,
                                         'source_sha256': metadata['source_sha256']}
        report['outcome'] = 'unchanged' if old['content_sha256'] == new['content_sha256'] else 'changed'
    except WatchError as error:
        report.update(outcome=error.status, reason=str(error))
    except (resale_db.DataValidationError, UnicodeError):
        report.update(outcome='incomplete', reason='CSV validation failed; inspect the candidate locally. Active data retained.')
    except httpx.HTTPError:
        # Do not write signed download URLs or authentication material to logs/artifacts.
        report.update(outcome='failed', reason='Source request failed or timed out; active data retained.')
    except (OSError, sqlite3.Error, ValueError):
        report.update(outcome='failed', reason='Local validation or candidate build failed; active data retained.')
    (folder / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def notify(report: dict, client: httpx.Client, repository: str, run_url: str):
    """One open attention issue; later runs add review links, never activate data."""
    if report['outcome'] == 'unchanged':
        return
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Invalid GitHub repository name')
    if not run_url.startswith(f'https://github.com/{repository}/actions/runs/'):
        raise ValueError('Invalid Actions run URL')
    comparison = report.get('comparison', {})
    body = (f"{ISSUE_MARKER}\n\nPrice source check: **{report['outcome']}**.\n\n"
            f"[Review this run and download its candidate artifact]({run_url}).\n\n"
            f"Candidate: `{report['candidate_id']}`. Added rows: {comparison.get('added_rows', 'n/a')}; "
            f"removed rows: {comparison.get('removed_rows', 'n/a')}.\n\n"
            "The active CSV/database and evaluation labels were not changed. Review provenance, coverage, "
            "corrections/removals and price regression checks before separate manual activation. "
            "A blocked or incomplete check is not evidence that the current data is fresh. "
            "Keep evaluation data frozen; close this issue only after reviewing outstanding candidates.")
    found = client.get('https://api.github.com/search/issues', params={
        'q': f'repo:{repository} is:issue is:open in:title "[Price refresh]"', 'per_page': 50})
    found.raise_for_status()
    result = found.json()
    if not isinstance(result, dict) or not isinstance(result.get('items'), list) or result.get('incomplete_results'):
        raise ValueError('GitHub issue search did not return a complete result')
    existing = None
    for item in result['items']:
        if not isinstance(item, dict) or not isinstance(item.get('body') or '', str):
            raise ValueError('GitHub issue search returned an invalid issue')
        if ISSUE_MARKER in (item.get('body') or ''):
            if type(item.get('number')) is not int or item['number'] <= 0:
                raise ValueError('GitHub issue search returned an invalid issue number')
            existing = item
            break
    if existing:
        response = client.post(f"https://api.github.com/repos/{repository}/issues/{existing['number']}/comments", json={'body': body})
    else:
        response = client.post(f'https://api.github.com/repos/{repository}/issues', json={'title': ISSUE_TITLE, 'body': body})
    response.raise_for_status()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-csv', type=Path, default=resale_db.DEFAULT_CSV)
    parser.add_argument('--notify', action='store_true', help='Publish a review notification on GitHub (Actions only).')
    args = parser.parse_args(argv)
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        report = watch(client, baseline_csv=args.baseline_csv)
    if args.notify:
        repository = os.environ.get('GITHUB_REPOSITORY', '')
        run = os.environ.get('GITHUB_RUN_ID', '')
        token = os.environ.get('GH_TOKEN', '')
        try:
            if not token or not run.isdigit():
                raise ValueError('Actions notification configuration missing')
            with httpx.Client(headers={'Authorization': 'Bearer ' + token,
                                       'Accept': 'application/vnd.github+json'}, timeout=20, follow_redirects=False) as client:
                notify(report, client, repository, f'https://github.com/{repository}/actions/runs/{run}')
        except (httpx.HTTPError, ValueError):
            report['notification_error'] = 'GitHub notification failed; inspect this workflow and its artifacts.'
    STATUS_REPORT.parent.mkdir(parents=True, exist_ok=True)
    STATUS_REPORT.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    folder = Path(report['candidate_directory'])
    (folder / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as f:
            f.write(f"outcome={report['outcome']}\ncandidate_id={report['candidate_id']}\n")
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as f:
            f.write(f"### Price refresh: {report['outcome']}\n\nCandidate only. Active data was not changed. "
                    "Inspect price-refresh-status.json and any review issue before manual activation.\n")
    print(f"Price refresh: {report['outcome']}. Active CSV/database unchanged.")
    print(f'Report: {STATUS_REPORT}')
    return 0 if report['outcome'] in {'changed', 'unchanged'} and not report.get('notification_error') else 1


if __name__ == '__main__':
    raise SystemExit(main())
