# Evaluation (DRAFT v0.1)

The labelled question set and a deterministic runner for the metrics in the proposal (§4, Appendix E).
Owner: Person 4. The labels need a second team member's review before held-out results are reported.

## Note for the team: two eval sets (2026-10-16, to agree with Breann)

`main` (PR #1) also has evaluation files, in different folders, so nothing overwrites anything:

| | Breann (`main`) | This folder |
|---|---|---|
| Questions | `data/evaluation/development/`: 30 dev questions and the Stage 1 router labels | `questions.json`: 50 questions (30 dev, 20 held-out) with verbatim evidence tied to chunk IDs |
| Runner | `backend/kopi_keys/evaluation/run_eval.py`: placeholder, not built yet | `run_eval.py`: working |
| Metrics / baselines | `backend/kopi_keys/evaluation/metrics.py`, `baselines.py`: starters | inside `run_eval.py` (discovery metrics, BM25 baseline) |

Proposal: keep both question sets for now, because they test different things:
- Breann's covers routing and answer behaviour.
- This one covers discovery, retrieval and policy changes.

Use a single runner. This folder's `run_eval.py` would fill in the placeholder and later read both sets. Not changed yet; waiting for team agreement.

## Files

| File | What |
|---|---|
| `questions.json` | **Authored** set: 50 questions. Each evidence entry is `{source, quote}`: a source-page pattern and a verbatim quote |
| `build_eval_set.py` | Resolves every quote to chunk IDs in the ACTIVE snapshot and fails if a quote isn't found word for word. Writes `eval_set.jsonl` |
| `eval_set.jsonl` | Generated. Don't edit by hand; rebuild after every snapshot goes live |
| `run_eval.py` | Runs the metrics and writes `results/<time>_<split>.json` (gitignored) |

## Question set

| Category | Total | Dev | Held-out |
|---|---|---|---|
| policy | 12 | 7 | 5 |
| price | 10 | 6 | 4 |
| mixed | 8 | 5 | 3 |
| discovery | 6 | 4 | 2 |
| policy_changed | 6 | 4 | 2 |
| unanswerable | 8 | 4 | 4 |
| **Total** | **50** | **30** | **20** |

- **Held-out split:** it only runs with `--final`. Don't look at it while iterating.
- **Price questions:** ground truth is computed at evaluation time by an independent SQL query on the same filters. Confirm the "recently = last 6 complete months" convention with Person 2.
- **Policy changed:** 4 of 6 have both values from official text:
  - **EHG for families:** $80,000 → $120,000. The old value is from the MND & HDB 2024 press release in the proposal.
  - **EC income ceiling:** $16,000 → $18,000.
  - **EC minimum occupation period:** 5 → 10 years.
  - **New-flat HDB loan-to-value limit:** 80% → 75%.

  **CHG-05 and CHG-06 still need a source for their old values.** Don't fill these from memory.
- Person 1's 15-question development set isn't in the repo yet. Merge it into `questions.json` with new IDs.

## Run

```powershell
.\.venv\Scripts\python.exe evaluation\build_eval_set.py
.\.venv\Scripts\python.exe evaluation\run_eval.py                                   # dev: discovery + BM25 baseline
.\.venv\Scripts\python.exe evaluation\run_eval.py --retriever mypkg.retrieval:search # your retriever: fn(query, k) -> [chunk_id]
.\.venv\Scripts\python.exe evaluation\run_eval.py --api http://127.0.0.1:8000       # + end-to-end against /chat
```

## First results (dev split, 2026-10-16)

These are baselines, not results to report.

| Metric | Result | Target | Note |
|---|---|---|---|
| Discovery precision / recall | 75% / 100% | ≥ 80% / ≥ 70% | Extras: the Step-Up card for SPR and foreigner profiles (the captured Step-Up page states no citizenship rule, so code cannot exclude it), and PHG for an SC/SC couple (label call) |
| Ask-next accuracy | 50% (2/4) | none set | The engine asks for the field that unblocks the most cards; review whether the labels or the tie-break should change |
| Recall@5, keyword baseline | 38% (6/16) | ≥ 85% | Plain keyword search, no embeddings. MyNiceHome summary chunks outrank HDB pages. Person 2's hybrid retriever should beat it |
| End-to-end on the demo backend | not meaningful | | The backend still runs the fictional demo workflow; rerun when the real stages are connected |

## Not done here

- **LLM-judged metrics** (faithfulness, answer relevance): these need a judge model. `--api` writes `results/*_ragas.jsonl` (question, answer, contexts, ground_truth), ready for Ragas or TruLens once the team picks a judge (e.g. a local Ollama model). Ragas isn't installed to keep dependencies light.
- **Explicit routing:** routing is inferred from the response `trace` until the backend returns its route.
