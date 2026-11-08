"""Policy Retrieval Tool: return the top-k dated policy chunks for a query.

Diagram box: "Policy Retrieval Tool (deterministic script)" over the Policy
Vector Index. The app uses HybridPolicyRetriever: a keyword ranker
(KeywordPolicyRetriever) fused with EmbeddingGemma vectors in ChromaDB
(components/policy_index.py). Without the index or Ollama it falls back to the
keyword ranker alone. Every passage keeps its source URL, dates, snapshot ID and superseded status.
"""

import json
import math
import re
import warnings
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from ..schemas import PolicyPassage


TOP_K = 5


class PolicyRetriever(Protocol):
    def search(self, query: str, limit: int = TOP_K) -> list[PolicyPassage]: ...


# --- Keyword ranker ---------------------------------------------------------
# BM25 over heading + content with general query normalisation. There are no
# rules for particular questions: every adjustment below applies to all queries.

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
_TOKEN = re.compile(r"[a-z0-9$%]+(?:[.,][0-9]+)*")
# Filler with no policy meaning ("may I know about ...", "please tell me ...").
_STOP = frozenset(
    "a an the am is are was were be been i we you he she they my our your his her their me us "
    "may can could would should will shall please know tell about want wants wanted do does did "
    "to of for in on at by and or with as it this that these those there here what which who how "
    "any some get got have has had just also so if then than".split())
# Same meaning, different words: abbreviations and HDB's own terms.
_SYNONYMS = {
    "pr": ["spr", "permanent", "resident"],
    "ehg": ["enhanced", "cpf", "housing", "grant"],
    "phg": ["proximity", "housing", "grant"],
    "hfe": ["flat", "eligibility", "letter"],
    "otp": ["option", "purchase"],
    "ltv": ["loan", "value"],
    "mop": ["minimum", "occupation", "period"],
    "eip": ["ethnic", "integration"],
    "couple": ["family"], "married": ["family"], "spouse": ["family"],
    "mortgage": ["loan"], "financing": ["loan"],
    # Added 2026-11-08: everyday words for HDB's terms. HDB writes "parents/ child",
    # "private residential property" and "ethnic group"; buyers say mum, condo, Chinese.
    **{w: ["parent"] for w in ("mum", "mom", "mother", "mummy", "mommy", "dad", "father", "daddy", "papa", "mama")},
    **{w: ["private", "residential", "property"] for w in ("condo", "condominium")},
    **{w: ["ethnic", "integration", "quota"] for w in ("chinese", "malay", "indian", "eurasian", "race", "racial",
                                                         "ethnicity")},
}
# Words in almost every chunk: they shouldn't decide the ranking.
_GENERIC = frozenset({"hdb", "flat", "resale", "buy", "buying", "singapore", "housing"})
_GENERIC_WEIGHT = 0.2
_HEADING_BONUS = 0.6          # per query word that also appears in the section heading
_TIER_WEIGHT = {1: 1.0, 2: 0.85, 3: 0.7}  # official scheme pages first (decision D7)
_LOW_PRIORITY_WEIGHT = 0.3    # thin pages and "recommended reads" link lists
# Added 2026-10-17: HDB's worked examples ("Details of Mr B, Mr C, and Mr D") describe a
# fictional household, not a rule. They outranked the rules for eligibility questions, and the model
# stitched their cells into an invented quote. Ranked down unless the question asks for an example.
_WORKED_EXAMPLE = re.compile(r"\|\s*Details of (?:Mr|Mrs|Ms|Mdm|Miss)\b")
_WORKED_EXAMPLE_WEIGHT = 0.3


def is_worked_example(content: str) -> bool:
    return bool(_WORKED_EXAMPLE.match(content))


# Added 2026-10-18: scheme focus. "What is the income ceiling for an HDB loan?" from a family
# profile became "... loan families" and the grant pages for families outranked the loan page.
# When a question names loans but not grants (or the reverse), the named scheme's chunks rank
# higher and the other's lower. Questions naming both, or neither, are unchanged.
_LOAN_WORDS = re.compile(r"\b(?:loans?|mortgage|financing|ltv|loan-to-value|borrow\w*|instal+ments?)\b", re.I)
_GRANT_WORDS = re.compile(r"\b(?:grants?|ehg|phg|subsid\w*)\b", re.I)
_FOCUS_WEIGHT, _OFF_FOCUS_WEIGHT = 1.5, 0.6


def scheme_focus(query: str) -> str | None:
    loan, grant = bool(_LOAN_WORDS.search(query)), bool(_GRANT_WORDS.search(query))
    return "loan" if loan and not grant else "grant" if grant and not loan else None
_SHORT_CHUNK_WORDS = 35       # very short chunks are usually intros, not conditions
_SHORT_CHUNK_WEIGHT = 0.4


def _stem(token: str) -> str:
    """Light plural folding: grants -> grant, families -> family, couples -> couple."""
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def policy_tokens(text: str) -> list[str]:
    """Search terms: filler removed, plurals folded, abbreviations expanded."""
    tokens = []
    for raw in _TOKEN.findall(text.lower()):
        if raw in _STOP:
            continue
        token = _stem(raw)
        tokens.append(token)
        tokens += _SYNONYMS.get(token, [])
    return tokens


