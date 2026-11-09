"""Candidate-only refresh boundaries, using fictional rows and mocked HTTP."""
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sqlite3

import httpx
import pytest

from kopi_keys.ingest import price_watch as watcher, resale_db

NOW = datetime(2026, 11, 9, 4, tzinfo=timezone.utc)
URL = ('https://s3.ap-southeast-1.amazonaws.com/table-downloads-ingest.data.gov.sg/'
       + resale_db.DEFAULT_DATASET_ID + '/resale.csv?signature=TEST-SIGNED-URL-DO-NOT-LOG')
ROW = dict(month='2025-01', town='TAMPINES', flat_type='4 ROOM', block='101',
           street_name='TAMPINES ST 11', storey_range='04 TO 06', floor_area_sqm='92',
           flat_model='Model A', lease_commence_date='1985', remaining_lease='59 years', resale_price='500000')


def csv_bytes(rows):
    f = io.StringIO(newline='')
    writer = csv.DictWriter(f, fieldnames=resale_db.CSV_COLUMNS)
    writer.writeheader(); writer.writerows(rows)
    return f.getvalue().encode()


def setup(tmp_path, baseline=None):
    source = tmp_path / 'active.csv'
    source.write_bytes(csv_bytes(baseline if baseline is not None else [ROW]))
    db = tmp_path / 'active.db'
    resale_db.build(source, db, today=NOW.date())
    return source, db


def client_for(content, *, api_status=201, export_url=URL, download_status=200, polls=None, calls=None):
    polls = iter(polls or ['DOWNLOAD_SUCCESS'])
    def handler(request):
        if calls is not None:
            calls.append(request)
        if request.url.path.endswith('initiate-download'):
            return httpx.Response(api_status, json={'code': 0, 'data': {'message': 'started'}})
        if request.url.path.endswith('poll-download'):
            return httpx.Response(201, json={'code': 0, 'data': {'status': next(polls), 'url': export_url}})
        return httpx.Response(download_status, content=content, headers={'Location': 'https://unapproved.example/redirect'})
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def run(tmp_path, content, baseline=None, **kwargs):
    source, db = setup(tmp_path, baseline)
    original_csv, original_db = source.read_bytes(), db.read_bytes()
    with client_for(content, **kwargs) as client:
        result = watcher.watch(client, baseline_csv=source, candidate_root=tmp_path / 'candidates', now=NOW, sleep=lambda _: None)
    assert source.read_bytes() == original_csv
    assert db.read_bytes() == original_db
    return result


def test_new_rows_build_valid_inactive_database_and_keep_active_data(tmp_path):
    report = run(tmp_path, csv_bytes([ROW, {**ROW, 'month': '2025-02', 'resale_price': '600000'}]))
    assert report['outcome'] == 'changed'
    assert report['comparison']['added_rows'] == 1 and report['comparison']['removed_rows'] == 0
    assert report['active_data_modified'] is False and report['activation'] == 'manual_review_required'
    folder = Path(report['candidate_directory'])
    with sqlite3.connect(folder / 'hdb_prices.db') as db:
        assert db.execute('select count(*) from transactions').fetchone()[0] == 2
        assert db.execute('select downloaded_on from import_metadata').fetchone()[0] == '2026-11-09'
    assert report['candidate_database']['integrity'] == 'ok'
    assert 'TEST-SIGNED-URL' not in json.dumps(report)


def test_reordering_is_unchanged_but_duplicates_are_counted(tmp_path):
    other = {**ROW, 'block': '102', 'resale_price': '600000'}
    report = run(tmp_path, csv_bytes([other, ROW, ROW]), baseline=[ROW, ROW, other])
    assert report['outcome'] == 'unchanged'
    assert report['baseline']['file_sha256'] != report['candidate']['file_sha256']
    assert report['candidate']['row_count'] == 3 and report['candidate']['duplicate_rows'] == 1


def test_adding_a_duplicate_is_a_real_count_change(tmp_path):
    report = run(tmp_path, csv_bytes([ROW, ROW]))
    assert report['outcome'] == 'changed' and report['comparison']['added_rows'] == 1
    assert report['candidate']['duplicate_rows'] == 1


