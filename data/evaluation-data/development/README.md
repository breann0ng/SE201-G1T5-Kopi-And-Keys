# Development evaluation data

`dev_set_questions.jsonl` is the active 50-question development set: 30 combined on
17 October 2026, plus 20 added on 31 October 2026 (`origin` `tasha:finals-2026-10`) aimed
at known weak spots (price wording, bands, aliases, periods, safety). It contains policy, price, mixed, discovery, policy-changed and
unanswerable cases. Each question has routing labels and applicable answer
labels, including verbatim evidence, price filters, expected price figures and expected topic cards.

Price labels: `price_filters` may include `lease_band` / `storey_band`. `expected_price`
(`volume`, `median`) is computed with plain SQL on `data/processed/hdb_prices.db`, not through
the app. Relative periods ("past 6 months", "this year") are resolved as of `AS_OF` in
`dataset.py`; the default window is the 12 months ending at the database's latest month.
Rebuilding the database or moving `AS_OF` means refreshing those labels.

`kopi_keys.evaluation.dataset.load_questions` validates the set and resolves
evidence quotes word for word to chunks in the ACTIVE policy snapshot. A missing
quote fails validation rather than silently counting as correct evidence.

`stage1_gateway_labels.jsonl` is the generated routing sidecar, joined by `id`:

- `expected_intent`, `expected_route` and `expected_status`
- `expected_extraction` and `expected_missing_fields`
- `turns` for applicable clarification follow-ups

After changing the active set, regenerate the sidecar from the repository root:

```powershell
.\.venv\Scripts\python.exe -m kopi_keys.evaluation.dataset
```

Evaluate routing, discovery and retrieval without generating full answers:

```powershell
.\.venv\Scripts\python.exe -m kopi_keys.evaluation.run_eval --retriever hybrid
```

Hybrid retrieval needs the built vector index and Ollama embedding service.
Use `--retriever bm25` for the keyword baseline. Full end-to-end runs additionally
call the local generation model; see the
[evaluation guide](../../../backend/kopi_keys/evaluation/README.md).

`archive/` preserves older development sets and an exposed former held-out draft.
Those questions are retired, not unseen evaluation data. A fresh held-out set
must remain outside the repository and must not be used during tuning.
Development scores are not final held-out results.
