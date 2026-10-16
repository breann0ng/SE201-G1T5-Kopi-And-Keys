# Evaluation (proposal section 4, Appendix E)

Scores the advisor against labelled questions. Owner: Person 4 (Sandra).

| File | What it does |
|---|---|
| `dataset.py` | Loads and validates the question sets, resolves every evidence quote **word for word** to chunk IDs in the ACTIVE snapshot (fails otherwise), and regenerates `stage1_gateway_labels.jsonl` |
| `metrics.py` | Router accuracy, discovery precision/recall and ask-next, Recall@5, and end-to-end checks (routing, unsafe answering, over-abstention, uncited answers, staleness) |
| `baselines.py` | Retrievers to score (`bm25`, `hybrid`, or `module:function`). The answer-level baselines (same LLM without tools, naive single-call RAG) are still TODO |
| `run_eval.py` | The command below; reports go to `.local/reports/` (gitignored) |

## Question sets

- **Development (committed):** `data/evaluation/development/dev_set_questions.jsonl`, 30 questions
  combined from Breann's and Sandra's earlier sets on 2026-10-17 (20 and 10; each records its
  `origin`). Stratified as the proposal says: policy 7, price 6, mixed 5, discovery 4,
  policy-changed 4, unanswerable 4. Each question carries the router labels (intent, route,
  status, extracted fields, missing fields, turns) and answer labels (verbatim evidence, price
  filters, expected cards, current vs superseded values). The previous sets are kept in
  `archive/`.
- **Held-out (never committed):** 20 fresh questions, written outside the repo by someone who
  hasn't tuned the system, with the same schema. Run once, for the final reported numbers:
  set `KOPI_HELDOUT_DIR` to the folder holding `heldout_questions.jsonl`, then add
  `--split heldout --final`.

After editing the dev set, regenerate the router labels:

```powershell
.\.venv\Scripts\python.exe -m kopi_keys.evaluation.dataset
```

## Run

```powershell
.\.venv\Scripts\python.exe -m kopi_keys.evaluation.run_eval                     # router, discovery, Recall@5 (keyword)
.\.venv\Scripts\python.exe -m kopi_keys.evaluation.run_eval --retriever hybrid  # Recall@5 with the app's retriever
.\.venv\Scripts\python.exe -m kopi_keys.evaluation.run_eval --retriever hybrid --local   # + end to end, in-process
.\.venv\Scripts\python.exe -m kopi_keys.evaluation.run_eval --api http://127.0.0.1:8000  # + end to end over HTTP
```

End-to-end runs call Ollama for every question and take a long time on CPU.

## Development results (2026-10-17, dev set; not results to report)

| Metric | Result | Target |
|---|---|---|
| Router (Stage 1 labels) | 100% (30/30) | ≥ 90% routing |
| Discovery precision / recall | 38% / 89% | ≥ 80% / ≥ 70% |
| Ask-next accuracy | 67% (2/3) | none set |
| Recall@5, hybrid retriever | 60% (12/20) | ≥ 85% |

Recall@5 on the same 20 questions: keyword ranker alone 45%, dense vectors alone 55%,
PR #5's keyword ranker 35%. The hybrid result was the same (60%) for dense weights 1 to 6,
so `DENSE_WEIGHT = 3` is not finely tuned. Several remaining misses retrieve a different
chunk stating the same fact, so evidence labels may still be too narrow; check before
changing the ranker.

Discovery precision is low because the matcher suggests every card a profile *could*
match (blocked cards included) and cards can't yet rule out by income.
