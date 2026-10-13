from datetime import date
from typing import Protocol

from ..schemas import PolicyPassage


class PolicyRetriever(Protocol):
    def search(self, query: str, limit: int = 5) -> list[PolicyPassage]: ...


class DemoPolicyRetriever:
    """Two fictional passages exercise retrieval of an interlocking condition."""

    def search(self, query: str, limit: int = 5) -> list[PolicyPassage]:
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
            snapshot_id="fictional-demo-v1",
        )
        return [passage][:limit]
