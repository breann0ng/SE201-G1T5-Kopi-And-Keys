"""Policy Vector Index: the ACTIVE snapshot's chunks embedded into ChromaDB.

Diagram box: "Policy Vector Index". Built offline by scripts/build_policy_index.py
into data/chroma/ (gitignored; each person builds it locally, like the price
database). One collection per snapshot date, so a new ACTIVE snapshot needs a
rebuild and an old index is never served by mistake.

Embeddings come from EmbeddingGemma via the local Ollama server, using the
model's retrieval prompts: documents as "title: <heading> | text: <content>"
(heading + content, as data/policy_chunks/README.md specifies), queries as
"task: search result | query: <question>".

Added 2026-11-06: the document vectors are committed per snapshot in
data/policy_index/<date>/ (vectors.f32 + vectors.json), so a teammate's build
loads them in seconds instead of embedding every chunk. A vector is reused only
when its chunk's embedded text (heading + content) and the model digest match;
anything else is re-embedded. Questions are still embedded at query time, so the
app still needs the same EmbeddingGemma locally.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from array import array
from pathlib import Path

import httpx

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
INDEX_DIR = Path(os.getenv("KOPI_CHROMA_DIR", DATA_DIR / "chroma"))
VECTORS_DIR = DATA_DIR / "policy_index"
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


def model_digest(timeout: float = 10) -> str | None:
    """The local Ollama digest of EMBED_MODEL, or None when Ollama or the model is missing."""
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=timeout)
        r.raise_for_status()
    except httpx.HTTPError:
        return None
    names = {EMBED_MODEL, f"{EMBED_MODEL}:latest"}
    return next((m.get("digest") for m in r.json().get("models", []) if m.get("name") in names), None)


def document_sha256(chunk: dict) -> str:
    """Hash of the exact text embedded for a chunk (heading + content)."""
    return hashlib.sha256(document_text(chunk).encode("utf-8")).hexdigest()


def load_vectors(snapshot: str, data_dir: Path = DATA_DIR) -> tuple[dict[str, list[float]], dict | None]:
    """Stored vectors for a snapshot as {document_sha256: vector}, and their metadata."""
    folder = data_dir / "policy_index" / snapshot
    if not (folder / "vectors.json").exists() or not (folder / "vectors.f32").exists():
        return {}, None
    meta = json.loads((folder / "vectors.json").read_text(encoding="utf-8"))
    raw = array("f")
    raw.frombytes((folder / "vectors.f32").read_bytes())
    if meta.get("byteorder", "little") != sys.byteorder:
        raw.byteswap()
    dim, hashes = meta["dim"], meta["document_sha256"]
    if len(raw) != dim * len(hashes):
        return {}, None  # truncated or mismatched file: re-embed rather than trust it
    return {h: raw[i * dim:(i + 1) * dim].tolist() for i, h in enumerate(hashes)}, meta


def save_vectors(snapshot: str, chunks: list[dict], vectors: list[list[float]], digest: str | None,
                 data_dir: Path = DATA_DIR) -> Path:
    folder = data_dir / "policy_index" / snapshot
    folder.mkdir(parents=True, exist_ok=True)
    raw = array("f", (x for v in vectors for x in v))
    (folder / "vectors.f32").write_bytes(raw.tobytes())
    meta = {"snapshot": snapshot, "embed_model": EMBED_MODEL, "model_digest": digest,
            "dim": len(vectors[0]), "byteorder": sys.byteorder, "document_text": "title: <heading> | text: <content>",
            "chunk_ids": [c["chunk_id"] for c in chunks], "document_sha256": [document_sha256(c) for c in chunks]}
    (folder / "vectors.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    return folder


def build(data_dir: Path = DATA_DIR, progress=print) -> int:
    """(Re)build the index for the ACTIVE snapshot from its chunks.jsonl. Returns the chunk count.

    Reuses data/policy_index/<snapshot>/ vectors for unchanged chunks, embeds the
    rest with Ollama, then saves every vector back there for teammates.
    """
    snapshot = active_snapshot(data_dir)
    chunks = [json.loads(line) for line in
              (data_dir / "policy_chunks" / snapshot / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    stored, meta = load_vectors(snapshot, data_dir)
    digest = model_digest()
    if meta and (meta.get("embed_model") != EMBED_MODEL or (digest and meta.get("model_digest") != digest)):
        progress(f"  stored vectors are from {meta.get('embed_model')} {str(meta.get('model_digest'))[:12]}, "
                 f"not the local {EMBED_MODEL} {str(digest)[:12]}: re-embedding every chunk")
        stored = {}
    hashes = [document_sha256(c) for c in chunks]
    missing = [i for i, h in enumerate(hashes) if h not in stored]
    progress(f"  {len(chunks) - len(missing)} stored vectors reused, {len(missing)} to embed")
    for start in range(0, len(missing), BATCH):
        batch = missing[start:start + BATCH]
        for i, vector in zip(batch, embed([document_text(chunks[i]) for i in batch])):
            stored[hashes[i]] = vector
        progress(f"  embedded {min(start + BATCH, len(missing))}/{len(missing)}")
    vectors = [stored[h] for h in hashes]
    if missing or meta is None or meta.get("chunk_ids") != [c["chunk_id"] for c in chunks]:
        save_vectors(snapshot, chunks, vectors, digest or (meta or {}).get("model_digest"), data_dir)

    client = _client()
    name = collection_name(snapshot)
    if name in [c.name for c in client.list_collections()]:
        client.delete_collection(name)
    collection = client.create_collection(
        name, metadata={"hnsw:space": "cosine", "embed_model": EMBED_MODEL, "snapshot": snapshot})
    for start in range(0, len(chunks), BATCH * 8):
        batch = chunks[start:start + BATCH * 8]
        collection.add(
            ids=[c["chunk_id"] for c in batch],
            embeddings=vectors[start:start + BATCH * 8],
            documents=[c["content"] for c in batch],
            metadatas=[{"source_slug": c["source_slug"], "source_tier": c["source_tier"],
                        "low_priority": c["low_priority"], "superseded": c["superseded"]} for c in batch],
        )
    return len(chunks)


def missing_from_index(collection, chunk_ids) -> list[str]:
    """Current chunk IDs the built index lacks (a partial build, or chunks changed since)."""
    indexed = set(collection.get(include=[])["ids"])
    return [i for i in chunk_ids if i not in indexed]
