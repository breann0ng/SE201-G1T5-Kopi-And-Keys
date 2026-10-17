"""Comparison systems (proposal section 4.1) and retrievers to score.

Retrievers for Recall@5 (`retriever(name)` returns fn(query, k) -> [chunk_id]):
- "bm25":   KeywordPolicyRetriever, keyword search only (the baseline).
- "hybrid": HybridPolicyRetriever, BM25 + EmbeddingGemma vectors (needs the index).
- "module:function": any other function with the same signature.

Still to build (TODO, team): the two answer-level baselines below. Both should
return a ChatResponse-like dict so metrics.end_to_end can score them alongside
the full graph.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable


def retriever(name: str = "bm25") -> tuple[Callable[[str, int], list[str]], str]:
    if ":" in name:
        module, _, fn = name.partition(":")
        return getattr(importlib.import_module(module), fn), name
    from ..components import policy_retrieval

    impl = {"bm25": policy_retrieval.KeywordPolicyRetriever,
            "hybrid": getattr(policy_retrieval, "HybridPolicyRetriever", None)}.get(name)
    if impl is None:
        raise SystemExit(f"Unknown retriever {name!r}: use bm25, hybrid or module:function")
    instance = impl()
    label = getattr(instance, "description", name)
    return (lambda query, k: [p.id for p in instance.search(query, limit=k)]), label


def no_tools_llm(question: str) -> dict:
    """TODO: the same model with no retrieval, SQL or verifier."""
    raise NotImplementedError


def naive_rag(question: str) -> dict:
    """TODO: one retrieval call plus one LLM call, no router or verifier."""
    raise NotImplementedError
