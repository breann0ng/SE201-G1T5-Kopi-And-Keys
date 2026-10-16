"""Polite, cached fetcher for official HDB/CPF policy pages (Person 4, Day 1).

Rules enforced here:
- domain allowlist (hdb.gov.sg, cpf.gov.sg, mynicehome.gov.sg)
- robots.txt checked per domain before any page fetch; result recorded
- >= 3 s between requests to the same domain, strictly sequential
- hard cap on total network fetches (robots.txt + sitemaps + pages count)
- raw responses cached; reruns never re-fetch a cached URL

Usage:
  python fetch.py robots                 # fetch + record robots.txt for each domain
  python fetch.py url <slug> <url>       # fetch one page (httpx) into raw/<slug>.html
  python fetch.py seeds                  # fetch every entry in seeds.json
  python fetch.py render <slug>          # re-fetch <slug> with headless Chromium
  python fetch.py pdf <slug> <url>       # download one PDF into raw/<slug>.pdf
  python fetch.py sitemap <url>          # fetch a robots-declared sitemap to locate seeds
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.robotparser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[2]
SGT = timezone(timedelta(hours=8))
SNAPSHOT_DATE = datetime.now(SGT).strftime("%Y-%m-%d")
SNAP_DIR = ROOT / "data" / "policy_snapshots" / SNAPSHOT_DATE
RAW_DIR = SNAP_DIR / "raw"
LOG_PATH = SNAP_DIR / "fetch_log.json"
SEEDS_PATH = Path(__file__).with_name("seeds.json")

ALLOWED = ("hdb.gov.sg", "cpf.gov.sg", "mynicehome.gov.sg")
USER_AGENT = (
    "SMU-SE201-StudentResearch/0.1 (university group project; HDB policy advisor; "
    "low-rate, public pages only)"
)
# hdb.gov.sg's WAF returns 403 to the plain research UA (robots.txt included).
# Approved by Person 4 on 2026-10-15: use a browser-compatible UA for that domain
# only, still naming the project. robots.txt, rate limit and fetch cap still apply,
# and we stop (never solve) if a bot challenge / CAPTCHA page is served.
BROWSER_COMPAT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36 (compatible; " + USER_AGENT + ")"
)
DOMAIN_UA = {"hdb.gov.sg": BROWSER_COMPAT_UA}
CHALLENGE_MARKERS = ("captcha", "cf-challenge", "challenge-platform", "are you a robot",
                     "access denied", "request unsuccessful")
MIN_DELAY_S = 3.0
# Was 30 for Day 1. Raised 2026-10-15 by Person 4 for the agreed scope (see discover.py);
# kept as a safety stop against runaway loops, not as a budget.
FETCH_CAP = 200

_last_hit: dict[str, float] = {}


def now_sgt() -> str:
    return datetime.now(SGT).isoformat(timespec="seconds")


def domain_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    for d in ALLOWED:
        if host == d or host.endswith("." + d):
            return d
    raise SystemExit(f"Refusing non-allowlisted URL: {url}")


def load_log() -> dict:
    if LOG_PATH.exists():
        return json.loads(LOG_PATH.read_text(encoding="utf-8"))
    return {"snapshot_date": SNAPSHOT_DATE, "fetch_count": 0, "robots": {}, "pages": {}, "events": []}


def save_log(log: dict) -> None:
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")


def _throttle(domain: str) -> None:
    wait = _last_hit.get(domain, 0) + MIN_DELAY_S - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_hit[domain] = time.monotonic()


def ua_for(url: str) -> str:
    return DOMAIN_UA.get(domain_of(url), USER_AGENT)


def check_not_challenge(resp: httpx.Response) -> None:
    """Abort rather than work around a WAF challenge."""
    head = resp.text[:20000].lower() if "html" in resp.headers.get("content-type", "") else ""
    if resp.status_code in (401, 403, 429) or any(m in head for m in CHALLENGE_MARKERS):
        raise SystemExit(f"Blocked/challenge page from {resp.url} (HTTP {resp.status_code}); "
                         "stopping without retrying.")


def _count(log: dict, url: str, kind: str) -> None:
    if log["fetch_count"] >= FETCH_CAP:
        raise SystemExit(f"Fetch cap of {FETCH_CAP} reached; not fetching {url}")
    log["fetch_count"] += 1
    log["events"].append({"n": log["fetch_count"], "kind": kind, "url": url, "at": now_sgt(),
                          "user_agent": ua_for(url)})


def get(url: str, log: dict, kind: str) -> httpx.Response:
    domain = domain_of(url)
    _count(log, url, kind)
    _throttle(domain)
    with httpx.Client(headers={"User-Agent": ua_for(url)}, follow_redirects=True, timeout=30) as c:
        resp = c.get(url)
    log["events"][-1]["http_status"] = resp.status_code
    # Redirects must stay on the allowlist.
    domain_of(str(resp.url))
    save_log(log)
    return resp


def robots(log: dict) -> None:
    out = SNAP_DIR / "robots"
    out.mkdir(parents=True, exist_ok=True)
    for d in ALLOWED:
        if d in log["robots"]:
            print(f"cached robots for {d}: {log['robots'][d]['status']}")
            continue
        url = f"https://www.{d}/robots.txt"
        try:
            r = get(url, log, "robots")
            (out / f"{d}.txt").write_text(r.text, encoding="utf-8")
            log["robots"][d] = {"url": url, "final_url": str(r.url), "status": r.status_code,
                                "fetched_at": now_sgt(), "user_agent": ua_for(url)}
        except httpx.HTTPError as e:
            log["robots"][d] = {"url": url, "status": None, "error": repr(e), "fetched_at": now_sgt()}
        save_log(log)
        print(d, log["robots"][d])


def robots_allowed(url: str, log: dict) -> bool | None:
    d = domain_of(url)
    info = log["robots"].get(d)
    path = SNAP_DIR / "robots" / f"{d}.txt"
    if not info or not path.exists():
        return None
    if info["status"] in (401, 403):
        return False  # conservative: treat access-denied robots as disallow-all
    if info["status"] and info["status"] >= 400:
        return True  # standard: missing robots.txt means no restrictions
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(path.read_text(encoding="utf-8").splitlines())
    # Check both our own token and the generic rules.
    return rp.can_fetch(USER_AGENT, url) and rp.can_fetch(ua_for(url), url)


def fetch_page(slug: str, url: str, log: dict) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dest = RAW_DIR / f"{slug}.html"
    if dest.exists() and slug in log["pages"]:
        print(f"cached: {slug}")
        return
    allowed = robots_allowed(url, log)
    if allowed is None:
        raise SystemExit("Run `fetch.py robots` first.")
    entry = {"slug": slug, "requested_url": url, "robots_allowed": allowed}
    if not allowed:
        entry.update(http_status=None, method=None, notes="blocked by robots.txt; not fetched")
        log["pages"][slug] = entry
        save_log(log)
        print(f"BLOCKED by robots: {slug} {url}")
        return
    r = get(url, log, "page")
    check_not_challenge(r)
    body = r.content
    dest.write_bytes(body)
    entry.update(final_url=str(r.url), http_status=r.status_code, fetched_at=now_sgt(),
                 method="httpx", user_agent=ua_for(url), content_type=r.headers.get("content-type"),
                 sha256=hashlib.sha256(body).hexdigest(),
                 redirect_chain=[str(h.url) for h in r.history])
    log["pages"][slug] = entry
    save_log(log)
    print(f"{slug}: {r.status_code} {r.url} ({len(body)} bytes)")


def render_page(slug: str, log: dict) -> None:
    from playwright.sync_api import sync_playwright

    entry = log["pages"][slug]
    url = entry.get("final_url") or entry["requested_url"]
    dest = RAW_DIR / f"{slug}.rendered.html"
    if dest.exists() and entry.get("rendered"):
        print(f"cached render: {slug}")
        return
    _count(log, url, "render")
    _throttle(domain_of(url))
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=ua_for(url))
        page = ctx.new_page()
        # Block third-party requests so only the allowlisted page itself is loaded.
        page.route("**/*", lambda route: route.continue_()
                   if _is_allowed(route.request.url) else route.abort())
        resp = page.goto(url, wait_until="networkidle", timeout=60000)
        html = page.content()
        final = page.url
        browser.close()
    domain_of(final)
    dest.write_text(html, encoding="utf-8")
    entry.update(rendered=True, method="playwright", final_url=final,
                 http_status=resp.status if resp else entry.get("http_status"),
                 fetched_at=now_sgt(), sha256=hashlib.sha256(html.encode("utf-8")).hexdigest())
    save_log(log)
    print(f"rendered {slug}: {final} ({len(html)} chars)")


def _is_allowed(url: str) -> bool:
    try:
        domain_of(url)
        return True
    except SystemExit:
        return False


def fetch_pdf(slug: str, url: str, log: dict) -> None:
    dest = RAW_DIR / f"{slug}.pdf"
    if dest.exists():
        print(f"cached pdf: {slug}")
        return
    if not robots_allowed(url, log):
        raise SystemExit(f"robots disallows {url}")
    r = get(url, log, "pdf")
    dest.write_bytes(r.content)
    log["pages"][slug] = {"slug": slug, "requested_url": url, "final_url": str(r.url),
                          "http_status": r.status_code, "fetched_at": now_sgt(), "method": "pdf",
                          "robots_allowed": True, "sha256": hashlib.sha256(r.content).hexdigest()}
    save_log(log)


def sitemap(url: str, log: dict) -> None:
    """Fetch a sitemap declared in robots.txt (used only to locate seed pages, not to crawl)."""
    out = SNAP_DIR / "sitemaps"
    out.mkdir(parents=True, exist_ok=True)
    dest = out / (urlparse(url).hostname + urlparse(url).path.replace("/", "_"))
    if dest.exists():
        print(f"cached sitemap: {dest.name}")
        return
    if not robots_allowed(url, log):
        raise SystemExit(f"robots disallows {url}")
    r = get(url, log, "sitemap")
    dest.write_bytes(r.content)
    print(f"sitemap {url}: {r.status_code} ({len(r.content)} bytes)")


def main(argv: list[str]) -> None:
    log = load_log()
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "robots":
        robots(log)
    elif cmd == "url":
        fetch_page(argv[2], argv[3], log)
    elif cmd == "seeds":
        for s in json.loads(SEEDS_PATH.read_text(encoding="utf-8")):
            fetch_page(s["slug"], s["url"], log)
    elif cmd == "render":
        render_page(argv[2], log)
    elif cmd == "sitemap":
        sitemap(argv[2], log)
    elif cmd == "pdf":
        fetch_pdf(argv[2], argv[3], log)
    else:
        print(__doc__)
    print(f"total fetches used: {log['fetch_count']}/{FETCH_CAP}")


if __name__ == "__main__":
    main(sys.argv)
