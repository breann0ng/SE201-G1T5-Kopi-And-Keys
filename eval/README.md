# Evaluation

```
eval/
  dataset/
    smoke.jsonl   Cases that exercise the demo fixtures; must always pass.
    dev.jsonl     Reviewed real questions used while developing (add here).
    test.jsonl    Held-out questions; only run for reported results.
  run_eval.py     Runs a dataset through the workflow and scores it.
  results/        One folder per run (gitignored except what you choose to keep).
```

## Case format (one JSON object per line)

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Stable, unique case ID, e.g. `grants-001`. |
| `family` | yes | Scenario family. Keep a family entirely in dev **or** test, never both. |
| `message` | yes | The user question sent to `/chat`. |
| `profile` | no | `BuyerProfile` fields. |
| `price_filters` | no | `PriceFilters` fields. |
| `expected_status` | yes | `answered`, `clarifying` or `abstained`. |
| `expected_citations` | no | Source IDs a correct answer must cite. |
| `forbidden_citations` | no | Source IDs that must not be cited (e.g. superseded). |
| `notes` | no | Why this label is correct; link the official source. |

## Run

```
python eval/run_eval.py eval/dataset/smoke.jsonl
```

Metrics: status accuracy, citation recall (over cases with `expected_citations`),
forbidden-citation violations, and mean retrieval rounds. Every run writes
`results/<timestamp>-<dataset>/cases.jsonl` (full responses) and `summary.json`;
failures are printed and listed in the summary.

Structural metrics are not proof of faithfulness. Answers that pass should still
be spot-checked by a human against the cited sources.
