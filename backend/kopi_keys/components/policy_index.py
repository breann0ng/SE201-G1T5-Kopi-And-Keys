"""Policy Vector Index: the ACTIVE snapshot's chunks embedded into ChromaDB.

Diagram box: "Policy Vector Index". Built offline by scripts/build_policy_index.py
into data/chroma/ (gitignored; each person builds it locally, like the price
database). One collection per snapshot date, so a new ACTIVE snapshot needs a
rebuild and an old index is never served by mistake.

Embeddings come from EmbeddingGemma via the local Ollama server, using the
model's retrieval prompts: documents as "title: <heading> | text: <content>"
(heading + content, as data/policy_chunks/README.md specifies), queries as
"task: search result | query: <question>".
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
INDEX_DIR = Path(os.getenv("KOPI_CHROMA_DIR", DATA_DIR / "chroma"))
EMBED_MODEL = os.getenv("KOPI_EMBED_MODEL", "embeddinggemma")
OLLAMA_URL = os.getenv("KOPI_EMBED_BASE_URL", os.getenv("KOPI_OLLAMA_BASE_URL", "http://127.0.0.1:11434"))
BATCH = 32


class IndexUnavailableError(RuntimeError):
    """No index for the ACTIVE snapshot, ChromaDB not installed, or Ollama unreachable."""


def active_snapshot(data_dir: Path = DATA_DIR) -> str:
    return (data_dir / "policy_snapshots" / "ACTIVE").read_text(encoding="utf-8").strip()


def collection_name(snapshot: str) -> str:
    return f"policy_{snapshot.replace('-', '_')}"


def embed(texts: list[str], *, timeout: float = 120) -> list[list[float]]:
    try:
        r = httpx.post(f"{OLLAMA_URL}/api/embed", json={"model": EMBED_MODEL, "input": texts}, timeout=timeout)
        r.raise_for_status()
    except httpx.HTTPError as error:
        raise IndexUnavailableError(f"Ollama embedding failed ({EMBED_MODEL}): {error}") from error
    return r.json()["embeddings"]


def document_text(chunk: dict) -> str:
    return f"title: {chunk['section_heading'] or chunk['policy_name']} | text: {chunk['content']}"


def query_text(question: str) -> str:
    return f"task: search result | query: {question}"


def _client():
    try:
        import chromadb
    except ImportError as error:
        raise IndexUnavailableError("chromadb is not installed (pip install -e \".[rag]\")") from error
    from chromadb.config import Settings

    # Local index only: no anonymous usage data sent to ChromaDB.
    return chromadb.PersistentClient(path=str(INDEX_DIR), settings=Settings(anonymized_telemetry=False))


def open_collection(snapshot: str):
    """The built collection for `snapshot`, or IndexUnavailableError."""
    try:
        collection = _client().get_collection(collection_name(snapshot))
    except IndexUnavailableError:
        raise
    except Exception as error:  # chromadb raises its own NotFound types across versions
        raise IndexUnavailableError(f"No policy index for snapshot {snapshot}; "
                                    "run scripts/build_policy_index.py") from error
    if collection.metadata.get("embed_model") != EMBED_MODEL:
        raise IndexUnavailableError(f"Index was built with {collection.metadata.get('embed_model')}, "
                                    f"not {EMBED_MODEL}; rebuild it")
    return collection


def build(data_dir: Path = DATA_DIR, progress=print) -> int:
    """(Re)build the index for the ACTIVE snapshot from its chunks.jsonl. Returns the chunk count."""
    snapshot = active_snapshot(data_dir)
    chunks = [json.loads(line) for line in
              (data_dir / "policy_chunks" / snapshot / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    client = _client()
    name = collection_name(snapshot)
    if name in [c.name for c in client.list_collections()]:
        client.delete_collection(name)
    collection = client.create_collection(
        name, metadata={"hnsw:space": "cosine", "embed_model": EMBED_MODEL, "snapshot": snapshot})
    for start in range(0, len(chunks), BATCH):
        batch = chunks[start:start + BATCH]
        collection.add(
            ids=[c["chunk_id"] for c in batch],
            embeddings=embed([document_text(c) for c in batch]),
            documents=[c["content"] for c in batch],
            metadatas=[{"source_slug": c["source_slug"], "source_tier": c["source_tier"],
                        "low_priority": c["low_priority"], "superseded": c["superseded"]} for c in batch],
        )
        progress(f"  embedded {min(start + BATCH, len(chunks))}/{len(chunks)}")
    return len(chunks)
