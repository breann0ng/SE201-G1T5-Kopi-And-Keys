"""Live freshness check: is the app current *today*, not as of the dev set's AS_OF month?

The dev-set evaluation pins the router's date to `dataset.AS_OF` so scores are reproducible.
That cannot tell whether relative periods ("past 6 months", "this year") work on the real
date, or whether the data and policy snapshot are up to date. This check does, without
calling a language model:

1. intent: the period the app asks for matches what the phrase means on `--today`
   (worked out here independently of the router's parser);
2. covered: the period actually queried does not run past the newest month in the price
   data, and when the asked-for period does, the answer says which months are missing
   (price_display.missing_months_note, #29): e.g. "past 6 months" on 9 Nov with data to Oct
   is queried Jun-Oct with "We don't have sales data for Nov 2026 yet";
3. figures: the price tool's volume and median equal plain SQL over the queried period;
4. data lag: the newest month in the price data is at most `--max-data-lag` months old;
5. policy age: the active policy snapshot is at most `--max-policy-age` days old.

Probes are generated from the date, not taken from the dev labels, so the check moves with
the calendar. Run from backend/:

    python -m kopi_keys.evaluation.freshness                     # today
    python -m kopi_keys.evaluation.freshness --today 2027-01-05  # e.g. a year boundary

Exit status 1 if any check fails. Reports go to .local/reports/ (gitignored).
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from . import metrics
from .dataset import ROOT, active_snapshot

REPORTS = ROOT / ".local" / "reports"
MAX_DATA_LAG_MONTHS = 2  # the current month is always incomplete; HDB data trails by ~1 month
MAX_POLICY_AGE_DAYS = 45  # the policy watcher runs weekly; this leaves room for review


def month_index(ym: str) -> int:
    year, month = map(int, ym.split("-"))
    return year * 12 + month - 1


def ym_of(index: int) -> str:
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def probes(today: date) -> list[dict]:
    """Price questions with relative periods, phrased the way users ask."""
    year = today.year
    return [
        {"id": "past-6-months", "question": "What did 4-room flats in Tampines sell for in the past 6 months?"},
        {"id": "past-3-months", "question": "How much were 3-room flats in Queenstown in the last 3 months?"},
        {"id": "this-year", "question": "How much are 4-room flats in Ang Mo Kio this year?"},
        {"id": "last-year", "question": "What were 5-room prices in Punggol last year?"},
        {"id": "in-current-year", "question": f"How much is a 3-room flat in Jurong West in {year}?"},
        {"id": "default", "question": "How much is a 4-room flat in Bedok?"},
    ]


def intended_window(question: str, today: date, data_max: str) -> tuple[str, str]:
    """What the question's period means on `today`, written independently of the router.

    "Past N months" and "this year" end at the current month (that is what the user means);
    with no period the app's documented default is the 12 months ending at the newest data.
    """
    now = today.year * 12 + today.month - 1
    text = question.casefold()
    if m := re.search(r"\b(?:past|last)\s+(\d{1,2})\s+months?\b", text):
        return ym_of(now - int(m.group(1)) + 1), ym_of(now)
    if "this year" in text:
        return f"{today.year:04d}-01", ym_of(now)
    if "last year" in text:
        return f"{today.year - 1:04d}-01", f"{today.year - 1:04d}-12"
    if m := re.search(r"\b((?:19|20)\d{2})\b", text):
        y = int(m.group(1))
        return f"{y:04d}-01", ym_of(min(now, y * 12 + 11))
    end = month_index(data_max)
    return ym_of(end - 11), data_max


def sql_figures(db_path, town: str, flat_type: str, start: str, end: str) -> tuple[int, Decimal | None]:
    """Volume and median with plain SQL + the textbook median, not the price tool."""
    with closing(sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)) as conn:
        prices = sorted(Decimal(str(r[0])) for r in conn.execute(
            "SELECT resale_price FROM transactions WHERE town = ? AND flat_type = ? "
            "AND month BETWEEN ? AND ?", (town, flat_type, start, end)))
    if not prices:
        return 0, None
    mid = len(prices) // 2
    median = prices[mid] if len(prices) % 2 else (prices[mid - 1] + prices[mid]) / 2
    return len(prices), median.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def app_filters(question: str, today: date, data_max: str):
    """(asked-for period, filters the app would query) on `today` (graph.price_query path)."""
    from ..components.price_query import PriceOutOfRangeError, filters_from_state
    from ..components.query_router import route_query

    with metrics.router_today(f"{today.year:04d}-{today.month:02d}"):
        state = route_query(question)
    if state.status == "clarify" or state.intent != "price":
        raise ValueError(f"routed as {state.intent}/{state.status}, not a price answer")
    try:
        filters = filters_from_state(state, latest_month=data_max)
    except PriceOutOfRangeError as error:
        if error.filters is None:
            raise
        filters = error.filters
    asked = (state.start_month or filters.start_month, state.end_month or filters.end_month)
    return asked, filters


def check(today: date, tool=None, snapshot: str | None = None,
          max_data_lag: int = MAX_DATA_LAG_MONTHS, max_policy_age: int = MAX_POLICY_AGE_DAYS) -> dict:
    from ..components.price_display import missing_months_note
    from ..components.price_query import InvalidPriceFilterError, SqlitePriceTool

    tool = tool or SqlitePriceTool()
    info = tool.info()
    data_max = info.max_month
    now = today.year * 12 + today.month - 1
    rows = []
    for probe in probes(today):
        row = {**probe, "intended": intended_window(probe["question"], today, data_max)}
        try:
            asked, f = app_filters(probe["question"], today, data_max)
        except Exception as error:  # a routing failure is a failed probe, not a crash
            rows.append({**row, "error": str(error), "intent": False, "covered": False, "figures": False})
            continue
        got = (f.start_month, f.end_month)
        row.update(asked=asked, app=got, intent=asked == row["intended"])
        try:
            result = tool.query(f)
        except InvalidPriceFilterError as error:  # whole period after the data: the app declines
            rows.append({**row, "covered": True, "figures": True, "volume": 0, "median": None,
                         "disclosure": None, "note": str(error)})
            continue
        disclosure = missing_months_note(f, asked[1])
        cut_short = asked[1] > f.end_month
        covered = f.end_month <= data_max and (not cut_short or bool(disclosure))
        volume, median = sql_figures(tool.db_path, result.filters.town, result.filters.flat_type, *got)
        rows.append({
            **row, "covered": covered, "disclosure": disclosure,
            "figures": (result.volume, result.median) == (volume, median),
            "volume": result.volume, "median": str(result.median), "sql": [volume, str(median)],
        })
    lag = now - month_index(data_max)
    snap = snapshot or active_snapshot()
    policy_age = (today - date.fromisoformat(snap)).days
    sources = {
        "price_data": {"newest_month": data_max, "downloaded_on": info.downloaded_on,
                       "lag_months": lag, "ok": lag <= max_data_lag},
        "policy_snapshot": {"date": snap, "age_days": policy_age, "ok": policy_age <= max_policy_age},
    }
    ok = all(r["intent"] and r["covered"] and r["figures"] for r in rows) and all(
        s["ok"] for s in sources.values())
    return {"today": today.isoformat(), "ok": ok, "probes": rows, "sources": sources,
            "thresholds": {"max_data_lag_months": max_data_lag, "max_policy_age_days": max_policy_age}}


def mark(flag: bool) -> str:
    return "ok" if flag else "FAIL"


def main() -> int:
    parser = argparse.ArgumentParser(description="Live freshness check (no model calls).")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today(),
                        help="YYYY-MM-DD; defaults to the real date")
    parser.add_argument("--max-data-lag", type=int, default=MAX_DATA_LAG_MONTHS)
    parser.add_argument("--max-policy-age", type=int, default=MAX_POLICY_AGE_DAYS)
    parser.add_argument("--out", help="report path (default .local/reports/<ts>_freshness.json)")
    args = parser.parse_args()
    report = check(args.today, max_data_lag=args.max_data_lag, max_policy_age=args.max_policy_age)

    print(f"Freshness as of {report['today']}")
    for r in report["probes"]:
        if "error" in r:
            print(f"  {r['id']:<16} FAIL  {r['error']}")
            continue
        print(f"  {r['id']:<16} meant {r['intended'][0]}..{r['intended'][1]}  asked {r['asked'][0]}..{r['asked'][1]}"
              f"  queried {r['app'][0]}..{r['app'][1]}"
              f"  intent {mark(r['intent'])}  covered {mark(r['covered'])}  figures {mark(r['figures'])}"
              f"  ({r['volume']} sales)" + ("  app declines: no data for that period" if r.get("note") else ""))
        if r.get("disclosure"):
            print(f"  {'':<16} says: {r['disclosure']}")
    p, s = report["sources"]["price_data"], report["sources"]["policy_snapshot"]
    print(f"  price data      newest month {p['newest_month']} (downloaded {p['downloaded_on']}), "
          f"{p['lag_months']} month(s) behind  {mark(p['ok'])}")
    print(f"  policy snapshot {s['date']}, {s['age_days']} days old  {mark(s['ok'])}")
    print("PASS" if report["ok"] else "FAIL")

    out = args.out or REPORTS / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_freshness.json"
    REPORTS.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"Report: {out}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