def _fingerprint(text: str) -> str:
    return " ".join(text.split()).casefold()


class KeywordPolicyRetriever:
    """Keyword-ranked chunks from data/policy_chunks/<ACTIVE>/chunks.jsonl, never superseded ones."""

    mode = "snapshot"  # reported as ChatResponse.mode: real official evidence
    description = "keyword (bm25)"

    def __init__(self, data_dir: Path = DATA_DIR, k1: float = 1.5, b: float = 0.75):
        snapshot = (data_dir / "policy_snapshots" / "ACTIVE").read_text(encoding="utf-8").strip()
        path = data_dir / "policy_chunks" / snapshot / "chunks.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.chunks = [r for r in rows if not r["superseded"]]
        if not self.chunks:
            raise ValueError(f"No current policy chunks in {path}")
        self.snapshot = snapshot
        self.by_id = {c["chunk_id"]: c for c in self.chunks}
        self.docs = [Counter(policy_tokens(f"{c['section_heading']} {c['content']}")) for c in self.chunks]
        self.headings = [set(policy_tokens(c["section_heading"])) for c in self.chunks]
        self.lens = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.lens) / len(self.lens)
        df = Counter(t for d in self.docs for t in d)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.k1, self.b = k1, b

    def _score(self, terms: list[str], i: int, heading_bonus: float = _HEADING_BONUS) -> float:
        doc, score = self.docs[i], 0.0
        norm = 1 - self.b + self.b * self.lens[i] / self.avg
        for t in terms:
            tf = doc.get(t)
            if tf:
                weight = _GENERIC_WEIGHT if t in _GENERIC else 1.0
                score += weight * self.idf[t] * tf * (self.k1 + 1) / (tf + self.k1 * norm)
        if score <= 0:
            return 0.0
        score += heading_bonus * len((set(terms) - _GENERIC) & self.headings[i])
        c = self.chunks[i]
        score *= _TIER_WEIGHT.get(c.get("source_tier"), 0.7)
        if c.get("low_priority") or "recommended reads" in c["section_heading"].lower():
            score *= _LOW_PRIORITY_WEIGHT
        if len(c["content"].split()) < _SHORT_CHUNK_WORDS:
            score *= _SHORT_CHUNK_WEIGHT
        return score

    def ranked_ids(self, query: str, depth: int, heading_bonus: float | None = None) -> list[str]:
        """Chunk IDs by keyword score, best first, with identical text removed.

        heading_bonus defaults to _HEADING_BONUS (keyword-only search); the hybrid
        retriever passes its own (HYBRID_HEADING_BONUS).
        """
        terms = policy_tokens(query)
        if not terms or depth <= 0:
            return []
        bonus = _HEADING_BONUS if heading_bonus is None else heading_bonus
        # Best score first; equal scores keep file order, so the first copy of a duplicate wins.
        scored = sorted(((self._score(terms, i, bonus), i) for i in range(len(self.chunks))),
                        key=lambda s: (-s[0], s[1]))
        out, seen = [], set()
        for score, i in scored:
            if score <= 0 or len(out) >= depth:
                break
            fingerprint = _fingerprint(self.chunks[i]["content"])
            if fingerprint not in seen:
                seen.add(fingerprint)
                out.append(self.chunks[i]["chunk_id"])
        return out

    def search(self, query: str, limit: int = TOP_K) -> list[PolicyPassage]:
        return self.get(self.ranked_ids(query, limit))

    def get(self, chunk_ids: list[str]) -> list[PolicyPassage]:
        """Current passages for the given chunk IDs (unknown or superseded IDs are skipped)."""
        return [self._passage(self.by_id[i]) for i in chunk_ids if i in self.by_id]

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


# --- Hybrid retriever (proposal Stage 3: dense + keyword) ------------------

# Tuned 2026-11-06 with evaluation/retrieval_sweep.py on the 29 dev questions with evidence
# (re-chunked snapshot): Recall@5 16/29 -> 20/29, MRR@10 0.497 -> 0.541. Chosen from a plateau
# of settings scoring 19-20 (neighbour mean 19.4), changing the fewest values. Was 60 / 30 / 0.6.
RRF_K = 20                  # reciprocal rank fusion constant
CANDIDATES = 20             # depth taken from each ranker
DENSE_WEIGHT = 3.0          # dense ranks count 3x keyword ranks
HYBRID_HEADING_BONUS = 0.0  # every top setting had none; keyword-only search keeps _HEADING_BONUS
                            # (dropping it there cost one hit, 14 -> 13 of 29)