def test_corrections_are_reported_as_added_and_removed_not_guessed_updates(tmp_path):
    report = run(tmp_path, csv_bytes([{**ROW, 'resale_price': '510000'}]))
    assert report['outcome'] == 'changed'
    assert report['comparison']['added_rows'] == report['comparison']['removed_rows'] == 1


@pytest.mark.parametrize('status', [401, 403, 429])
def test_blocked_api_retains_active_database(tmp_path, status):
    report = run(tmp_path, csv_bytes([ROW]), api_status=status)
    assert report['outcome'] == 'blocked' and 'candidate_database' not in report


@pytest.mark.parametrize('content', [b'', b'<html>not a csv</html>', csv_bytes([{**ROW, 'resale_price': '-1'}]),
                                    csv_bytes([{**ROW, 'month': '2027-01'}])])
def test_empty_or_invalid_candidate_never_becomes_a_valid_database(tmp_path, content):
    report = run(tmp_path, content)
    assert report['outcome'] == 'incomplete'
    assert not (Path(report['candidate_directory']) / 'hdb_prices.db').exists()


def test_lost_month_coverage_is_incomplete(tmp_path):
    report = run(tmp_path, csv_bytes([ROW]), baseline=[ROW, {**ROW, 'month': '2025-02'}])
    assert report['outcome'] == 'incomplete' and 'coverage regressed' in report['reason']


@pytest.mark.parametrize('url', [
    'http://s3.ap-southeast-1.amazonaws.com/not-secure',
    'https://unapproved.example/resale.csv',
    URL.replace('table-downloads-ingest.data.gov.sg', 'untrusted-bucket'),
    URL.replace(resale_db.DEFAULT_DATASET_ID, 'd_some_other_dataset'),
    URL.replace('s3.ap-southeast-1.amazonaws.com', 's3.ap-southeast-1.amazonaws.com.evil.example'),
    URL.replace('https://', 'https://user:password@'),
    URL + '#fragment', URL.replace('.com/', '.com:bad/'),
])
def test_export_destination_is_validated_before_fetch(tmp_path, url):
    calls = []
    report = run(tmp_path, csv_bytes([ROW]), export_url=url, calls=calls)
    assert report['outcome'] == 'failed'
    assert len(calls) == 2 and all(r.url.host == 'api-open.data.gov.sg' for r in calls)


def test_file_redirect_is_not_followed(tmp_path):
    calls = []
    report = run(tmp_path, b'redirect', download_status=302, calls=calls)
    assert report['outcome'] == 'failed'
    assert not any(r.url.host == 'unapproved.example' for r in calls)


def test_api_redirect_is_not_followed(tmp_path):
    calls = []
    report = run(tmp_path, b'ignored', api_status=302, calls=calls)
    assert report['outcome'] == 'failed' and len(calls) == 1


def test_bounded_polling_waits_without_a_tight_retry_loop(tmp_path):
    source, _ = setup(tmp_path)
    delays, calls = [], []
    with client_for(csv_bytes([ROW]), polls=['DOWNLOAD_IN_PROGRESS'] * 5, calls=calls) as client:
        report = watcher.watch(client, baseline_csv=source, candidate_root=tmp_path / 'candidates', now=NOW, sleep=delays.append)
    assert report['outcome'] == 'incomplete' and delays == [15] * 5
    assert len(calls) == 6  # initiate plus five bounded polls


def test_oversized_file_is_rejected_and_partial_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(watcher, 'MAX_BYTES', 10)
    report = run(tmp_path, csv_bytes([ROW]))
    assert report['outcome'] == 'incomplete'
    assert not list(Path(report['candidate_directory']).glob('*.part'))


def test_network_error_report_does_not_expose_signed_url(tmp_path):
    source, db = setup(tmp_path)
    def handler(request):
        raise httpx.ConnectError('TEST-SECRET-DO-NOT-LOG', request=request)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        report = watcher.watch(client, baseline_csv=source, candidate_root=tmp_path / 'candidates', now=NOW, sleep=lambda _: None)
    assert report['outcome'] == 'failed' and 'TEST-SECRET' not in json.dumps(report)


