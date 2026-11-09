# Evaluation (proposal section 4, Appendix E)

Scores the advisor against labelled questions. Owner: Sandra.

| File | What it does |
|---|---|
| `dataset.py` | Loads and validates the question sets, resolves every evidence quote **word for word** to chunk IDs in the ACTIVE snapshot (fails otherwise), and regenerates `stage1_gateway_labels.jsonl` |
| `metrics.py` | Router accuracy, discovery precision/recall and ask-next, Recall@5, price checks, and end-to-end checks (routing, unsafe answering, over-abstention, uncited answers, staleness, price figures) |

**Price checks** (no model needed): `price_filters` compares the filters the app would query
(router with its date pinned to `dataset.AS_OF`, default window ending at the database's latest
month) with each question's `price_filters`, including `lease_band` / `storey_band`.
`price_figures` runs the price tool on those filters and compares volume and median with
`expected_price`, which is computed separately with plain SQL on `hdb_prices.db`. End to end,
answered price questions are also checked against `expected_price`.
| `baselines.py` | Retrievers to score (`bm25`, `hybrid`, or `module:function`), and the answer-level baselines: the same LLM without tools (`no-tools`) and naive single-call RAG (`naive-rag` hybrid, `naive-rag-dense`). Hybrid scoring refuses the keyword-only fallback, so a failed embedding service can never be reported as hybrid |
| `run_baselines.py` | Runs the full app (in-process) or a baseline on the dev set, sending scripted follow-up turns, and saves answers and `end_to_end` scores to `data/evaluation-data/results/` |
| `retrieval_report.py` | Hit@5, Recall@5, Recall@20 and MRR@20 for `bm25` / `dense` / `hybrid`, in three slices (all, policy, discovery), with a miss type per question. Prints strict and relaxed scores |
| `stats.py`, `compare.py` | 95% Wilson intervals and paired exact McNemar tests; `compare.py` lines up result files question by question on fixed populations (a run error counts as a failure) |
| `run_eval.py` | The command below; reports go to `.local/reports/` (gitignored) |
| `freshness.py` | Live freshness check on the real date (no model calls): relative periods ("past 6 months", "this year") match the phrase and stay within the newest price data, figures equal plain SQL, price data and policy snapshot not too old. Exit 1 on a failure; reports go to `.local/reports/` |
| `synthesis_benchmark.py` | Nisha's fixed-evidence CPU synthesis comparison; independent of the team dev/held-out splits. See [the finals guide](../../../docs/finals-nisha.md). |

## Question sets

- **Development (committed):** `data/evaluation-data/development/dev_set_questions.jsonl`, 50 questions:
  30 combined from two earlier sets on 2026-10-17 (20 and 10), plus 20 added on 2026-10-31
  (each records its `origin`). Stratified: policy 7, price 13, mixed 8, discovery 7,
  policy-changed 7, unanswerable 8. Each question carries the router labels (intent, route,
  status, extracted fields, missing fields, turns) and answer labels (verbatim evidence, price
  filters, expected cards, current vs superseded values). The previous sets are kept in
  `archive/`.
- **Held-out (never committed):** 40 fresh questions, written outside the repo by people who
  haven't tuned the areas they write for, with the same schema (see
  [the held-out guide](../../../docs/heldout-guide.md)). Run once, for the final reported numbers:
  set `KOPI_HELDOUT_DIR` to the folder holding `heldout_questions.jsonl`, then add
  `--split heldout --final`.

**Strict and relaxed retrieval scoring.** `data/evaluation-data/development/accepted_evidence.json`
lists same-fact alternatives for two evidence labels (POL-02, POL-04) under a written rule.
The labels themselves are never edited, and strict scores are always reported beside relaxed ones.

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

Local full-system evaluation now pins the router to `dataset.AS_OF` and follows
scripted clarification turns consistently in both runners. Remote API evaluation
refuses questions whose date interpretation has drifted from the labels: use
`--local` rather than changing the frozen data or labels to fit today's date.
Reports retain the legacy final-route accuracy and separately report
`initial_routing_accuracy`, so answering a clarification is not mistaken for an
incorrect first-turn route. The superseded-value metric remains a literal screen;
qualified earlier-cohort amounts need human review, not automatic deletion.

For a development diagnosis with verifier reasons and a human-review worksheet:

```powershell
.\.venv\Scripts\python.exe -m kopi_keys.evaluation.dev_review --case-ids MIX-01 POL-02
```

Omit `--case-ids` for all 50 **development** questions. There is no held-out option.
The command requires the complete hybrid index, disables tracing, pins dates,
preserves errors/drafts/relevance scores and writes incrementally to ignored
`.local/reports/dev-review.json`. GPU mode verifies actual offload before the run.
Reports record source/evidence/dataset/SQL hashes; keep model settings, model
digest and the final clean Git commit together when freezing. A completed run
does not establish semantic accuracy: the human-review fields remain unfilled.

Finals runs (from `backend/`):

