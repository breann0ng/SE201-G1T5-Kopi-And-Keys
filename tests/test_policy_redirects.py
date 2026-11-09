"""No off-source redirect may be contacted, including from an official source."""
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "scraping"))
import fetch


@pytest.fixture
def network(monkeypatch, tmp_path):
    calls = []
    factory = httpx.Client
    monkeypatch.setattr(fetch, "SNAP_DIR", tmp_path)
    monkeypatch.setattr(fetch, "LOG_PATH", tmp_path / "fetch_log.json")
    monkeypatch.setattr(fetch, "_throttle", lambda domain: None)
    monkeypatch.setattr(fetch, "robots_allowed", lambda url, log: True)

    def install(handler):
        def record(request):
            calls.append(str(request.url))
            return handler(request)
        monkeypatch.setattr(fetch.httpx, "Client", lambda **kwargs:
                            factory(transport=httpx.MockTransport(record), **kwargs))
        return calls
    return install


@pytest.mark.parametrize("target", [
    "https://untrusted.invalid/policy", "https://hdb.gov.sg.untrusted.invalid/policy",
    "https://127.0.0.1/policy", "http://www.hdb.gov.sg/policy",
    "https://www.hdb.gov.sg:8080/policy", "https://user:password@www.hdb.gov.sg/policy",
    "file:///etc/passwd", "//untrusted.invalid/policy",
])
def test_unapproved_redirect_never_reaches_transport(network, target):
    calls = network(lambda req: httpx.Response(302, headers={"location": target}))
    with pytest.raises(fetch.FetchBlocked, match="outside the allowed"):
        fetch.get("https://www.hdb.gov.sg/start", fetch.load_log(), "page")
    assert calls == ["https://www.hdb.gov.sg/start"]


def test_relative_official_redirect_keeps_history_and_counts_each_hop(network):
    calls = network(lambda req: httpx.Response(302, headers={"location": "/final"})
                    if req.url.path == "/start" else httpx.Response(200, text="policy"))
    log = fetch.load_log()
    response = fetch.get("https://www.hdb.gov.sg/start", log, "page")
    assert response.text == "policy"
    assert len(response.history) == 1
    assert log["fetch_count"] == len(calls) == 2
    assert [e["kind"] for e in log["events"]] == ["page", "redirect"]


def test_redirect_robots_denial_stops_before_second_request(network, monkeypatch):
    calls = network(lambda req: httpx.Response(302, headers={"location": "/denied"}))
    monkeypatch.setattr(fetch, "robots_allowed", lambda url, log: False)
    with pytest.raises(fetch.FetchBlocked, match="robots permission"):
        fetch.get("https://www.hdb.gov.sg/start", fetch.load_log(), "page")
    assert len(calls) == 1


def test_redirect_loop_is_bounded(network):
    calls = network(lambda req: httpx.Response(302, headers={"location": "/loop"}))
    with pytest.raises(fetch.FetchBlocked, match="Redirect limit"):
        fetch.get("https://www.hdb.gov.sg/start", fetch.load_log(), "page")
    assert len(calls) == fetch.MAX_REDIRECTS + 1


def test_robots_cannot_redirect_to_another_policy_source(network):
    calls = network(lambda req: httpx.Response(302, headers={"location": "https://www.cpf.gov.sg/robots.txt"}))
    with pytest.raises(fetch.FetchBlocked, match="different policy source"):
        fetch.get("https://www.hdb.gov.sg/robots.txt", fetch.load_log(), "robots")
    assert len(calls) == 1
