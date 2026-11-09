"""Property tests: relations that must hold for every input in a range, not one example.

Hypothesis is not a project dependency, so the ranges are small enough to check exhaustively
(every k and n) or with a seeded random sample. A failure names the exact input.
"""
import random
import re

import pytest

from kopi_keys.components.policy_retrieval import KeywordPolicyRetriever
from kopi_keys.evaluation import stats

N_MAX = 60
PAIRS = [(k, n) for n in range(1, N_MAX + 1) for k in range(n + 1)]


# --- Wilson interval -----------------------------------------------------------

def test_wilson_interval_is_inside_0_1_and_contains_the_observed_rate():
    for k, n in PAIRS:
        lo, hi = stats.wilson(k, n)
        assert 0.0 <= lo <= k / n <= hi <= 1.0, (k, n, lo, hi)


def test_wilson_is_symmetric_between_successes_and_failures():
    for k, n in PAIRS:
        lo, hi = stats.wilson(k, n)
        lo2, hi2 = stats.wilson(n - k, n)
        assert lo == pytest.approx(1 - hi2, abs=1e-12) and hi == pytest.approx(1 - lo2, abs=1e-12), (k, n)


def test_wilson_narrows_as_the_sample_grows_at_the_same_rate():
    for k, n in PAIRS:
        if 2 * n > 2 * N_MAX:
            continue
        lo, hi = stats.wilson(k, n)
        lo2, hi2 = stats.wilson(2 * k, 2 * n)
        assert hi2 - lo2 < hi - lo, (k, n)


def test_wilson_interval_is_never_a_single_point():
    for k, n in PAIRS:
        lo, hi = stats.wilson(k, n)
        assert hi - lo > 0.0, (k, n)


# --- Exact McNemar --------------------------------------------------------------

B_MAX = 30
DISCORDANT = [(b, c) for b in range(B_MAX + 1) for c in range(B_MAX + 1)]


def test_mcnemar_p_is_a_probability_and_symmetric():
    for b, c in DISCORDANT:
        p = stats.mcnemar_exact(b, c)
        assert 0.0 < p <= 1.0, (b, c, p)
        assert p == stats.mcnemar_exact(c, b), (b, c)


def test_mcnemar_equal_split_is_no_evidence_of_a_difference():
    for b in range(B_MAX + 1):
        assert stats.mcnemar_exact(b, b) == 1.0, b


def test_mcnemar_more_lopsided_split_gives_a_smaller_p():
    # Same number of discordant questions; moving one from the smaller side to the larger.
    for n in range(1, 2 * B_MAX + 1):
        for small in range(n // 2):
            assert stats.mcnemar_exact(small, n - small) <= stats.mcnemar_exact(small + 1, n - small - 1), (n, small)


# --- Keyword retrieval ------------------------------------------------------------

@pytest.fixture(scope="module")
def retriever():
    return KeywordPolicyRetriever()


@pytest.fixture(scope="module")
def queries(retriever):
    """200 seeded random queries of 1 to 6 words drawn from the snapshot's own text."""
    words = sorted({w for c in retriever.chunks for w in re.findall(r"[a-z]{3,}", c["content"].lower())})
    rng = random.Random(201)
    return [" ".join(rng.sample(words, rng.randint(1, 6))) for _ in range(200)]


def test_keyword_results_are_unique_current_and_within_the_limit(retriever, queries):
    for query in queries:
        for depth in (1, 5, 20):
            ids = retriever.ranked_ids(query, depth)
            assert len(ids) <= depth, (query, depth)
            assert len(ids) == len(set(ids)), query
            assert set(ids) <= set(retriever.by_id), query  # never a superseded or unknown chunk


def test_keyword_ranking_is_deterministic_and_a_shorter_list_is_a_prefix(retriever, queries):
    for query in queries:
        top20 = retriever.ranked_ids(query, 20)
        assert retriever.ranked_ids(query, 20) == top20, query
        assert retriever.ranked_ids(query, 5) == top20[:5], query


def test_query_with_no_searchable_words_returns_nothing(retriever):
    for query in ("", "   ", "?!", "the a of"):
        assert retriever.ranked_ids(query, 5) == [], query