```powershell
..\.venv\Scripts\python.exe -m kopi_keys.evaluation.retrieval_report --mode hybrid      # strict + relaxed
..\.venv\Scripts\python.exe -m kopi_keys.evaluation.run_baselines --system no-tools     # naive-rag-dense, naive-rag, full
..\.venv\Scripts\python.exe -m kopi_keys.evaluation.compare <result files>              # CIs + paired McNemar
..\.venv\Scripts\python.exe -m kopi_keys.evaluation.freshness                         # live, real date
```

## Finals development results (2026-11-08, 50-question dev set)

See [the evaluation results](../../../docs/evaluation-results.md) for the full tables, the
miss diagnosis and limits. Headline figures (95% Wilson intervals):

| Metric | Result |
|---|---|
| Policy Hit@5, hybrid, strict (22 Qs) | 81.8% (18/22), CI 61.5–92.7% |
| Policy Recall@5, hybrid, strict / relaxed | 74.2% / 83.3% (target ≥ 85%) |
| Discovery card recall / precision (7 Qs, 15 cards) | 93% / 54% (target ≥ 70% / ≥ 80%) |
| No-tools baseline: cited answers / price figures | 0% (0/42) / 0% (0/21) |
| Naive RAG (dense): cited answers / price figures | 62% (26/42) / 0% (0/21) |

The tables below are from the earlier 30-question set and are kept for history; they are not
comparable with the 50-question figures.

## Earlier development results (2026-10-17, 30-question set; not results to report)

| Metric | Result | Target |
|---|---|---|
| Router (Stage 1 labels) | 100% (30/30) | ≥ 90% routing |
| Discovery precision / recall | 38% / 89% | ≥ 80% / ≥ 70% |
| Ask-next accuracy | 67% (2/3) | none set |
| Recall@5, hybrid retriever | 60% (12/20) | ≥ 85% |

End to end (`--retriever hybrid --local`, 8 threads, 3 passages / 800 words; ~20 min):

| Metric | Run 1 | Run 2 (after date and hyphen fixes) | Run 3 (after reply and keep-verified fixes) | Target |
|---|---|---|---|---|
| Routing | 100% (30/30) | 100% (30/30) | 100% (30/30) | ≥ 90% |
| Unsafe answering | 25% (1/4) | 0% (0/4) | 0% (0/4) | ≤ 5% |
| Over-abstention | 15% (4/26) | 12% (3/26) | 8% (2/26) | ≤ 10% |
| Uncited answers | 0 | 0 | 0 | 0 |
| Staleness | 0% (0/4) | 0% (0/4) | 0% (0/4) | 0% |

Run 1's unsafe answer (OOS-02) gave recent prices to a question about another year; the
router now reads named periods (`extract_month_range`). One false rejection (MIX-01) came
from a PDF word split after a hyphen; the verifier now joins those (`_comparable`).
Run 3 (2026-10-17) adds the multi-value clarification reply and keeping verified quotes:
over-abstention is within target. Still declined: DSC-02 and CHG-04 (CHG-04's paraphrase is
correctly rejected).
Run 4 (2026-10-17) adds worked-example down-ranking: every figure identical to run 3 (no
regression; no dev question depends on the four example chunks). Its benefit is on eligibility
questions outside the dev set, such as the EHG question with an income.

Recall@5 on the same 20 questions: keyword ranker alone 45%, dense vectors alone 55%,
PR #5's keyword ranker 35%. The hybrid result was the same (60%) for dense weights 1 to 6,
so `DENSE_WEIGHT = 3` is not finely tuned. Several remaining misses retrieve a different
chunk stating the same fact, so evidence labels may still be too narrow; check before
changing the ranker.

Discovery precision is low because the matcher suggests every card a profile *could*
match (blocked cards included) and cards can't yet rule out by income.

## Speed tuning (policy answers, laptop CPU)

Measured on the first 8 dev policy questions (POL-01 to POL-07, CHG-01), Intel i7-1255U
(2 performance + 8 efficiency cores), plugged in, Windows "Best performance" mode, Ollama
qwen2.5:3b, nothing else using Ollama. Medians per answer; one run each, so treat as indicative.

| Setting | Median | Answered + verified | Right source |
|---|---|---|---|
| 4 threads, 3 passages / 1,100 words (old default) | ~103 s | 8/8 | 4/8 |
| 8 threads, 3 / 1,100 | ~67 s | 8/8 | 3/8 |
| 6 threads / 10 threads, 3 / 1,100 | ~75 s / ~60 s | 6/8 / 7/8 | one 28 to 48 min stall each |
| 8 threads, 2 / 800 | ~19 s | 5/8 (3 declined) | 1/8 |
| **8 threads, 3 / 800 (new default)** | **~37 s** | **8/8** | **4/8** |

- Threads: `KOPI_OLLAMA_NUM_THREADS=8` in `.env` (documented in `.env.example`).
- Passage budget: `KOPI_POLICY_MAX_PASSAGES` / `KOPI_POLICY_MAX_WORDS`, defaults 3 / 800.
- Output length was not cut: answers use about 120 to 175 output tokens, far below the 850-token
  cap, so a lower cap would save little and risk truncated (declined) answers.
- On battery or in a power-saving mode the same answers took about twice as long.
