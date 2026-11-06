"""Source blocks must retain the active snapshot; other failures stay failures."""

import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "scraping"))
import fetch
import refresh


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    root = tmp_path / "data" / "policy_snapshots"
    root.mkdir(parents=True)
    (root / "ACTIVE").write_text("2026-10-15\n", encoding="utf-8")
    folder = root / "2026-11-01"
    monkeypatch.setattr(fetch, "ROOT", tmp_path)
    monkeypatch.setattr(fetch, "SNAPSHOT_DATE", "2026-11-01")
    monkeypatch.setattr(fetch, "SNAP_DIR", folder)
    monkeypatch.setattr(fetch, "RAW_DIR", folder / "raw")
    monkeypatch.setattr(fetch, "LOG_PATH", folder / "fetch_log.json")
    monkeypatch.setattr(refresh, "REPORT_PATH", tmp_path / "report.json")
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "outputs"))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary"))
    return tmp_path


def robots_log(status=200, text="User-agent: *\nAllow: /\n"):
    folder = fetch.SNAP_DIR / "robots"
    folder.mkdir(parents=True)
    (folder / "hdb.gov.sg.txt").write_text(text, encoding="utf-8")
    log = fetch.load_log()
    log["robots"]["hdb.gov.sg"] = {"url": "https://www.hdb.gov.sg/robots.txt", "status": status}
    fetch.save_log(log)
    return log


@pytest.mark.parametrize("status", [401, 403, 429])
def test_inaccessible_robots_is_a_recorded_block_not_an_explicit_robots_rule(snapshot, monkeypatch, status):
    robots_log(status)
    monkeypatch.setattr(fetch, "get", lambda *args: pytest.fail("Must not fetch a blocked sitemap"))
    assert fetch.cli(["fetch.py", "sitemap", "https://www.hdb.gov.sg/sitemap.xml"]) == 2
    blocked = fetch.load_log()["blocked"]
    assert blocked["http_status"] == status
    assert blocked["url"].endswith("/robots.txt")
    assert "Cannot read robots.txt" in blocked["reason"]


@pytest.mark.parametrize("status", [None, 500])
def test_unavailable_robots_is_not_treated_as_permission_to_fetch(snapshot, status):
    log = robots_log(status)
    with pytest.raises(RuntimeError, match="Cannot verify robots.txt"):
        fetch.robots_allowed("https://www.hdb.gov.sg/sitemap.xml", log)


def test_robots_network_error_without_a_cached_body_remains_a_failure(snapshot):
    log = fetch.load_log()
    log["robots"]["hdb.gov.sg"] = {
        "url": "https://www.hdb.gov.sg/robots.txt", "status": None, "error": "connection failed",
    }
    with pytest.raises(RuntimeError, match="Cannot verify robots.txt"):
        fetch.robots_allowed("https://www.hdb.gov.sg/sitemap.xml", log)


def test_explicit_robots_disallow_stops_before_fetching_any_page(snapshot, monkeypatch):
    robots_log(text="User-agent: *\nDisallow: /\n")
    monkeypatch.setattr(fetch, "get", lambda *args: pytest.fail("Must respect robots rules"))
    assert fetch.cli(["fetch.py", "url", "example", "https://www.hdb.gov.sg/buying-a-flat/"]) == 2
    assert fetch.load_log()["blocked"]["reason"] == "Disallowed by robots.txt"
    assert not (fetch.RAW_DIR / "example.html").exists()


@pytest.mark.parametrize("kind", ["sitemap", "pdf", "url"])
@pytest.mark.parametrize("status", [403, 200])
def test_denial_or_html_challenge_is_never_saved_as_policy_content(snapshot, monkeypatch, kind, status):
    robots_log()
    monkeypatch.setattr(fetch, "get", lambda url, *args: httpx.Response(
        status, text="<html>Access denied</html>", headers={"content-type": "text/html"},
        request=httpx.Request("GET", url),
    ))
    args = ["fetch.py", kind]
    if kind != "sitemap":
        args.append("example")
    args.append("https://www.hdb.gov.sg/example")
    assert fetch.cli(args) == 2
    assert fetch.load_log()["blocked"]["http_status"] == status
    assert not list(fetch.SNAP_DIR.rglob("example.*"))
    assert not list((fetch.SNAP_DIR / "sitemaps").glob("*"))


