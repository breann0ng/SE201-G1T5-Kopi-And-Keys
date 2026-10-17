"""Test-only stand-ins. The app never uses these: it always retrieves from the official snapshot.

FictionalRetriever serves two made-up passages so graph tests can check routing,
citations, repairs and abstention without depending on real policy text, which
changes with every monthly refresh. Its answers report mode "demo", which is how
the UI knows to warn about fictional evidence.
"""

from datetime import date

from kopi_keys.components.policy_retrieval import TOP_K
from kopi_keys.schemas import PolicyPassage


class FictionalRetriever:
    """Two fictional passages; only queries containing "demo" match anything."""

    mode = "demo"

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
