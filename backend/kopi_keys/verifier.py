"""Structural checks only. Semantic claim support needs separate evaluation."""

from .state import AdvisorState


def verify(state: AdvisorState) -> list[str]:
    decision = state["decision"]
    if decision is None or decision.action != "answer":
        return ["No answer draft was provided."]
    errors = []
    sources = {passage.id: passage for passage in state["passages"]}
    if not decision.claims and state["price_result"] is None:
        errors.append("An answer requires cited claims or an executed price result.")
    for claim in decision.claims:
        if not claim.citation_ids:
            errors.append("A policy claim has no citation.")
        for source_id in claim.citation_ids:
            source = sources.get(source_id)
            if source is None:
                errors.append(f"Unknown citation: {source_id}")
            elif source.superseded:
                errors.append(f"Superseded source: {source_id}")
    price = state["price_result"]
    if price is not None:
        if price.filters != state["request"].price_filters:
            errors.append("Price result does not match the requested filters.")
        if price.count == 0:
            errors.append("No matching transactions support a price benchmark.")
        values = (price.minimum, price.median, price.maximum)
        if any(value is None for value in values):
            errors.append("Price statistics are incomplete.")
        elif not price.minimum <= price.median <= price.maximum:
            errors.append("Price statistics are inconsistent.")
    return errors
