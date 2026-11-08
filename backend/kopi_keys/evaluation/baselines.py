"""Comparison systems (proposal section 4.1) and retrievers to score.

Retrievers for Recall@5 (`retriever(name)` returns fn(query, k) -> [chunk_id]):
- "bm25":   KeywordPolicyRetriever, keyword search only (the baseline).
- "hybrid": HybridPolicyRetriever, BM25 + EmbeddingGemma vectors (needs the index).
- "module:function": any other function with the same signature.

Answer-level baselines (`run_eval --system no-tools|naive-rag`), each returning a
ChatResponse-like dict so metrics.end_to_end scores them alongside the full graph:
- no_tools_llm: the same model, no retrieval, SQL or verifier.
- naive_rag:    one hybrid retrieval call plus one model call, no router or verifier.
- naive_rag_dense: the same, but dense-only retrieval (EmbeddingGemma top 5, no BM25,
  no fusion weights): the textbook single-call RAG baseline.
Each takes an optional `history` (earlier user/assistant turns), so a scripted
follow-up reply reaches the model as turn 2. evaluation/run_baselines.py runs them.
"""

from __future__ import annotations

import importlib
import json
import re
from collections.abc import Callable
from dataclasses import replace
from functools import lru_cache
from time import perf_counter


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


# --- Answer-level baselines (proposal section 4.1) ------------------------
# Same model and policy token budget as the app (llm.OllamaEngine.for_policy), one call each.
# Both use one abstention rule, so unsafe-answering and over-abstention compare fairly:
# the prompt asks for exactly "I don't know" when unsure, and ABSTAINED also catches
# other plain refusals.

ABSTAINED = re.compile(r"^\W*I (?:do not|don't) know\b|\b(?:I (?:cannot|can't|am unable to) "
                       r"(?:answer|confirm|provide|say)|unable to (?:answer|confirm|provide))\b", re.I)
_SYSTEM = ("You answer questions from people buying an HDB resale flat in Singapore, about HDB/CPF "
           "policy and resale prices. Answer concisely. If you cannot answer reliably, reply exactly: "
           "I don't know.")
_CITED = re.compile(r"\[(CHUNK_[A-Z]+_\d+)\]")


@lru_cache(maxsize=1)
def _engine():
    from ..llm import OllamaEngine, OllamaSettings

    return OllamaEngine(replace(OllamaSettings.from_env(), context_size=4096, max_output_tokens=850))


def _profile_line(profile: dict | None) -> str:
    filled = {k: v for k, v in (profile or {}).items() if v not in (None, "")}
    return f"\n\nAbout me: {json.dumps(filled)}" if filled else ""


def _response(system: str, text: str, started: float, citations: list[dict] | None = None) -> dict:
    """A ChatResponse-like dict for metrics.end_to_end."""
    return {"system": system, "status": "abstained" if ABSTAINED.search(text) else "answered",
            "route": None, "message": text, "citations": citations or [], "price_result": None,
            "latency_seconds": round(perf_counter() - started, 3)}


def _messages(user: str, history: list[dict] | None) -> list[dict]:
    return ([{"role": "system", "content": _SYSTEM}]
            + [{"role": t["role"], "content": t["content"]} for t in history or []]
            + [{"role": "user", "content": user}])


def no_tools_llm(question: str, profile: dict | None = None, history: list[dict] | None = None) -> dict:
    """The same model with no retrieval, SQL, router or verifier: one call per turn."""
    from ..llm import ModelEngineError

    started = perf_counter()
    try:
        out = _engine().complete(_messages(question + _profile_line(profile), history))
    except ModelEngineError as error:
        return {"error": str(error)}
    return _response("no-tools", out.text, started)


@lru_cache(maxsize=1)
def _naive_retriever():
    from ..components.policy_retrieval import HybridPolicyRetriever

    return HybridPolicyRetriever()


def _dense_top5(query: str):
    r = _naive_retriever()
    if r.collection is None:
        from ..components.policy_index import IndexUnavailableError
        raise IndexUnavailableError("dense-only naive RAG needs the policy index")
    return r.get(r._dense(query)[:5])


def naive_rag(question: str, profile: dict | None = None, history: list[dict] | None = None,
              *, dense_only: bool = False) -> dict:
    """One retrieval call (the app's hybrid retriever, or dense only, top 5) plus one model call.

    No router, SQL, topic cards or verifier. Citations are the supplied passages
    the answer names as [CHUNK_ID]; IDs that were not supplied are ignored. On a
    follow-up turn the search query is the earlier user turns plus this one.
    """
    from ..llm import ModelEngineError

    started = perf_counter()
    query = " ".join([t["content"] for t in history or [] if t["role"] == "user"] + [question])
    passages = _dense_top5(query) if dense_only else _naive_retriever().search(query)
    context = "\n\n".join(f"[{p.id}] {p.title}\n{p.text}" for p in passages)
    prompt = (f"Passages from official HDB/CPF pages:\n\n{context}\n\nQuestion: {question}"
              f"{_profile_line(profile)}\n\nAnswer from the passages and cite each one you use as [CHUNK_ID].")
    try:
        out = _engine().complete(_messages(prompt, history))
    except ModelEngineError as error:
        return {"error": str(error)}
    by_id = {p.id: p for p in passages}
    cited = [by_id[i] for i in dict.fromkeys(_CITED.findall(out.text)) if i in by_id]
    return _response("naive-rag-dense" if dense_only else "naive-rag", out.text, started,
                     [{"id": p.id, "text": p.text} for p in cited])


def naive_rag_dense(question: str, profile: dict | None = None, history: list[dict] | None = None) -> dict:
    return naive_rag(question, profile, history, dense_only=True)


SYSTEMS = {"no-tools": no_tools_llm, "naive-rag": naive_rag, "naive-rag-dense": naive_rag_dense}
