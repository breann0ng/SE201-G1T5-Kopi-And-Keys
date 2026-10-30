# Held-out evaluation set: how to write it

The held-out set gives the final reported numbers (proposal section 4.1). It only
counts if nobody tuned the system on it, so it lives **outside the repository** and is
run **once**, after the code freeze.

## Rules

1. **40 questions**, same schema as the development set
   (`data/evaluation-data/development/dev_set_questions.jsonl`; the schema is the
   `Question` model in `backend/kopi_keys/evaluation/dataset.py`). Start from
   [`data/evaluation-data/question_template.jsonl`](../data/evaluation-data/question_template.jsonl).
2. **Write only for areas you did not tune.** Use the table below, which assigns
   categories by component owner (`docs/architecture.md`). Everyone has seen the dev set,
   so don't copy or paraphrase dev questions. Write fresh wording, towns and periods.
3. **Store it outside the repo**, in the team shared drive folder
   `Kopi & Keys/heldout/`, as `heldout_questions.jsonl`. Never save it inside the
   repository folder, never paste it into an issue, PR, chat with a coding assistant,
   or commit message, and never commit it. `.gitignore` ignores `*heldout*` as a safety net.
4. **Don't run the system on your questions while writing them.** Write the labels
   from the official sources and the data, not from what the app answers.
5. **Run once, for the final report**, after the code freeze. Record the commit hash.
   No fixes based on held-out results go into the reported numbers.

## Who writes what (proposed; agree as a team)

| Writer | Categories (count) | Why this split |
|---|---|---|
| Tasha | policy (8) | Tuned the price tool, price routing rules, price wording and income rules, not policy retrieval or synthesis |
| Sandra | price (8) | Tuned evaluation, topic cards, retrieval and later synthesis/verifier fixes, not the price tool |
| Breann | mixed (6), policy_changed (6) | Tuned the router and output/abstention, not retrieval, verifier staleness checks or price figures |
| Nisha | discovery (6), unanswerable (6) | Tuned synthesis/verifier and policy guardrails, not topic-card matching or the router's abstain patterns |

Nobody is fully independent: the router touches every category. Note any overlap in
the question's `notes`.

## Labelling

Use the same rules as the dev set (see `data/evaluation-data/development/README.md`):

- **IDs:** `POL-01` … `PRC-01` … `MIX-`, `DSC-`, `CHG-`, `OOS-`, numbered from 01
  within the held-out file. Set `origin` to `heldout:<your name>`.
- **Evidence quotes:** copy word for word from a non-superseded chunk in the ACTIVE
  snapshot (`data/policy_chunks/<ACTIVE>/chunks.jsonl`). The loader fails if a quote
  is not found.
- **Price questions:** set `price_filters` (town and flat type as stored in the database,
  e.g. `TOA PAYOH`, `4 ROOM`; add `lease_band` / `storey_band` if the question asks for
  one). Compute `expected_price` (`volume`, `median`) **with SQL directly on
  `data/processed/hdb_prices.db`**, not through the app. The median is the mean of the
  middle row(s) of the sorted prices. Prefer named periods ("in 2024", "March to
  August 2025"). If you use a relative one ("past 6 months", "these days"), resolve it as of
  `AS_OF` in `dataset.py` and say so in `notes`. The default window ends at the latest
  month in the database.
- **Unanswerable:** `should_abstain: true`. A price question outside the data
  (before January 2017 or in the future) keeps its price route and filters but must abstain.

## Validate (format only, no scoring)

This checks the schema, vocab values and that every quote resolves. It does not run the
router or score anything. Run it on your own questions only:

```powershell
$env:KOPI_HELDOUT_DIR = "G:\Shared drives\Kopi & Keys\heldout"
.\.venv\Scripts\python.exe -c "from kopi_keys.evaluation.dataset import load_questions; print(len(load_questions('heldout')), 'valid')"
Remove-Item Env:KOPI_HELDOUT_DIR
```

## Final run (once)

```powershell
$env:KOPI_HELDOUT_DIR = "G:\Shared drives\Kopi & Keys\heldout"
.\.venv\Scripts\python.exe -m kopi_keys.evaluation.run_eval --split heldout --final --retriever hybrid --local
```

Reports go to `.local/reports/` (gitignored). Copy the summary figures into the report;
do not commit the per-question report, because it contains the questions.
