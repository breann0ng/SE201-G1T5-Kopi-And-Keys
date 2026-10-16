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
from functools import lru_cache

from ..schemas import PolicyPassage


TOP_K = 5


class PolicyRetriever(Protocol):
    def search(self, query: str, limit: int = TOP_K) -> list[PolicyPassage]: ...


class DemoPolicyRetriever:
    """Two fictional passages; only queries containing "demo" match anything."""

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
# can be swapped in main.py without touching the graph. The historical plain
# BM25 baseline stays in evaluation/run_eval.py; this adapter adds normalization,
# topic scoping and deduplication.

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
_TOKEN = re.compile(r"[a-z0-9$%]+(?:[.,][0-9]+)*")
_STOP = set("a an the am is are was were i we you my our your may can could would should please know tell me about want do does to of for in on at and or with as be it this that".split())
_FORMS = {"loans": "loan", "grants": "grant", "couples": "family", "couple": "family",
          "families": "family", "singles": "single", "residents": "resident", "citizens": "citizen", "flats": "flat"}
_GENERIC = {"hdb", "flat", "resale", "buy", "buying", "singapore"}


def policy_tokens(text: str) -> list[str]:
    tokens = [_FORMS.get(t, t) for t in _TOKEN.findall(text.lower()) if t not in _STOP]
    if "pr" in tokens or "spr" in tokens:
        tokens = [t for t in tokens if t != "pr"] + ["spr", "permanent", "resident"]
    if "ehg" in tokens:
        tokens += ["enhanced", "cpf", "housing", "grant"]
    return tokens


class SnapshotPolicyRetriever:
    """Top-k chunks from data/policy_chunks/<ACTIVE>/chunks.jsonl, never superseded ones."""

    def __init__(self, data_dir: Path = DATA_DIR, k1: float = 1.5, b: float = 0.75):
        snapshot = (data_dir / "policy_snapshots" / "ACTIVE").read_text(encoding="utf-8").strip()
        path = data_dir / "policy_chunks" / snapshot / "chunks.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.chunks = [r for r in rows if not r["superseded"]]
        if not self.chunks:
            raise ValueError(f"No current policy chunks in {path}")
        self.snapshot = snapshot
        self.docs = [Counter(policy_tokens(f"{c['section_heading']} {c['content']}")) for c in self.chunks]
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
                if t in _GENERIC:
                    score -= 0.8 * self.idf[t] * tf * (self.k1 + 1) / (tf + self.k1 * norm)
        chunk = self.chunks[i]
        heading = set(policy_tokens(chunk["section_heading"]))
        score += sum(0.6 for t in set(terms) & heading if t not in _GENERIC)
        if "recommended reads" in chunk["section_heading"].lower() or chunk.get("low_priority"):
            score *= 0.15
        if chunk.get("source_tier") == 1:
            score *= 1.15
        return score

    def search(self, query: str, limit: int = TOP_K) -> list[PolicyPassage]:
        terms = policy_tokens(query)
        if not terms or limit <= 0:
            return []
        # Scope retrieval by policy topic, not by hard-coded eligibility values.
        # This keeps a citizenship question on the eligibility page rather than
        # letting a short SPR-quota introduction outrank the actual conditions.
        pr_purchase = bool(re.search(r"\b(?:pr|spr)\b|permanent resident", query, re.I)) and bool(
            re.search(r"\bbuy\b|resale", query, re.I))
        ehg = bool(re.search(r"\behg\b|enhanced cpf housing grant", query, re.I))
        single = "single" in terms
        family = "family" in terms
        broad_loan = bool(set(terms) & {"loan", "mortgage", "financing"}) and not (
            set(terms) - _GENERIC - {"loan", "mortgage", "financing", "housing"})

        def rank(i):
            c = self.chunks[i]
            score = self._score(terms, i)
            if score <= 0:
                return 0
            heading = c["section_heading"].lower()
            if len(c["content"].split()) < 35:
                score *= 0.25
            if broad_loan and heading.strip() in {
                "housing loan from hdb", "housing loan from financial institutions",
                "housing loans for hdb flat buyers",
            }:
                score *= 3
            if pr_purchase:
                if c.get("source_slug") == "hdb-elig-couples-families" and "eligibility conditions" in heading:
                    score *= 3
                elif "non-resident" in heading or "singles" in heading:
                    score *= 0.1
            if ehg and c.get("source_slug", "").startswith("hdb-grant-"):
                score *= 1.4
                if "eligibility conditions" in heading:
                    score *= 1.5
                if (single and "families" in heading) or (family and "singles" in heading):
                    score *= 0.1
            return score

        scored = sorted(((rank(i), i) for i in range(len(self.chunks))), reverse=True)
        results, seen = [], set()
        for score, i in scored:
            if score <= 0 or len(results) >= limit:
                break
            c = self.chunks[i]
            fingerprint = " ".join(c["content"].split())
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            results.append(self._passage(c))
        return results

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


@lru_cache(maxsize=1)
def _evaluation_retriever():
    return SnapshotPolicyRetriever()


def retrieve_chunk_ids(query: str, k: int = TOP_K) -> list[str]:
    """Adapter for evaluation/run_eval.py --retriever; uses production scoring."""
    return [p.id for p in _evaluation_retriever().search(query, limit=k)]
