"""The mutation checker must not mistake broken test infrastructure for detection."""
import importlib.util
import subprocess
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("policy_mutations", Path(__file__).resolve().parents[1] / "scripts/mutation_test_policy.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def report(tmp_path, contents):
    path = tmp_path / "junit.xml"
    path.write_text(contents)
    return path


def test_real_assertion_failure_is_a_kill(tmp_path):
    path = report(tmp_path, '<testsuites><testsuite><testcase name="good"/><testcase name="bad">'
                  '<failure message="AssertionError: expected rejection"/></testcase></testsuite></testsuites>')
    result = runner.classify(1, path, expected_tests=2)
    assert result["status"] == "killed"
    assert result["failures"][0]["reason"] == "AssertionError: expected rejection"


@pytest.mark.parametrize("code,contents,expected", [
    (2, '<testsuite><testcase><failure/></testcase></testsuite>', None),
    (1, '<testsuite><testcase><error message="fixture failed"/></testcase></testsuite>', None),
    (1, '<testsuite><testcase><failure message="TypeError: crashed"/></testcase></testsuite>', None),
    (0, '<testsuite><testcase><skipped/></testcase></testsuite>', None),
    (0, '<testsuite/>', None),
    (1, '<testsuite><testcase/></testsuite>', None),
    (0, '<testsuite><testcase><failure/></testcase></testsuite>', None),
    (0, 'not XML', None),
    (1, '<testsuite><testcase><failure/></testcase></testsuite>', 2),
])
def test_infrastructure_skips_or_wrong_test_count_are_not_kills(tmp_path, code, contents, expected):
    assert runner.classify(code, report(tmp_path, contents), expected)["status"] == "error"


def test_absent_result_is_not_a_kill(tmp_path):
    assert runner.classify(1, tmp_path / "missing.xml")["status"] == "error"


def test_clean_test_run_is_a_survivor(tmp_path):
    assert runner.classify(0, report(tmp_path, '<testsuite><testcase/></testsuite>'), 1)["status"] == "survived"


def test_child_does_not_inherit_credentials_or_heldout_location(monkeypatch, tmp_path):
    monkeypatch.setenv("LANGSMITH_API_KEY", "fake-private-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fake-private-key")
    monkeypatch.setenv("KOPI_HELDOUT_DIR", "private-evaluation")
    monkeypatch.setenv("HTTPS_PROXY", "https://fake-user:fake-password@proxy.invalid")
    env = runner.child_environment(tmp_path)
    assert not {"LANGSMITH_API_KEY", "AWS_SECRET_ACCESS_KEY", "HTTPS_PROXY"} & env.keys()
    assert env["KOPI_HELDOUT_DIR"] == ""
    assert env["LANGSMITH_TRACING"] == env["LANGCHAIN_TRACING_V2"] == "false"
    assert env["PYTHONPATH"] == str(tmp_path / "backend")


@pytest.fixture
def copied_project(tmp_path):
    root, parent = tmp_path / "project", tmp_path / "work"
    parent.mkdir()
    for name in runner.TESTS + ["fakes.py", "conftest.py"]:
        path = root / "tests" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")
    for name in ("tests/fixtures", "data/schema", "data/topic_cards", "data/policy_chunks/2026-10-15"):
        (root / name).mkdir(parents=True)
    target = root / "backend/policy.py"
    target.parent.mkdir()
    target.write_text("flag = True\n")
    active = root / "data/policy_snapshots/ACTIVE"
    active.parent.mkdir()
    active.write_text("2026-10-15\n")
    (root / ".env").write_text("FAKE_SECRET=do-not-copy\n")
    return root, parent, target


def test_fault_is_applied_only_to_private_copy_and_workspace_is_removed(copied_project, monkeypatch):
    root, parent, original = copied_project

    def fake_process(command, *, cwd, env, **kwargs):
        assert (cwd / "backend/policy.py").read_text() == "flag = False\n"
        assert not (cwd / ".env").exists()
        assert env["PYTHONPATH"] == str(cwd / "backend")
        report(cwd, '<testsuite><testcase/></testsuite>').rename(cwd / "results.xml")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(runner.subprocess, "run", fake_process)
    result = runner.execute(root, parent, {"file": "backend/policy.py", "before": "True", "after": "False"}, 10, 1)
    assert result["status"] == "survived"
    assert original.read_text() == "flag = True\n"
    assert list(parent.iterdir()) == []


def test_timeout_is_not_a_kill_and_copy_is_still_cleaned(copied_project, monkeypatch):
    root, parent, original = copied_project

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("pytest", 1)

    monkeypatch.setattr(runner.subprocess, "run", timeout)
    assert runner.execute(root, parent, None, 1)["status"] == "timeout"
    assert original.read_text() == "flag = True\n"
    assert list(parent.iterdir()) == []
