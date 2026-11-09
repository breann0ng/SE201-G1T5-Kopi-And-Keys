"""Error bars for small eval sets: Wilson intervals and paired exact McNemar tests.

With 22 policy questions one question moves a rate by 4.5 points, so every rate is
reported with a 95% Wilson interval, and two systems run on the same questions are
compared question by question: only the discordant questions (one system right,
the other wrong) carry information, and the exact McNemar test asks whether that
split could be a coin flip. Pure Python, no SciPy.
"""
from __future__ import annotations

from math import comb, sqrt

Z95 = 1.959963984540054


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """95% Wilson score interval for k successes out of n (good at small n and at 0% / 100%)."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def rate(k: int, n: int) -> str:
    """'81.8% (18/22), 95% CI 61.5-92.7%'."""
    if n == 0:
        return "n/a"
    lo, hi = wilson(k, n)
    return f"{100 * k / n:.1f}% ({k}/{n}), 95% CI {100 * lo:.1f}-{100 * hi:.1f}%"


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from the discordant counts.

    b: questions only system A got right; c: questions only system B got right.
    Under 'no difference' each discordant question is a fair coin, so the p-value is
    the two-sided binomial tail of min(b, c) in b + c tosses.
    """
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def paired(a: dict[str, bool], b: dict[str, bool]) -> dict:
    """Compare two systems' per-question successes on the questions both were scored on."""
    ids = sorted(set(a) & set(b))
    only_a = sum(a[i] and not b[i] for i in ids)
    only_b = sum(b[i] and not a[i] for i in ids)
    return {"n": len(ids), "a": sum(a[i] for i in ids), "b": sum(b[i] for i in ids),
            "only_a": only_a, "only_b": only_b, "p": mcnemar_exact(only_a, only_b)}