@pytest.mark.parametrize("github_actions,exit_code", [(False, 2), (True, 0)])
def test_blocked_pipeline_stops_and_retains_active_snapshot(snapshot, monkeypatch, capsys, github_actions, exit_code):
    robots_log(403)
    assert fetch.cli(["fetch.py", "sitemap", "https://www.hdb.gov.sg/sitemap.xml"]) == 2
    called = []

    def run(*args):
        called.append(args)
        if args[1] == "sitemap":
            raise subprocess.CalledProcessError(2, [sys.executable, "fetch.py", *args[1:]])

    monkeypatch.setattr(refresh, "run", run)
    assert refresh.main(github_actions=github_actions) == exit_code
    report = json.loads(refresh.REPORT_PATH.read_text())
    assert report["outcome"] == "blocked"
    assert report["snapshot_ready"] is False
    assert report["blocked"]["http_status"] == 403
    assert len(called) == 2  # Stops before discovery, policy-page fetching and extraction.
    assert (snapshot / "data/policy_snapshots/ACTIVE").read_text() == "2026-10-15\n"
    assert not (fetch.SNAP_DIR / "manifest.json").exists()
    if github_actions:
        assert "outcome=blocked" in (snapshot / "outputs").read_text()
        assert "No new snapshot will be published" in (snapshot / "summary").read_text()
        assert "::notice title=Policy refresh blocked" in capsys.readouterr().out
    else:
        assert not (snapshot / "outputs").exists()


@pytest.mark.parametrize("script,code,record_block", [
    ("fetch.py", 1, True),
    ("extract.py", 2, True),
    ("fetch.py", 2, False),
])
def test_unexpected_script_failure_cannot_be_hidden_by_a_blocked_status(
    snapshot, monkeypatch, script, code, record_block,
):
    if record_block:
        log = fetch.load_log()
        log["blocked"] = {"reason": "A stale record must not hide unrelated failures"}
        fetch.save_log(log)

    def pipeline():
        raise subprocess.CalledProcessError(code, [sys.executable, script])

    monkeypatch.setattr(refresh, "pipeline", pipeline)
    assert refresh.main(github_actions=True) == 1
    report = json.loads(refresh.REPORT_PATH.read_text())
    assert report["outcome"] == "failed"
    assert report["snapshot_ready"] is False
    assert "outcome=failed" in (snapshot / "outputs").read_text()


def test_unexpected_python_error_still_fails(snapshot, monkeypatch):
    def pipeline():
        raise ValueError("broken extraction")

    monkeypatch.setattr(refresh, "pipeline", pipeline)
    assert refresh.main(github_actions=True) == 1
    assert json.loads(refresh.REPORT_PATH.read_text())["error"] == "broken extraction"


def test_fetcher_cannot_reuse_a_previous_block_to_hide_an_unrelated_exit_2(snapshot, monkeypatch):
    log = fetch.load_log()
    log["blocked"] = {"reason": "An earlier command was blocked"}
    fetch.save_log(log)

    def broken_command(argv):
        raise SystemExit(2)

    monkeypatch.setattr(fetch, "main", broken_command)
    with pytest.raises(SystemExit) as error:
        fetch.cli(["fetch.py", "seeds"])
    assert error.value.code == 2
    assert "blocked" not in fetch.load_log()


def test_completed_pipeline_is_the_only_publishable_outcome(snapshot, monkeypatch):
    monkeypatch.setattr(refresh, "pipeline", lambda: None)
    assert refresh.main(github_actions=True) == 0
    report = json.loads(refresh.REPORT_PATH.read_text())
    assert report["outcome"] == "ready"
    assert report["snapshot_ready"] is True
    assert "outcome=ready" in (snapshot / "outputs").read_text()
    assert (snapshot / "data/policy_snapshots/ACTIVE").read_text() == "2026-10-15\n"
