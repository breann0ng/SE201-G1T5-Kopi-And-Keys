"""PLACEHOLDER: comparison systems from proposal section 4.1.

- no_tools_llm(question): the same model with no retrieval, SQL or verifier.
- naive_rag(question): one retrieval call plus one LLM call, no router or verifier.

Both should return a ChatResponse-like record so metrics.py can score them
alongside the full graph.
"""


def no_tools_llm(question: str):
    raise NotImplementedError


def naive_rag(question: str):
    raise NotImplementedError
