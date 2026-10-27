# Evaluation (proposal section 4, Appendix E)

Scores the advisor against labelled questions. Owner: Sandra.

| File | What it does |
|---|---|
| `dataset.py` | Loads and validates the question sets, resolves every evidence quote **word for word** to chunk IDs in the ACTIVE snapshot (fails otherwise), and regenerates `stage1_gateway_labels.jsonl` |
| `metrics.py` | Router accuracy, discovery precision/recall and ask-next, Recall@5, and end-to-end checks (routing, unsafe answering, over-abstention, uncited answers, staleness) |
| `baselines.py` | Retrievers to score (`bm25`, `hybrid`, or `module:function`). The answer-level baselines (same LLM without tools, naive single-call RAG) are still TODO |
| `run_eval.py` | The command below; reports go to `.local/reports/` (gitignored) |
| `synthesis_benchmark.py` | Nisha's fixed-evidence CPU synthesis comparison; independent of the team dev/held-out splits. See [the finals guide](../../../docs/finals-nisha.md). |

## Question sets

- **Development (committed):** `data/evaluation-data/development/dev_set_questions.jsonl`, 30 questions
  combined from two earlier sets on 2026-10-17 (20 and 10; each records its
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
