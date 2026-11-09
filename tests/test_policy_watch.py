"""Exercise the real watcher against temporary snapshots; no web or GitHub writes."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/policy_watch.py"
spec = importlib.util.spec_from_file_location("policy_watch", SCRIPT)
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    active = tmp_path / "data/policy_snapshots/ACTIVE"
    active.parent.mkdir(parents=True)
    active.write_text("2026-10-15\n")
    write(tmp_path / ".local/reports/policy-refresh-status.json", {
        "date": "2026-11-09", "active_snapshot": "2026-10-15", "outcome": "ready",
        "snapshot_ready": True, "checked_at": "2026-11-09T02:17:00+00:00",
    })
    folder = tmp_path / "data/policy_snapshots/2026-11-09"
    write(folder / "manifest.json", {"snapshot_date": "2026-11-09", "pages": [{
        "slug": "hdb-ehg", "http_status": 200, "method": "trafilatura", "word_count": 12,
    }]})
    (folder / "clean").mkdir()
    (folder / "clean/hdb-ehg.md").write_text("Source: https://www.hdb.gov.sg/example\nPolicy text.")
    write(folder / "verification.json", {"hdb-ehg": {"missing_from_clean": []}})
    write(folder / "changes_since_2026-10-15.json", {
        "old": "2026-10-15", "new": "2026-11-09", "changed": [], "added": [],
        "removed": [], "status_changed": [], "unchanged": 1,
    })
    write(tmp_path / "scripts/scraping/seeds.json", [{"slug": "hdb-ehg"}])
    write(tmp_path / "scripts/scraping/pdf_seeds.json", [])
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/project")
    monkeypatch.setenv("POLICY_DEFAULT_BRANCH", "main")
    monkeypatch.setenv("GITHUB_RUN_ID", "1234")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    return tmp_path


def change(root, relative, **updates):
    path = root / relative
    data = watch.read_json(path)
    data.update(updates)
    write(path, data)


STATUS = ".local/reports/policy-refresh-status.json"
FOLDER = "data/policy_snapshots/2026-11-09/"


def test_complete_unchanged_check_has_no_network_or_publication(candidate, monkeypatch):
    monkeypatch.setattr(watch, "run", lambda *args: pytest.fail("Local check must not use git/gh"))
    assert watch.main(root=candidate) == 0
    report = watch.read_json(candidate / ".local/reports/policy-watch-status.json")
    assert report["status"] == "unchanged"
    assert report["source_checked_at"] == "2026-11-09T02:17:00+00:00"
    assert (candidate / "data/policy_snapshots/ACTIVE").read_text() == "2026-10-15\n"


@pytest.mark.parametrize("kind", watch.CHANGE_KEYS)
def test_wording_addition_removal_and_redirect_changes_all_require_review(candidate, kind):
    change(candidate, FOLDER + "changes_since_2026-10-15.json", **{kind: [{"slug": "hdb-ehg"}]})
    assert watch.inspect(candidate)["status"] == "changed"


def test_access_block_is_not_unchanged_or_publishable(candidate):
    change(candidate, STATUS, outcome="blocked", snapshot_ready=False,
           blocked={"http_status": 403, "url": "https://www.hdb.gov.sg/robots.txt"})
    report = watch.inspect(candidate)
    assert report["status"] == "blocked"
    assert report["detail"]["http_status"] == 403
    assert "counts" not in report


@pytest.mark.parametrize("relative", [STATUS, FOLDER + "manifest.json", FOLDER + "verification.json",
                                       FOLDER + "changes_since_2026-10-15.json"])
def test_missing_evidence_fails_closed(candidate, relative):
    (candidate / relative).unlink()
    assert watch.inspect(candidate)["status"] == "failed"


@pytest.mark.parametrize("field,value", [("http_status", 404), ("word_count", 0), ("method", None)])
def test_bad_page_requires_attention(candidate, field, value):
    manifest = watch.read_json(candidate / (FOLDER + "manifest.json"))
    manifest["pages"][0][field] = value
    write(candidate / (FOLDER + "manifest.json"), manifest)
    assert watch.inspect(candidate)["status"] == "incomplete"


def test_missing_seed_pdf_or_clean_file_cannot_be_silent(candidate):
    write(candidate / "scripts/scraping/pdf_seeds.json", [{"slug": "missing-pdf"}])
    (candidate / (FOLDER + "clean/hdb-ehg.md")).unlink()
    report = watch.inspect(candidate)
    assert report["status"] == "incomplete"
    assert report["detail"]["pages"] == ["hdb-ehg", "missing-pdf"]


def test_missing_extracted_figures_hold_candidate_for_review(candidate):
    write(candidate / (FOLDER + "verification.json"), {"hdb-ehg": {"missing_from_clean": ["$9,000"]}})
    report = watch.inspect(candidate)
    assert report["status"] == "incomplete"
    assert report["figure_warnings"] == ["hdb-ehg"]


@pytest.mark.parametrize("updates", [{"active_snapshot": "2026-09-01"}, {"date": "../elsewhere"},
                                      {"date": "2026-10-15"}, {"snapshot_ready": False},
                                      {"outcome": "failed", "error": "extraction failed"}])
def test_wrong_baseline_unsafe_date_or_failed_pipeline_never_publishes(candidate, updates):
    change(candidate, STATUS, **updates)
    assert watch.inspect(candidate)["status"] == "failed"


def fake_commands(monkeypatch, *, pending=None, issues=None, staged=""):
    calls = []

    def fake(root, *args):
        calls.append(args)
        if args[:3] == ("gh", "pr", "list"):
            return json.dumps(pending or [])
        if args[:3] == ("gh", "issue", "list"):
            return json.dumps(issues or [])
        if args[:4] == ("git", "diff", "--cached", "--name-only"):
            return staged
        if args[:3] == ("gh", "pr", "create"):
            return "https://github.com/example/project/pull/42"
        if args[:3] == ("gh", "issue", "create"):
            return "https://github.com/example/project/issues/43"
        return ""

    monkeypatch.setattr(watch, "run", fake)
    return calls


def test_changed_candidate_prepares_only_draft_pr_and_allowed_paths(candidate, monkeypatch):
    change(candidate, FOLDER + "changes_since_2026-10-15.json", changed=[{"slug": "hdb-ehg"}])
    calls = fake_commands(monkeypatch)
    assert watch.main(root=candidate, do_publish=True) == 0
    assert ("git", "add", "--", "data/policy_snapshots/2026-11-09", "scripts/scraping/seeds.json") in calls
    assert ("git", "push", "origin", "HEAD:refs/heads/automation/policy-snapshot-2026-11-09-1234") in calls
    pr = next(args for args in calls if args[:3] == ("gh", "pr", "create"))
    assert "--draft" in pr
    assert "--body-file" in pr
    assert (candidate / "data/policy_snapshots/ACTIVE").read_text() == "2026-10-15\n"
    assert not (candidate / "data/policy_chunks").exists()
    assert not (candidate / "data/chroma").exists()


def test_successful_inactive_build_is_included_in_review_without_served_paths(candidate, monkeypatch):
    change(candidate, FOLDER + "changes_since_2026-10-15.json", changed=[{}])
    monkeypatch.setenv("POLICY_CANDIDATE_BUILD_STATUS", "success")
    for name in ("policy_chunks", "topic_cards"):
        (candidate / "data" / name / "2026-11-09").mkdir(parents=True)
    write(candidate / "data/policy_chunks/chunk_id_registry.json", {"fixture": "CHUNK_FAKE_01"})
    calls = fake_commands(monkeypatch)
    assert watch.main(root=candidate, do_publish=True) == 0
    added = next(args for args in calls if args[:3] == ("git", "add", "--"))
    assert "data/policy_chunks/2026-11-09" in added
    assert "data/topic_cards/2026-11-09" in added
    assert "data/policy_chunks/chunk_id_registry.json" in added
    assert not any("2026-10-15" in name or "ACTIVE" in name or "chroma" in name for name in added)
    assert "date folders are inactive" in (candidate / ".local/reports/policy-watch-pr.md").read_text()


def test_missing_successful_build_outputs_fail_before_git_writes(candidate, monkeypatch):
    change(candidate, FOLDER + "changes_since_2026-10-15.json", added=[{}])
    monkeypatch.setenv("POLICY_CANDIDATE_BUILD_STATUS", "success")
    calls = fake_commands(monkeypatch)
    assert watch.main(root=candidate, do_publish=True) == 1
    assert not any(args[0] == "git" for args in calls)


def test_failed_build_publishes_snapshot_only_with_explicit_warning(candidate, monkeypatch):
    change(candidate, FOLDER + "changes_since_2026-10-15.json", changed=[{}])
    monkeypatch.setenv("POLICY_CANDIDATE_BUILD_STATUS", "failure")
    calls = fake_commands(monkeypatch)
    assert watch.main(root=candidate, do_publish=True) == 0
    added = next(args for args in calls if args[:3] == ("git", "add", "--"))
    assert len(added) == 5
    assert "No candidate chunks/cards are included" in (candidate / ".local/reports/policy-watch-pr.md").read_text()


def test_existing_candidate_is_not_overwritten_or_duplicated(candidate, monkeypatch):
    change(candidate, FOLDER + "changes_since_2026-10-15.json", added=[{"slug": "new"}])
    calls = fake_commands(monkeypatch, pending=[{
        "headRefName": "automation/policy-snapshot-2026-11-02-1100", "url": "https://github.com/example/project/pull/41",
    }])
    assert watch.main(root=candidate, do_publish=True) == 0
    assert not any(args[0] == "git" for args in calls)
    assert not any(args[:3] == ("gh", "pr", "create") for args in calls)
    body = (candidate / ".local/reports/policy-watch-issue.md").read_text()
    assert "pending PR may be older" in body


def test_repeated_block_updates_one_issue_without_git_writes(candidate, monkeypatch):
    change(candidate, STATUS, outcome="blocked", snapshot_ready=False, blocked={"http_status": 403})
    calls = fake_commands(monkeypatch, issues=[{
        "title": watch.ATTENTION_TITLE, "body": watch.MARKER, "number": 43,
        "url": "https://github.com/example/project/issues/43",
    }])
    assert watch.main(root=candidate, do_publish=True) == 0
    assert any(args[:3] == ("gh", "issue", "edit") for args in calls)
    assert not any(args[:3] == ("gh", "issue", "create") or args[0] == "git" for args in calls)


def test_unchanged_does_not_create_issues_prs_or_close_earlier_alert(candidate, monkeypatch):
    calls = fake_commands(monkeypatch)
    assert watch.main(root=candidate, do_publish=True) == 0
    assert calls == []


def test_refuses_unrelated_staged_changes(candidate, monkeypatch):
    change(candidate, FOLDER + "changes_since_2026-10-15.json", changed=[{}])
    calls = fake_commands(monkeypatch, staged="backend/other_work.py")
    assert watch.main(root=candidate, do_publish=True) == 1
    assert not any(args[:2] == ("git", "switch") for args in calls)
    report = watch.read_json(candidate / ".local/reports/policy-watch-status.json")
    assert "unrelated staged changes" in report["publication_error"]


def test_notification_permissions_error_is_visible_failure(candidate, monkeypatch):
    change(candidate, STATUS, outcome="blocked", snapshot_ready=False, blocked={"http_status": 403})

    def denied(*args):
        raise subprocess.CalledProcessError(1, ["gh", "issue", "create"])

    monkeypatch.setattr(watch, "run", denied)
    assert watch.main(root=candidate, do_publish=True) == 1
    report = watch.read_json(candidate / ".local/reports/policy-watch-status.json")
    assert report["status"] == "blocked"
    assert "publication_error" in report


def test_real_diff_catches_changed_conditions_even_when_amount_sets_match(candidate, monkeypatch):
    """Run the production diff: matching numbers alone must never mean unchanged policy."""
    script = SCRIPT.parent / "scraping/diff.py"
    monkeypatch.syspath_prepend(str(script.parent))
    diff_spec = importlib.util.spec_from_file_location("watcher_diff", script)
    diff = importlib.util.module_from_spec(diff_spec)
    diff_spec.loader.exec_module(diff)
    snaps = candidate / "data/policy_snapshots"
    old = snaps / "2026-10-15"
    (old / "clean").mkdir(parents=True)
    write(old / "manifest.json", watch.read_json(candidate / (FOLDER + "manifest.json")))
    (old / "clean/hdb-ehg.md").write_text("Families: $9,000\nSingles: $4,500\nFirst-timer conditions apply.")
    (candidate / (FOLDER + "clean/hdb-ehg.md")).write_text(
        "Families: $4,500\nSingles: $9,000\nDifferent household conditions apply.")
    monkeypatch.setattr(diff, "SNAPS", snaps)
    monkeypatch.setattr(sys, "argv", ["diff.py", "2026-10-15", "2026-11-09"])
    diff.main()
    report = watch.inspect(candidate)
    assert report["status"] == "changed"
    actual = watch.read_json(candidate / (FOLDER + "changes_since_2026-10-15.json"))
    assert actual["changed"][0]["figures_added"] == []
    assert actual["changed"][0]["figures_removed"] == []


@pytest.mark.parametrize("relative,value", [(STATUS, []), (FOLDER + "manifest.json", {}),
    (FOLDER + "verification.json", {"hdb-ehg": "broken"}),
    (FOLDER + "changes_since_2026-10-15.json", {"old": "2026-10-15", "new": "2026-11-09", "changed": "bad"})])
def test_malformed_evidence_produces_reported_failure(candidate, relative, value):
    write(candidate / relative, value)
    assert watch.inspect(candidate)["status"] == "failed"


def test_candidate_git_publication_end_to_end_uses_only_inactive_paths(candidate, monkeypatch):
    """Real local git commit/push, with gh simulated and no external repository access."""
    real_run = watch.run
    remote = candidate / ".local/test-remote.git"
    real_run(candidate, "git", "init", "--initial-branch=main")
    real_run(candidate, "git", "config", "user.name", "Watcher Test")
    real_run(candidate, "git", "config", "user.email", "watcher@example.invalid")
    real_run(candidate, "git", "add", "data/policy_snapshots/ACTIVE", "scripts/scraping/seeds.json",
             "scripts/scraping/pdf_seeds.json")
    real_run(candidate, "git", "commit", "-m", "initial active snapshot")
    original = real_run(candidate, "git", "rev-parse", "HEAD")
    real_run(candidate, "git", "init", "--bare", str(remote))
    real_run(candidate, "git", "remote", "add", "origin", str(remote))
    (candidate / "unrelated.txt").write_text("Do not include my other work")
    change(candidate, FOLDER + "changes_since_2026-10-15.json", changed=[{}])

    def local_only(root, *args):
        if args[:3] == ("gh", "pr", "list"):
            return "[]"
        if args[:3] == ("gh", "pr", "create"):
            return "https://github.com/example/project/pull/42"
        assert args[0] == "git"
        return real_run(root, *args)

    monkeypatch.setattr(watch, "run", local_only)
    assert watch.main(root=candidate, do_publish=True) == 0
    changed = real_run(candidate, "git", "diff", "--name-only", original, "HEAD").splitlines()
    assert changed
    assert all(name.startswith("data/policy_snapshots/2026-11-09/") for name in changed)
    assert "unrelated.txt" not in real_run(candidate, "git", "ls-files")
    branch = real_run(candidate, "git", "branch", "--show-current")
    assert branch == "automation/policy-snapshot-2026-11-09-1234"
    assert real_run(candidate, "git", "show", "main:data/policy_snapshots/ACTIVE") == "2026-10-15"
    refs = real_run(candidate, "git", "ls-remote", "origin")
    assert f"refs/heads/{branch}" in refs
    assert "refs/heads/main" not in refs
