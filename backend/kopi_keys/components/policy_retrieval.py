"""Policy Retrieval Tool: return the top-k dated policy chunks for a query.

Diagram box: "Policy Retrieval Tool (deterministic script)" over the Policy
Vector Index. Replace DemoPolicyRetriever with a ChromaDB + EmbeddingGemma
adapter implementing the same `PolicyRetriever.search` protocol. Preserve
source URL, effective date, snapshot ID and superseded status on every chunk.
"""

from datetime import date
from typing import Protocol

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
