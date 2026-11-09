# Evaluation results: retrieval, topic cards and end-to-end comparison

Branch `feat/sandra-finals-eval-retrieval` (PR #18, stacked on #16). Written 8 Nov 2026.
All figures are on the **50-question development set** (`dev_set_questions.jsonl`) with the
15 Oct 2026 policy snapshot. No held-out material was opened or used for any of this work;
the held-out run belongs to the frozen system (section 8).

Every rate is given with its count and a 95% Wilson interval. Comparisons between systems
are paired, question by question (exact McNemar test), because with 22 policy questions a
single question moves a rate by 4.5 points.

## 1. Summary

| Area | Before | After | Target |
|---|---|---|---|
| Policy retrieval Hit@5 (22 Qs), strict labels | 81.8% (18/22) | 81.8% (18/22), CI 61.5–92.7% | — |
| Policy retrieval Recall@5, strict | 74.2% | 74.2% | ≥85% |
| Policy retrieval Recall@5, relaxed labels (section 5) | — | 83.3% | ≥85% |
| Discovery card recall, suggested (7 Qs, 15 cards) | 87% (13/15) | 93% (14/15) | ≥70% |
| Discovery card precision, suggested | 46% (13/28) | 54% (14/26) | ≥80% |
| Eval reports keyword-only search as "hybrid" when embeddings fail | possible | fails loudly | — |
| Correct price figures, full system vs no-tools (21 Qs) | 0% (no-tools) | 76.2% (16/21) on main @c36f6b9 (7b); 71.4% on 8 Nov | — |
| Cited answers, full system (42 answerable) | 0% (no-tools) | 69.0% (29/42) on main @c36f6b9; 73.8% on 8 Nov | 0 uncited |
| Safe on should-abstain questions, full system (8 Qs) | 75.0% (8 Nov) | 100% (8/8) on main @c36f6b9 | — |

The retrieval pipeline was already near its ceiling on this set: of the 4 policy misses, 2 are
answer-key problems (section 5), not retrieval problems. Discovery is still the weakest
area: precision is limited mostly by profiles that leave out citizenship or income, so
cards wait for an answer instead of being confirmed or ruled out.

## 2. What changed

| Change | Files | Why |
|---|---|---|
| Baseline runner (`--system full / no-tools / naive-rag / naive-rag-dense`), sends scripted follow-up turns | `evaluation/run_baselines.py`, `baselines.py` | Proposal 4.1 baselines; the old eval only sent the first turn, so PRC-07 and DSC-04 were never answered as written |
| Retrieval report: Hit@5, Recall@5, Recall@20, MRR@20, per slice, with miss types | `evaluation/retrieval_report.py`, `metrics.py` | The old "recall@5" was really Hit@5 |
| Everyday-word synonyms for keyword search (mum → parent, condo → private property, race → ethnic quota) | `components/policy_retrieval.py` | Vocabulary mismatch found in the miss diagnosis |
| Strict mode: eval tools refuse keyword-only fallback | `policy_retrieval.py`, eval tools | Review finding on #18: a failed embedding call silently turned "hybrid" into keyword-only |
| Cards: `amount_fields` split from `required_fields` | `topic_cards.py`, `build_cards.py`, cards | Flat type only sets the grant amount but was hiding cards |
| Cards: Singles Grant trigger includes SC + non-resident spouse | `build_cards.py` | The card could never match a case the snapshot allows (CHUNK_SINGLES_05) |
| Cards: `exclude_if` (owning private property), `priority`, `group` | `topic_cards.py`, `build_cards.py`, `validate.py` | Rules as code, each cited to a chunk |
| Error bars and paired comparison | `evaluation/stats.py`, `compare.py` | Small-sample honesty |
| Relaxed scoring with a written rule | `accepted_evidence.json`, `metrics.py` | Two answer keys were too narrow (section 5) |

Tests: 522 passed, 0 failed (after merging main, which includes Nisha's SYN-08 fix; section 9). New test files: `test_topic_cards_amount_fields.py`, `test_topic_cards_rules.py`,
`test_eval_stats.py`, `test_eval_relaxed_evidence.py`, plus two strict-mode tests in
`test_snapshot_retriever.py`. `scripts/scraping/validate.py`: all checks pass.

## 3. Retrieval results (dev, Hit@5)

| Retriever | All (29) | Policy (22) | Discovery (7) |
|---|---|---|---|
| Keyword (BM25) | 48.3% (14/29), CI 31.4–65.6% | 59.1% (13/22), CI 38.7–76.7% | 14.3% (1/7) |
| Keyword + synonyms | 51.7% (15/29), CI 34.4–68.6% | 63.6% (14/22), CI 43.0–80.3% | 14.3% (1/7) |
| Dense (EmbeddingGemma) | 62.1% (18/29), CI 44.0–77.3% | 72.7% (16/22), CI 51.8–86.8% | 28.6% (2/7) |
| **Hybrid (app)** | **69.0% (20/29), CI 50.8–82.7%** | **81.8% (18/22), CI 61.5–92.7%** | 28.6% (2/7) |
| Hybrid, relaxed labels | 75.9% (22/29), CI 57.9–87.8% | 90.9% (20/22), CI 72.2–97.5% | 28.6% (2/7) |

Hybrid, strict: Recall@5 61.5% all / 74.2% policy; Recall@20 73.6% / 90.2%; MRR@20 0.543 / 0.661.
No gold chunk is missing from the index.

**Paired, policy questions, vs keyword-only:** hybrid wins 6 questions and loses 1
(p = 0.125); dense wins 5, loses 2 (p = 0.45); synonyms win 1, lose 0 (p = 1). Hybrid vs
dense: wins 2, loses 0 (p = 0.5). The direction is consistent, but **no single step is
statistically significant on 22 questions**. Say this on the slide rather than "+23 points".

Synonyms moved keyword search (Hit@5 59.1% → 63.6% policy; POL-04's gold chunk from rank 25
to 2) but did not change any hybrid result. The embedding prefixes recommended by Google
(`task: search result | query:` and `title: … | text:`) were already in place
(`policy_index.py`), so that item needed no work.

## 4. Why the remaining policy questions miss

| Question | Miss | Cause |
|---|---|---|
| POL-02 (single, turning 35) | gold at rank 16 | Answer key: rank 1 (HDB's CHUNK_SINGLES_05) states the same age rule (section 5) |
| POL-04 ("block is full for Chinese buyers") | gold not in top 20 | Answer key: rank 1 (CHUNK_EIP_02) states the same EIP limit (section 5) |
| MIX-04 | rank 7 | Ranking: EHG amount tables outrank the gold passage |
| MIX-08 ("mum") | rank 10 | Vocabulary; a related PHG chunk is in the top 5 |
| DSC-01, -02, -03, -04, -06 | not in top 20 | Discovery questions describe a situation, not a policy; their evidence comes from cards, not search (section 6) |

None of the misses is caused by table rows being split, so table-row chunks were not built,
and ranking misses do not dominate, so fusion weights were not re-tuned (that would overfit
22 questions).

## 5. Answer-key audit (strict vs relaxed)

POL-02 and POL-04 were flagged because the top-ranked chunk already answers the question.
**The labels were not edited.** Instead `data/evaluation-data/development/accepted_evidence.json`
lists accepted alternatives under a written rule:

> An evidence item also counts as found when a retrieved current tier-1 HDB/CPF chunk states
> the same fact. Each alternative is listed with its own verbatim quote and the reason; the
> original labels are unchanged and strict scores are always reported alongside. Alternatives
> are added only after reading the chunk, never because it ranked well, and the file is fixed
> before any held-out run.

| Question | Gold quote | Accepted alternative |
|---|---|---|
| POL-02 | "Be at least 35 years old" (third-party guide) | "First-timer applicants aged 35 and above who are buying a resale flat" (HDB) |
| POL-04 | "…your household is within the EIP quota for the block and neighbourhood" | "…the number of households of your ethnic group remains within the block and neighbourhood limits" |

An alternative whose quote is not in a current chunk raises an error, and the retrieval
report always prints strict and relaxed side by side.

## 6. Discovery (topic cards)

**Why only 1 of 15 expected cards was shown:** not a crash or field-name bug. A card is
shown only when every `required_field` is known, and `required_fields` mixed eligibility
inputs with amount-only inputs. The dev discovery profiles also deliberately leave out
citizenship, first-timer status or income, so most cards wait on the follow-up question.

What changed, each backed by a snapshot chunk:

- **`amount_fields`.** Flat type only sets the CPF Housing Grant amount (CHUNK_GRANTS_20,
  CHUNK_SINGLES_01); living *with* vs *near* parents only sets the PHG amount
  (CHUNK_GRANTS_14). Missing amount fields no longer hide a card; they are reported in
  `MatchResult.amount_missing`, and personal answers still ask for them.
- **Singles Grant for SC + non-resident spouse** (aged 21+, CHUNK_SINGLES_05); fiancé couples excluded.
- **`exclude_if`: owning private property** rules out EHG, Family, Singles and Step-Up
  grants ("Must not have disposed of any private residential property in the last 30
  months", CHUNK_EHG_36 / FAMILY_08 / SINGLES_06 / STEPUP_07). The PHG pages state no such
  condition for the buyer, so the PHG is kept. The reason and chunk ID appear in
  `MatchResult.ruled_out`. Until the profile has the field, it is read from the user's own
  words: present ownership only ("we have a condo"); "we sold our condo" (the 30-month
  rule depends on the date), "my parents' condo", "we live in a condo" and executive condos
  leave it unknown.
- **`priority` / `group`:** matched cards come out as Family/Singles Grant → EHG →
  PHG/Step-Up → eligibility → loans → buying steps.
- **Income rule (read-only from Tasha's ceilings):** a card is ruled out only above the
  highest ceiling any variant states plus a 5% margin. Example: the EHG (Families) ceiling is
  $9,000, so a card is ruled out only above $9,450. The margin exists because HDB assesses
  a 12-month average; a figure just above the ceiling should lead to the HFE letter, not
  hide the grant.

| Discovery (7 Qs, 15 expected cards) | Before | After 3B | After 3C |
|---|---|---|---|
| Recall (suggested = shown + waiting on a detail) | 87% (13/15) | 93% (14/15) | 93% (14/15) |
| Precision (suggested) | 46% (13/28) | 47% (14/30) | 54% (14/26) |
| Shown now (all details known) | 1/15 | 2/15 | 2/15 |
| ask-next matches the label | 60% (3/5) | 60% | 60% |

With 7 questions these are illustrations, not significant differences. Remaining extras
are mostly cards still waiting on citizenship (non-citizen and EIP cards when citizenship
is unknown); DSC-04 still misses `CARD_HFE_LETTER`, which is selected by topic, not by
profile.

**Rule tests** (`test_topic_cards_rules.py`) check properties over every combination of
citizenship × household × first-timer × ownership × income ($0–$30,000 in $500 steps):
raising income never adds an income-capped card; income never changes the PHG outcome;
owning private property removes exactly the four grants; matched cards are in priority
order; a card stays at the ceiling and is ruled out only beyond the margin.

## 7. End-to-end comparison (dev, 50 questions)

Same 50 questions, profiles and scripted follow-up turns for every system; qwen2.5:3b on a
laptop CPU, temperature 0. Each metric is a success rate over a population fixed by the labels,
so every system is scored on the same questions (a run error counts as a failure). Full table:
`data/evaluation-data/results/comparison_dev.md`.

| Metric (population) | **Full system** | No-tools | Naive RAG (dense) | Full vs no-tools (paired p) |
|---|---|---|---|---|
| Correct route (50) | **90.0% (45/50)**, CI 78.6–95.7% | 0% (no router) | 0% (no router) | 5.7×10⁻¹⁴ |
| Correct price figures (21) | **71.4% (15/21)**, CI 50.0–86.2% | 0% (0/21), CI 0–15.5% | 0% (0/21), CI 0–15.5% | 6.1×10⁻⁵ |
| Answer with a citation (42 answerable) | **73.8% (31/42)**, CI 58.9–84.7% | 0% (0/42) | 61.9% (26/42) | 9.3×10⁻¹⁰ (vs naive RAG: p = 0.42) |
| Answers answerable questions (42) | 76.2% (32/42), CI 61.5–86.5% | 64.3% (27/42) | 64.3% (27/42) | 0.41 |
| Not stale on changed policies (7) | 71.4% (5/7) | 71.4% (5/7) | 85.7% (6/7) | 1 |
| Safe on should-abstain questions (8) | 75.0% (6/8), CI 40.9–92.9% | 100% (8/8) | 75.0% (6/8)* | 0.5 |
| Mean latency per question | 85.7 s | 10.0 s | 113.6 s | |

\* One naive-RAG "unsafe" case is an Ollama timeout (OOS-03), scored as a failure.

**What it shows.** The tools make the difference where the bare model cannot work at all:
prices (0/21 → 15/21) and routing are large, significant gains, and every full-system answer
that is given is cited (0 uncited). Retrieval alone (naive RAG) already brings citations, so
the full system's citation gain over naive RAG is not significant. Answering, staleness and
safety are not significantly different on these small populations.

**Manual check of the flagged answers** (the automatic checks are string matches):

| Question | Flag | What happened | Owner / status |
|---|---|---|---|
| OOS-06 (price "next year") | unsafe | Gave past prices instead of declining a forecast (it did say "past sales only") | Fixed by Breann's router (#20): declined in the 9 Nov re-run (section 7a) |
| OOS-07 ("guarantee my Family Grant") | unsafe | Quoted an unrelated Step-Up Grant sentence | Fixed by the same router change: declined in the 9 Nov re-run |
| CHG-05 (loan-to-value limit now) | stale | Quoted the old 80% rule, correctly dated "before 20 August 2024", without the current 75% | Quote selection; see limitation L1 in section 8 |
| CHG-07 (singles and Standard/Plus/Prime) | stale | Quoted "Previously, singles were limited to…" without the current rule | Quote selection; see L1 |

Retrieval found the right passage in both cases (rank 5 and rank 1); the old and current rule
sit in the same passage. Neither stale case presents an old figure as current, but neither
answers the question. Breann's router branch has since been merged; the re-run is in 7a.

### 7a. Re-run on main after the router change (9 Nov)

The 8 Nov run predates Breann's router (#20, rules plus an LLM fallback that declines
forecasts and guarantees). The full system was re-run on main at `19eeaec` (after #20–#26),
same 50 questions, same index, database and model. No run errors. Files:
`20261109T112136Z_full_dev*.json(l)` and `comparison_dev_20261109.md`.

| Metric (population) | Full, 8 Nov (before #20) | **Full, 9 Nov (main @19eeaec)** | Paired p (9 vs 8 Nov) |
|---|---|---|---|
| Correct route (50) | 90.0% (45/50) | **94.0% (47/50)**, CI 83.8–97.9% | 0.5 |
| Safe on should-abstain questions (8) | 75.0% (6/8) | **100% (8/8)**, CI 67.6–100% | 0.5 |
| Answers answerable questions (42) | 76.2% (32/42) | 71.4% (30/42), CI 56.4–82.8% | 0.73 |
| Answer with a citation (42) | 73.8% (31/42) | 69.0% (29/42), CI 54.0–80.9% | 0.73 |
| Not stale on changed policies (7) | 71.4% (5/7) | 57.1% (4/7) | 1 |
| Correct price figures (21) | 71.4% (15/21) | 61.9% (13/21), CI 40.9–79.2% | 0.5 |
| Mean latency per question | 85.7 s | 100.1 s | |

Against the baselines the conclusion is unchanged: prices 13/21 vs 0/21 for both baselines
(p = 2.4×10⁻⁴), routing 47/50 vs 0/50, cited answers 29/42 vs 0/42 without tools (p = 3.7×10⁻⁹).

**What changed and why.**

- *Safety (real change).* OOS-06 (forecast) and OOS-07 (guarantee) are now declined by the
  router's rules, every time, so this is a fix, not run-to-run noise.
- *Answering and citations (noise).* Questions moved both ways: POL-07, DSC-03 and DSC-05
  went from answered to declined, while DSC-04, DSC-07 and CHG-03 went from declined to
  answered. Nearly all the declines are the verifier rejecting a draft ("I could not verify
  the drafted answer…"), so the drafts differ between runs even at temperature 0. No
  difference is significant (all paired p ≥ 0.5).
- *Prices.*
  - MIX-01 failed because the local model did not respond ("language model engine was
    unavailable"). That is infrastructure, but it is still counted as a failure.
  - MIX-08 was declined by the verifier.
  - PRC-10 failed on the evaluation's clock, not the app (see the note below).
  - PRC-11 and PRC-12 are real misses: "newer" and "high floor" were not applied as filters.
  - MIX-07 gave no price.
- *Routing.* PRC-07 ("a flat in Toa Payoh") and DSC-04 should have asked a follow-up
  question but answered directly; MIX-06 asked for profile details when it should have
  answered.
- *Staleness.* CHG-05 and CHG-07 are still limitation L1. CHG-03 is new: asked about EC
  income ceilings, it quoted the resale-flat ceilings.

**Evaluation clock (PRC-10).** The dev labels resolve "past 6 months" as of `AS_OF`
(Oct 2026), but `run_baselines --system full` used the real date: PRC-10 was answered for
Jun–Nov (147 sales) against a label for May–Oct (188 sales). This affects both full runs.
#27 (Nisha) now pins the router's date to `AS_OF` in `run_baselines`, as `run_eval` already
did, so later runs score PRC-10 on the labels' own timeline. That fixes the score, not
the app; what it meant for the app is L2 in section 8 (now fixed by #29). The run on
main @c36f6b9 (7b) is the first with the pinned clock.

### 7b. Main @c36f6b9 (9 Nov, after #27 and #28)

A second full run on main at `c36f6b9` (after Nisha's #27 and #28: router follow-ups,
floor and lease filters, synthesis and verifier fixes, and the pinned evaluation clock).
Same questions, index, database and model; no run errors. **These are the latest measured
full-system figures.** Merged afterwards and not re-measured:

- #29 (Tasha, missing months) does not change dev scores: with the clock pinned to Oct 2026,
  no dev period runs past the data;
- #30 (policy answer coverage) and #31 (verifier relevance) change how policy answers are
  drafted and checked, and may raise the answering and citation rates.

A final run is planned on the frozen commit, the same one the held-out run uses. Files:
`20261109T142139Z_full_dev*.json(l)` and `comparison_dev_20261109_main.md` (all five runs).

| Metric (population) | Full, 8 Nov | Full @19eeaec | **Full @c36f6b9** | No-tools | Naive RAG |
|---|---|---|---|---|---|
| Correct route (50) | 90.0% (45/50) | 94.0% (47/50) | **94.0% (47/50)**, CI 83.8–97.9% | 0% | 0% |
| Safe on should-abstain questions (8) | 75.0% (6/8) | 100% (8/8) | **100% (8/8)**, CI 67.6–100% | 100% | 75.0% |
| Correct price figures (21) | 71.4% (15/21) | 61.9% (13/21) | **76.2% (16/21)**, CI 54.9–89.4% | 0% | 0% |
| Answers answerable questions (42) | 76.2% (32/42) | 71.4% (30/42) | **71.4% (30/42)**, CI 56.4–82.8% | 64.3% | 64.3% |
| Answer with a citation (42) | 73.8% (31/42) | 69.0% (29/42) | **69.0% (29/42)**, CI 54.0–80.9% | 0% | 61.9% |
| Not stale on changed policies (7) | 71.4% (5/7) | 57.1% (4/7) | **42.9% (3/7)**, CI 15.8–75.0% | 71.4% | 85.7% |
| Mean latency per question | 85.7 s | 100.1 s | **87.3 s** | 10.0 s | 113.6 s |

**@c36f6b9 vs the baselines (paired):** prices 16/21 vs 0/21 for both (p = 3.1×10⁻⁵),
routing 47/50 vs 0/50 (p = 1.4×10⁻¹⁴), cited answers 29/42 vs 0/42 without tools
(p = 3.7×10⁻⁹). Against naive RAG, citations (p = 0.69) and answering (p = 0.68) are not
significantly different.

**@c36f6b9 vs @19eeaec.**

- *Prices: 4 fixed, 1 lost (p = 0.375).*
  - Fixed: PRC-10 (the clock is now pinned, so the label's May–Oct is queried); PRC-11
    ("newer") and PRC-12 ("high floor"), whose filters are now applied; MIX-07 now gives
    the price.
  - Lost: MIX-04, because the local model did not respond.
  - The 5 remaining price failures are all mixed questions: MIX-01 and MIX-04 (model did
    not respond), MIX-02 and MIX-08 (verifier rejected the draft), and MIX-06 (asked for
    profile details instead of answering; also a routing miss).
- *Answering and citations.* Exactly 3 questions flipped each way (p = 1): run-to-run
  variation, as between the earlier runs.
- *Routing.* The same three misses as before: PRC-07 and DSC-04 should have asked a
  follow-up question but answered; MIX-06 asked for profile details when it should have
  answered.
- *Staleness (4 flagged), checked by hand.*
  - CHG-05, CHG-06 and CHG-07 are limitation L1. CHG-06 (upfront payment with an HDB loan)
    was declined in the earlier run; this time it was answered with the pre-August-2024
    footnote from CHUNK_RESALE_187 (20% initial payment).
  - CHG-03 (EC income ceiling) is a different failure. The answer quotes the resale flat
    ceilings (Plus flat: $16,000) instead of the EC ceiling. The automatic screen flags it
    because $16,000 is also the old EC figure; in substance it answers for the wrong
    scheme.
  - 43% vs 57% on 7 questions is not significant (p = 1), but L1 is now the clearest
    remaining weakness.

## 8. Limits and threats to validity

**L1. Old and current rules in the same passage: the answer can quote only the old one.**

- *What happens.* Some HDB pages state the current rule in a table and the previous rule in
  plain text in the same passage. Two dev examples:
  - CHUNK_RESALE_187: the current HDB loan-to-value limit of **75%** is a table cell; the old
    80% is a footnote ("For complete resale applications received before 20 August 2024, the
    LTV limit … is at 80%").
  - CHUNK_BTO_36: opens with "**Previously**, singles were limited to…", and the current
    Standard/Plus/Prime options follow in a table.

  Asked what applies *now* (CHG-05, CHG-07, and in the @c36f6b9 run also CHG-06), the
  model quoted the plain-text historical sentence instead of the table row, so the answer is
  true and correctly dated but does not give the current rule.
- *What is not wrong.* Retrieval found the right passage (rank 5 and rank 1). Neither passage
  is superseded, and the verifier correctly accepted the quotes because they are verbatim and
  not presented as current. No old figure was shown as the current one.
- *How often.* 2 of the 7 changed-policy dev questions on 8 Nov, and 3 of 7 on main @c36f6b9
  (CHG-05, -06, -07; section 7b). CHG-06 was declined in the other runs, so whether it
  shows up depends on the run. It can happen on any page that keeps a dated footnote or a
  "Previously…" sentence next to the current table, and is most likely exactly where policy
  has recently changed.
- *Why it was not fixed now.* The cause sits between chunking (Sandra) and quote selection
  (Nisha), and any fix needs the full dev evaluation re-run (about 70 minutes) a day before
  submission. It is documented instead of patched.
- *Possible fixes (future work).*
  1. Chunking: split dated footnotes and "Previously…" sentences into their own chunks,
     tagged as historical with their date, so they rank below the current rule.
  2. Synthesis: when a passage holds both, prefer the sentence or table row without a past
     date, and state the effective date.
  3. Verifier: for questions with "now / currently / still", flag an answer whose only quote
     carries a past date ("before 20 August 2024", "Previously") and repair it once.
- *For users today.* Answers show the snapshot date and source link, and the passage itself
  (with the current table) is one click away under Sources.

**L2 (fixed on main by #29). Relative periods could run past the newest price data.**

- *What happened.* The price data ends at the newest month in the import (Oct 2026; 0 sales
  for Nov). On 8–9 Nov, "past 6 months" was resolved as Jun–Nov 2026 and the answer was
  labelled "Jun 2026 to Nov 2026", although only five of those months have sales. The same
  applied to "past 3 months", "this year" and "in 2026". Questions with no period were not
  affected: the default window already ends at the newest data month.
- *Why the dev evaluation could not see it.* It pins its clock to `AS_OF` (Oct 2026), where
  the data and the calendar agree.
- *Fix (Tasha, #29, merged 9 Nov).* The period is queried up to the newest data month and
  the answer starts with "We don't have sales data for Nov 2026 yet: our records go up to
  Oct 2026, so these figures cover Jun 2026 to Oct 2026." The full dev runs in section 7a
  are unaffected: with the clock pinned to Oct 2026 no dev period runs past the data.
- *Confirmed by the live freshness check below:* on 9 Nov, 4 of 6 probes are cut to Oct
  with that sentence, and all 6 pass.

**Live freshness check.** `python -m kopi_keys.evaluation.freshness [--today YYYY-MM-DD]`
runs without a language model, in under a minute on an idle laptop. For six price
questions phrased with relative periods, generated from the date (not taken from the dev
labels), it checks:

- the period the app asks for matches the phrase on that day (worked out independently of
  the router);
- the period it queries does not run past the newest data month, and if the asked-for
  period does, the answer says which months are missing;
- the figures equal plain SQL over the queried period.

It also fails if the price data is more than 2 months behind, or the active policy snapshot
is more than 45 days old. On 9 Nov (main with #29):

- period, coverage and figures: 6/6;
- price data: newest month Oct 2026, 1 month behind (ok);
- policy snapshot: 15 Oct 2026, 25 days old (ok).

Tests (`test_eval_freshness.py`, 14) include a year boundary, stale data, an old snapshot,
and the behaviour before #29 (period labelled up to November), which the check fails.

The dev scores stay pinned, so they are reproducible; freshness is checked live, so it
moves with the calendar.

- Dev only, and the dev set was used while tuning; dev numbers are optimistic. The held-out
  run must use a frozen tag (`git tag finals-frozen`) and record the model digests and
  sampling settings. Sandra did not open held-out material.
- Small n: 22 policy and 7 discovery questions. Most step-wise differences are not significant.
- Relaxed scoring covers 2 questions, under a rule written before any held-out run.
- `owns_private_property` is a regex until the profile has the field; it is conservative
  (unknown rather than guessed) and covers English phrasings only.
- Card rules encode only conditions found in the snapshot. Rules suggested by third-party
  sites (e.g. EHG depending on Family Grant eligibility, lease to age 95) are not encoded.

## 9. Notes for teammates

- **Nisha:** fixed on main (`b3503af`, merged with #16): SYN-08 in `data/benchmarks/synthesis_cases.json`
  pointed at `CHUNK_LOAN_27/_28`, retired by re-chunking. All three required quotes are in
  `CHUNK_LOAN_49`. Lesson for future work: derive chunk IDs from source + content so re-chunking
  cannot silently break benchmarks.
- **Breann:**
  - Discovery needs `owns_private_property` (ideally also `lives_with_or_near_parents_or_child`)
    in `GraphState`/the sidebar; the adapter's regex is a stop-gap.
  - The matcher now returns why each card was ruled out (`MatchResult.ruled_out`), but the graph
    trace logs only `topic_cards:N matched` (`graph.py:111`). One line could add the reasons.
  - Suggestions now come in priority order (an SC/SC couple sees the Family Grant before EHG),
    and a couple without a flat type now also gets the Family Grant suggestion.
- **Tasha:** `rules/income_ceilings.json` stays the single source of truth; discovery reads it
  and never copies values. A `source_chunk_id` and `effective_date` per ceiling would let the
  card build check them the same way it checks exclusion quotes.

## Reproduce

From `backend/` with the project venv (Ollama with the policy index for dense/hybrid):

```
python -m kopi_keys.evaluation.retrieval_report --mode hybrid      # strict + relaxed
python -m kopi_keys.evaluation.run_baselines --system no-tools     # or naive-rag-dense / full
python -m kopi_keys.evaluation.compare <results files>             # CIs + paired McNemar
python -m pytest ../tests -q
```
