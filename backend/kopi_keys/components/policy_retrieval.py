"""Policy Retrieval Tool: return the top-k dated policy chunks for a query.

Diagram box: "Policy Retrieval Tool (deterministic script)" over the Policy
Vector Index. The app uses SnapshotPolicyRetriever (keyword search over the real
policy chunks) until a ChromaDB + EmbeddingGemma adapter implementing the same
`PolicyRetriever.search` protocol replaces it. DemoPolicyRetriever stays for tests. Preserve
source URL, effective date, snapshot ID and superseded status on every chunk.
"""

import json
import math
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Protocol

from ..schemas import PolicyPassage


TOP_K = 5


class PolicyRetriever(Protocol):
    def search(self, query: str, limit: int = TOP_K) -> list[PolicyPassage]: ...


class DemoPolicyRetriever:
    """Two fictional passages; only queries containing "demo" match anything."""

    mode = "demo"  # reported as ChatResponse.mode, so the UI can warn about fictional evidence

    def search(self, query: str, limit: int = TOP_K) -> list[PolicyPassage]:
        query = query.lower()
        if "demo" not in query:
            return []
        related = "related condition" in query
        passage = PolicyPassage(
            id="demo-condition" if related else "demo-programme",
            title="Fictional demo condition" if related else "Fictional demo programme",
            text=(
                "The fictional demo condition requires a completed demo checklist."
                if related else
                "The fictional demo programme requires the related demo condition to be met."
            ),
            source_url="demo://condition" if related else "demo://programme",
            effective_date=date(2000, 1, 1),
            verified_on=date(2000, 1, 1),
            snapshot_id="fictional-demo-v1",
        )
        return [passage][:limit]


# --- Snapshot retriever (interim) ------------------------------------------
# Keyword search (BM25) over the ACTIVE policy snapshot's chunks. Interim until
# the ChromaDB + EmbeddingGemma retriever exists: same `search` protocol, so it
# can be swapped in main.py without touching the graph. Same scoring as the
# BM25 baseline in evaluation/run_eval.py (Recall@5 38% on the dev split).

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
_TOKEN = re.compile(r"[a-z0-9$%]+(?:[.,][0-9]+)*")


class SnapshotPolicyRetriever:
    """Top-k chunks from data/policy_chunks/<ACTIVE>/chunks.jsonl, never superseded ones."""

    mode = "snapshot"  # reported as ChatResponse.mode: real official evidence

    def __init__(self, data_dir: Path = DATA_DIR, k1: float = 1.5, b: float = 0.75):
        snapshot = (data_dir / "policy_snapshots" / "ACTIVE").read_text(encoding="utf-8").strip()
        path = data_dir / "policy_chunks" / snapshot / "chunks.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.chunks = [r for r in rows if not r["superseded"]]
        if not self.chunks:
            raise ValueError(f"No current policy chunks in {path}")
        self.snapshot = snapshot
        self.docs = [Counter(_TOKEN.findall(f"{c['section_heading']} {c['content']}".lower())) for c in self.chunks]
        self.lens = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.lens) / len(self.lens)
        df = Counter(t for d in self.docs for t in d)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.k1, self.b = k1, b

    def _score(self, terms: list[str], i: int) -> float:
        d, score = self.docs[i], 0.0
        for t in terms:
            tf = d.get(t)
            if tf:
                norm = 1 - self.b + self.b * self.lens[i] / self.avg
                score += self.idf[t] * tf * (self.k1 + 1) / (tf + self.k1 * norm)
        return score

    def search(self, query: str, limit: int = TOP_K) -> list[PolicyPassage]:
        terms = _TOKEN.findall(query.lower())
        scored = sorted(((self._score(terms, i), i) for i in range(len(self.chunks))), reverse=True)
        return [self._passage(self.chunks[i]) for s, i in scored[:limit] if s > 0]

    def _passage(self, c: dict) -> PolicyPassage:
        heading = c["section_heading"]
        return PolicyPassage(
            id=c["chunk_id"],
            title=f"{c['policy_name']}: {heading}" if heading else c["policy_name"],
            text=c["content"],
            source_url=c["source_url"],
            effective_date=c["effective_date"],
            verified_on=c["verified_on"],
            page_last_updated=c["page_last_updated"],
            snapshot_id=c["snapshot_date"],
            superseded=c["superseded"],
        )
