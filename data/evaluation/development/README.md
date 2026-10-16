# Development Evaluation Data

`dev_set_questions.jsonl` is the rich semantic evaluation brief. It contains policy and SQL assertions that require the team's authoritative policy snapshot and reference SQL results before answer-quality scoring is enabled.

`stage1_gateway_labels.jsonl` is the executable Stage 1 contract. Join records by `id`. It contains:

- `expected_intent`: the parser intent
- `expected_route`: canonical route: `policy`, `price`, `mixed`, `discovery`, `clarify`, or `abstain`
- `expected_extraction`: normalized profile and query fields
- `expected_missing_fields`: fields that should trigger clarification
- `expected_status`: `continue`, `clarify`, or `abstain`
- `turns`: single-turn cases or explicit clarification follow-ups

The Stage 1 evaluator must use the sidecar file until the semantic file's policy snapshot and SQL reference results are populated. Do not treat unresolved policy or SQL facts as passing ground truth.

The held-out set must use the same label schema but remain outside the repository.
