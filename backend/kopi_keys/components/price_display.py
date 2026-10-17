"""User-facing wording for a verified price summary.

Display only. The Synthesiser's five lines have already passed the numeric
Verifier; this module re-arranges those same verified figures into a short,
readable answer. It never recomputes a statistic. The query ID stays in
`price_result` and the trace for debugging, not in the message.
"""

from __future__ import annotations

import re
from decimal import Decimal

from ..schemas import PriceFilters, PriceResult

_MONEY = r"(?:SGD\s*|S\$\s*|\$\s*)?([\d,]+(?:\.\d+)?)"
_LINES = {
    "mean": re.compile(rf"^\s*Mean:\s*{_MONEY}\s*$", re.IGNORECASE),
    "median": re.compile(rf"^\s*Median:\s*{_MONEY}\s*$", re.IGNORECASE),
    "iqr": re.compile(rf"^\s*IQR:\s*{_MONEY}\s*$", re.IGNORECASE),
    "range": re.compile(rf"^\s*Range:\s*{_MONEY}\s*to\s*{_MONEY}\s*$", re.IGNORECASE),
    "volume": re.compile(r"^\s*Volume:\s*([\d,]+)\s*transactions?\s*$", re.IGNORECASE),
}
_MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def money(text: str) -> str:
    """'1,050,000.00' -> '$1,050,000'; '1079268.31' -> '$1,079,268.31'."""
    value = Decimal(text.replace(",", ""))
    if value == value.to_integral_value():
        return f"${int(value):,}"
    return f"${value:,.2f}"


def month_label(yyyy_mm: str) -> str:
    year, month = yyyy_mm.split("-")
    return f"{_MONTHS[int(month) - 1]} {year}"


def period_label(filters: PriceFilters) -> str:
    start, end = month_label(filters.start_month), month_label(filters.end_month)
    return start if start == end else f"{start} to {end}"


def flat_label(flat_type: str) -> str:
    """'5 ROOM' -> '5-room', 'EXECUTIVE' -> 'Executive'."""
    match = re.fullmatch(r"(\d)\s*ROOM", flat_type.strip().upper())
    return f"{match.group(1)}-room" if match else flat_type.strip().capitalize()


def town_label(town: str) -> str:
    """'TOA PAYOH' -> 'Toa Payoh', 'KALLANG/WHAMPOA' -> 'Kallang/Whampoa'."""
    return re.sub(r"[A-Za-z]+", lambda m: m.group(0).capitalize(), town.strip().lower())


LEASE_LABELS = {"under_60": "under 60 years", "60_79": "60 to 79 years", "80_plus": "80+ years"}
STOREY_LABELS = {"low": "low floors (1 to 6)", "mid": "middle floors (7 to 12)", "high": "high floors (13+)"}


def subject_label(filters: PriceFilters) -> str:
    """'5-room flats in Toa Payoh with 80+ years of lease left, on high floors (13+)'."""
    text = f"{flat_label(filters.flat_type)} flats in {town_label(filters.town)}"
    extras = []
    if filters.lease_band:
        extras.append(f"with {LEASE_LABELS[filters.lease_band]} of lease left")
    if filters.storey_band:
        extras.append(f"on {STOREY_LABELS[filters.storey_band]}")
    return text + (" " + ", ".join(extras) if extras else "")


def lease_note(price: PriceResult) -> str | None:
    """One line on how much remaining lease matters, when the user has not picked a lease band."""
    if price.filters.lease_band:
        return None
    bands = [b for b in price.breakdown if b.dimension == "lease" and b.volume >= 5 and b.median is not None]
    if len(bands) < 2:
        return None
    low = min(bands, key=lambda b: b.median)
    high = max(bands, key=lambda b: b.median)
    if high.median < low.median * Decimal("1.1"):
        return None
    return (f"Remaining lease matters here: the median ranges from {money(str(low.median))} "
            f"({LEASE_LABELS[low.band]} left) to {money(str(high.median))} ({LEASE_LABELS[high.band]} left). "
            "Use **Narrow it down** below to compare like with like.")


def _parse(price_text: str) -> dict[str, tuple[str, ...]] | None:
    found: dict[str, tuple[str, ...]] = {}
    for line in price_text.strip().splitlines():
        if not line.strip():
            continue
        for name, pattern in _LINES.items():
            match = pattern.match(line)
            if match:
                found[name] = match.groups()
                break
    return found if len(found) == len(_LINES) else None


def price_answer(price_text: str, price: PriceResult) -> str:
    """The verified figures as a short answer: median first, then spread, range and source."""
    f = price.filters
    subject = subject_label(f)
    period = period_label(f)
    parsed = _parse(price_text)
    if parsed is None:  # Unexpected layout: show the verified lines as they are.
        lines = "\n".join(f"- {line.strip()}" for line in price_text.strip().splitlines() if line.strip())
        return f"**{subject}**, {period}\n\n{lines}"
    sales = int(parsed["volume"][0].replace(",", ""))
    low, high = parsed["range"]
    note = lease_note(price)
    return (
        f"**{subject}** sold for a median of **{money(parsed['median'][0])}** "
        f"({period}, {sales:,} {'sale' if sales == 1 else 'sales'}).\n\n"
        f"- Average (mean): {money(parsed['mean'][0])}\n"
        f"- Middle 50% of prices fall within a {money(parsed['iqr'][0])} band\n"
        f"- Lowest to highest: {money(low)} to {money(high)}\n\n"
        + (f"{note}\n\n" if note else "")
        + "*Source: HDB resale flat prices (data.gov.sg). Past sales only, not a valuation of any particular flat.*"
    )