def test_candidate_build_failure_leaves_active_database_intact(tmp_path, monkeypatch):
    source, db = setup(tmp_path); before = db.read_bytes()
    def fail(*args, **kwargs): raise OSError('simulated disk failure')
    monkeypatch.setattr(resale_db, 'build', fail)
    with client_for(csv_bytes([ROW])) as client:
        report = watcher.watch(client, baseline_csv=source, candidate_root=tmp_path / 'candidates', now=NOW, sleep=lambda _: None)
    assert report['outcome'] == 'failed' and db.read_bytes() == before


def test_repeated_checks_preserve_previous_candidate(tmp_path):
    source, _ = setup(tmp_path)
    with client_for(csv_bytes([ROW])) as client:
        first = watcher.watch(client, baseline_csv=source, candidate_root=tmp_path / 'candidates', now=NOW, sleep=lambda _: None)
    first_path = Path(first['candidate_directory']) / 'report.json'; original = first_path.read_bytes()
    with client_for(csv_bytes([ROW, ROW])) as client:
        second = watcher.watch(client, baseline_csv=source, candidate_root=tmp_path / 'candidates', now=NOW, sleep=lambda _: None)
    assert first['candidate_id'] != second['candidate_id'] and first_path.read_bytes() == original


@pytest.mark.parametrize('existing', [False, True])
def test_notification_creates_one_attention_issue_then_adds_review_links(existing):
    requests = []
    def handler(request):
        requests.append(request)
        if request.method == 'GET':
            return httpx.Response(200, json={'items': [{'number': 12, 'body': watcher.ISSUE_MARKER}] if existing else []})
        return httpx.Response(201, json={'number': 12})
    report = {'outcome': 'changed', 'candidate_id': '20261109-test', 'comparison': {'added_rows': 2, 'removed_rows': 0}}
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        watcher.notify(report, client, 'example/project', 'https://github.com/example/project/actions/runs/123')
    assert len(requests) == 2
    assert requests[-1].url.path.endswith('/12/comments' if existing else '/issues')
    assert 'active CSV/database' in json.loads(requests[-1].content)['body']


def test_unchanged_does_not_close_or_replace_pending_review_issue():
    def forbidden(request): pytest.fail('Unchanged checks must not modify pending review issues')
    with httpx.Client(transport=httpx.MockTransport(forbidden)) as client:
        watcher.notify({'outcome': 'unchanged'}, client, 'example/project', 'https://github.com/example/project/actions/runs/123')


@pytest.mark.parametrize('payload', [[], {'items': None}, {'items': [], 'incomplete_results': True},
                                    {'items': [None]}, {'items': [{'body': watcher.ISSUE_MARKER, 'number': '../bad'}]}])
def test_incomplete_or_invalid_issue_search_does_not_publish_duplicate_notification(payload):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=payload)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client, pytest.raises(ValueError):
        watcher.notify({'outcome': 'changed', 'candidate_id': 'test'}, client,
                       'example/project', 'https://github.com/example/project/actions/runs/123')
    assert len(requests) == 1


def test_notification_failure_still_writes_diagnostic_and_candidate_output(tmp_path, monkeypatch):
    folder = tmp_path / 'candidate'; folder.mkdir()
    report = {'outcome': 'changed', 'candidate_directory': str(folder), 'candidate_id': 'test-candidate'}
    monkeypatch.setattr(watcher, 'watch', lambda *a, **kw: dict(report))
    monkeypatch.setattr(watcher, 'STATUS_REPORT', tmp_path / 'reports/status.json')
    monkeypatch.delenv('GH_TOKEN', raising=False)
    monkeypatch.setenv('GITHUB_OUTPUT', str(tmp_path / 'outputs'))
    monkeypatch.setenv('GITHUB_STEP_SUMMARY', str(tmp_path / 'summary'))
    assert watcher.main(['--notify']) == 1
    assert json.loads(watcher.STATUS_REPORT.read_text())['notification_error']
    assert json.loads((folder / 'report.json').read_text())['outcome'] == 'changed'
    assert 'outcome=changed' in (tmp_path / 'outputs').read_text()


@pytest.mark.parametrize('body', [b'not-json', b'[]', b'{"code":0,"data":null}'])
def test_malformed_download_api_is_a_failed_check_without_export_fetch(tmp_path, body):
    source, _ = setup(tmp_path)
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=body)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        report = watcher.watch(client, baseline_csv=source, candidate_root=tmp_path / 'candidates', now=NOW)
    assert report['outcome'] == 'failed' and len(calls) == 1
