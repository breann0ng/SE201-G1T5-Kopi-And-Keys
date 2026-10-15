"""PLACEHOLDER: Appendix E metrics. Each takes labelled records and final states.

Targets from the proposal:
- routing_accuracy            >= 90%
- numerical_accuracy          100% (every figure from an executed query)
- retrieval_recall_at_5       >= 85% of policy questions
- citation_faithfulness       >= 95% supported (manual review input)
- abstention_accuracy         unsafe <= 5%, over-abstention <= 10%
- framing_compliance          >= 90% (manual review input)
- discovery_precision_recall  >= 80% / >= 70%
- staleness_error_rate        0%
"""


def routing_accuracy(records, states) -> float:
    raise NotImplementedError


def retrieval_recall_at_5(records, states) -> float:
    raise NotImplementedError


def abstention_accuracy(records, states) -> dict:
    raise NotImplementedError


def discovery_precision_recall(records, states) -> dict:
    raise NotImplementedError


def staleness_error_rate(records, states) -> float:
    raise NotImplementedError