class HybridPolicyRetriever:
    """Keyword ranker + EmbeddingGemma vectors (ChromaDB), fused by reciprocal rank.

    Source tier, low priority and duplicate removal are applied again after fusion.
    Falls back to the keyword ranker alone when the index, ChromaDB or Ollama is
    unavailable; `description` says which mode is serving.
    """

    mode = "snapshot"

    def __init__(self, data_dir: Path = DATA_DIR):
        from . import policy_index

        self._index = policy_index
        self.keyword = KeywordPolicyRetriever(data_dir)
        try:
            self.collection = policy_index.open_collection(self.keyword.snapshot)
            self.description = f"hybrid (keyword + {policy_index.EMBED_MODEL})"
        except policy_index.IndexUnavailableError as error:
            self.collection = None
            self.description = f"keyword only ({error})"
            warnings.warn(f"Policy search is keyword-only: {error}", stacklevel=2)
        else:
            # Added 2026-11-06: a build cut short, or chunks changed since the build, leaves
            # chunks that dense search can never return.
            missing = policy_index.missing_from_index(self.collection, self.keyword.by_id)
            if missing:
                self.description += f", {len(missing)} chunks missing from the index"
                warnings.warn(f"The policy index lacks {len(missing)} of {len(self.keyword.by_id)} current chunks; "
                              "run scripts/build_policy_index.py", stacklevel=2)

    def _dense(self, query: str) -> list[str]:
        vector = self._index.embed([self._index.query_text(query)], timeout=30)[0]
        hits = self.collection.query(query_embeddings=[vector], n_results=CANDIDATES,
                                     where={"superseded": False})
        return hits["ids"][0]

    def require_dense(self) -> None:
        """Raise IndexUnavailableError unless every current chunk is searchable by vector.

        For evaluation: a score labelled "hybrid" must not come from keyword-only search.
        """
        if self.collection is None:
            raise self._index.IndexUnavailableError(self.description)
        missing = self._index.missing_from_index(self.collection, self.keyword.by_id)
        if missing:
            raise self._index.IndexUnavailableError(
                f"the policy index lacks {len(missing)} current chunks; run scripts/build_policy_index.py")

    def search(self, query: str, limit: int = TOP_K, *, strict: bool = False) -> list[PolicyPassage]:
        """Fused top `limit`. The app falls back to keyword ranking when the index or Ollama
        is unavailable; strict=True (evaluation) raises IndexUnavailableError instead."""
        if strict and self.collection is None:
            raise self._index.IndexUnavailableError(self.description)
        keyword = self.keyword.ranked_ids(query, CANDIDATES, heading_bonus=HYBRID_HEADING_BONUS)
        dense = None
        if self.collection is not None:
            try:
                dense = self._dense(query)
            except self._index.IndexUnavailableError:
                if strict:
                    raise
                pass  # Ollama down: keyword ranking alone for this query
        return self.keyword.get(fuse(self.keyword.by_id, query, keyword, dense, limit))

    def get(self, chunk_ids: list[str]) -> list[PolicyPassage]:
        return self.keyword.get(chunk_ids)


def fuse(by_id: dict[str, dict], query: str, keyword: list[str], dense: list[str] | None, limit: int = TOP_K,
         *, dense_weight: float = DENSE_WEIGHT, rrf_k: int = RRF_K, candidates: int = CANDIDATES) -> list[str]:
    """Reciprocal-rank fusion of the keyword and dense rankings, then source tier, low
    priority, worked examples and scheme focus, with identical text removed.

    The parameters default to the app's settings; evaluation/retrieval_sweep.py varies them.
    """
    rankings = [(1.0, keyword[:candidates])]
    if dense is not None:
        rankings.append((dense_weight, dense[:candidates]))
    wants_example = bool(re.search(r"\bexamples?\b|\bworked\b|\billustrat", query, re.I))
    focus = scheme_focus(query)
    scores: dict[str, float] = {}
    for weight, ranking in rankings:
        for rank, chunk_id in enumerate(ranking):
            if chunk_id in by_id:
                scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (rrf_k + rank + 1)
    for chunk_id in scores:
        c = by_id[chunk_id]
        scores[chunk_id] *= _TIER_WEIGHT.get(c.get("source_tier"), 0.7)
        if c.get("low_priority"):
            scores[chunk_id] *= _LOW_PRIORITY_WEIGHT
        if is_worked_example(c["content"]) and not wants_example:
            scores[chunk_id] *= _WORKED_EXAMPLE_WEIGHT
        if focus is not None:
            name = c.get("policy_name", "").lower()
            kind = "loan" if "loan" in name else "grant" if "grant" in name else None
            if kind is not None:
                scores[chunk_id] *= _FOCUS_WEIGHT if kind == focus else _OFF_FOCUS_WEIGHT
    best, seen = [], set()
    for chunk_id in sorted(scores, key=scores.get, reverse=True):
        fingerprint = _fingerprint(by_id[chunk_id]["content"])
        if fingerprint not in seen:
            seen.add(fingerprint)
            best.append(chunk_id)
        if len(best) == limit:
            break
    return best


@lru_cache(maxsize=1)
def _evaluation_retriever():
    return HybridPolicyRetriever()


def retrieve_chunk_ids(query: str, k: int = TOP_K) -> list[str]:
    """Production retrieval as chunk IDs, for the evaluation runner (--retriever)."""
    return [p.id for p in _evaluation_retriever().search(query, limit=k)]
