# Testing Sandra's modules: mutation score

Owner: Sandra. Scope: retrieval, topic cards, chunking and the evaluation scripts Sandra wrote
(the eight modules in the first table). Same method as Tasha's price-tool work: see
[testing-price-tool.md](testing-price-tool.md) for what mutation testing is.

In short, a **mutant** is a small change to the code (`<` becomes `<=`, `0` becomes `1`, `and`
becomes `or`, a string gets `XX` added). The tests run once per mutant. A mutant is **killed** if a
test fails and **survives** if every test still passes. A survivor is either **equivalent** (no
input can produce a different result, so ignore it) or a **missing test**. A low score means the
tests are weak, not that the code is wrong.

## Result

Baseline: main at `d9a1b88`, 2026-11-09. "After" means after the four new and edited test
files listed below. The four modules on the left of the table were the weakest, so those are
the ones improved first.

| Module | Mutants | Before | After |
|---|---|---|---|
| `evaluation/stats.py` | 81 | 52 (64.2%) | **79 (97.5%)** |
| `evaluation/compare.py` | 170 | 35 (20.6%) | **159 (93.5%)** |
| `evaluation/retrieval_report.py` | 11 | 0 (0%) | **9 (81.8%)** |
| `components/topic_cards.py` | 157 | 31 (19.7%) | **144 (91.7%)** |
| *these four* | *419* | *118 (28.2%)* | ***391 (93.3%)*** |
| `topic_cards.py` | 167 | 121 (72.5%) | not re-run |
| `components/policy_retrieval.py` | 275 | 98 (35.6%) | not re-run |
| `components/policy_index.py` | 187 | 54 (28.9%) | not re-run |
| `scripts/scraping/chunk.py` | 418 | 132 (31.6%) | not re-run |
| **all eight** | **1466** | **523 (35.7%)** | **796 (54.3%)** |

The full test suite still passes after the change, including after updating the branch to
main at `c95b2c4` (967 passed, with the property and convention tests below). The mutation scores above were measured
on `d9a1b88`; none of the eight modules changed between the two commits.

Not measured because they have no tests yet: `evaluation/baselines.py`,
`evaluation/run_baselines.py` and `evaluation/retrieval_sweep.py`. `evaluation/metrics.py` is
shared with Tasha's price scoring, so it was left out.

## How to rerun

```bash
python scripts/mutation_test_sandra.py                        # all eight modules (~45 min)
python scripts/mutation_test_sandra.py --only stats compare   # targets whose path contains these
python scripts/mutation_test_sandra.py --list                 # count mutants only
python scripts/mutation_test_sandra.py --json out.json        # every mutant and its result
```

Run it from the repo root with the project venv. It uses only the standard library, so there is
no new dependency.

### How the runner works

`scripts/mutation_test_sandra.py` reuses Tasha's mutant generator from `scripts/mutation_test.py`
unchanged, with the same operators and the same skipped code: docstrings, annotations,
`main()`/`__main__` blocks and exception classes. It differs from Tasha's runner in four ways:

1. **Per-module tests.** Each module runs only the tests that exercise it (the `TARGETS` map at
   the top of the script). This keeps a full run under an hour. If you add a test file for one
   of these modules, add it to `TARGETS` too.
2. **Works on Windows.** Each worker gets its own copy of `backend/`, `scripts/` and `tests/`,
   so mutants of `scripts/scraping/chunk.py` are tested as well. `data/` and `frontend/` are
   shared through a directory junction (a symlink on macOS/Linux). The junction itself is
   removed before the copy is deleted, so the real folders are never touched.
3. **Cleans up after string mutants.** A string mutant can turn the path `"chroma"` into
   `"XXchromaXX"`, which creates `data/XXchromaXX/` in the shared folder. The first run did
   exactly this. The runner now removes any new `data/XX…` entry at the end and warns about any
   other new entry.
4. **Longer timeout.** A run that times out (120 s) counts as killed, as in Tasha's runner. Six
   `chunk.py` mutants did.

## Tests added

| File | What it pins down |
|---|---|
| `tests/test_eval_stats.py` (+2 tests) | `rate()` text, including `"n/a"` for 0 questions. `paired()` keeps the two systems apart and ignores questions both got right. |
| `tests/test_eval_compare.py` (new, 16 tests) | One rule per answer metric: routing, safe when it should abstain, answers answerable, cited, not stale, price correct (only with an expected volume). A run error fails every metric it belongs to. Hit@5 slices. Table rows and paired rows. `--relaxed` and mixed-file refusals. Loading by path or by name. |
| `tests/test_topic_card_component.py` (new, 33 tests) | `required_fields` order. `personal_eligibility_fields` (EHG versus loan wording, follow-ups). `discovery_question_field`: only for discovery, not during a clarification, not once a card matches, never asks twice. Suggestions: order, at most 3, skip what the question asks about, skip cards without an overview. Income-ceiling notes: when shown, which schemes, never unverified ones. `profile_from_state` field by field. Every askable field, in order. Every card keyword, loan wording and grant word, written out by hand so editing a keyword list makes a test fail. |
| `tests/test_retrieval_report.py` (new, 6 tests) | The report file (name, mode, strict and relaxed scores). Each query is searched once. The miss table. The bm25, dense and hybrid search adapters. Refusing keyword-only search for dense/hybrid. The bm25 baseline never builds the hybrid retriever. |

The mutation work changed no production code and found no bug. One small bug was found later
by a property test (next section) and fixed in `stats.py`.

## Survivors in the four improved modules (28)

**Equivalent: ignore (8).**

- `stats.py:43` `n == 0` → `n == 1` / `n == -1`: for 0 or 1 discordant question the p-value is
  1.0 either way.
- `compare.py:77, 88, 96` `[0]` → `[-1]`: every result in one table is the same kind and has
  the same metric names, so the first and last results give the same answer.
- `components/topic_cards.py:41` `stacklevel=2` → 1 or 3: only changes which line the warning
  points at.
- `components/topic_cards.py:193` `or` → `and`: the grant schemes are all different, so
  `scheme in seen` is never true, and a `None` scheme is skipped by the `IncomeRuleError`
  handler anyway.

**Strings (20).** All harmless: `__all__` names, error message text (tests check only part
of each message) and the results folder path (tests point it at a temp folder).

The one real gap the last run showed, `topic == "grants"` (line 182), now has a test
(`test_grants_topic_lists_every_grant_even_when_one_card_matched`). It was added after that
run, so it is not counted in the table.

## Tests that check themselves (tautological tests)

A test whose expected value is computed by the code under test cannot fail when that code
is wrong. Six assertions in the new tests built their expected table cells and p-value by
calling `stats.rate()` and `stats.mcnemar_exact()`. They now use literal values, and those
two functions are pinned separately by literal tests in `tests/test_eval_stats.py`.

## Other checks added: validator, property, convention and regression tests

These follow the SE201 Week 10 list of verification instruments. All run offline in seconds,
so CI's backend job runs them on every PR with no change to `ci.yml`.

| File | Instrument | What it establishes |
|---|---|---|
| `tests/test_scraping_validate.py` | Data validation | `scripts/scraping/validate.py` (10 checks on the ACTIVE snapshot's chunks and cards) passes. Before, nothing ran it automatically. |
| `tests/test_properties.py` | Property tests | Relations that hold for every input in a range, checked exhaustively or with a seeded sample. Hypothesis is not a dependency, so no new package. Wilson: inside [0, 1], contains k/n, symmetric, narrower with more data. McNemar: a probability, symmetric, 1 for an equal split, smaller for a more lopsided split. Keyword search on 200 random queries: unique, current IDs within the limit; deterministic; the top 5 is a prefix of the top 20. |
| `tests/test_retrieval_floor.py` | Regression floor | Keyword (BM25) search on the DEV set keeps strict Hit@5 at 13 or more of 22 policy questions and 14 or more of 29 overall (today 14 and 15, so each floor is one question below). Offline, under a second. Raise the floors when retrieval improves; re-measure if the dev set or snapshot changes. Checked that it fails when the top result is dropped (10/22). |
| `tests/test_conventions.py` | Convention tests | This codebase's rules: `CHUNK_*`/`CARD_*` ID forms and card file names, every chunk from an https `.gov.sg` page with a source tier and the ACTIVE snapshot date, income kept as an exact `Decimal`, months as `YYYY-MM`, held-out questions only through `KOPI_HELDOUT_DIR` and never committed. |

**Finding.** The Wilson property found that `wilson(0, n)` returned a lower bound slightly
above 0 (e.g. `5.6e-17` for n = 3) and `wilson(n, n)` an upper bound slightly below 1, for 29
values of n up to 60. The observed rate then fell outside its own interval. The example tests
had passed only because they used n = 9 and n = 22. Fixed by returning exactly 0 or 1 at those
edges. No reported figure changes, because `rate()` prints one decimal place.

## Weakest spots still open (not yet re-run)

- **`policy_retrieval.py` (35.6%).** The BM25 formula (lines 136–149) and the plural/stemming
  rules (lines 95–98) can change without a test failing. One hand-computed BM25 score on a
  three-chunk corpus would fix most of these, plus a table of word → stem cases.
- **`policy_index.py` (28.9%).** Vector search and ranking (lines 148–177). This needs a tiny
  in-memory index with known vectors.
- **`chunk.py` (31.6%).** Heading and table handling around lines 169, 247–253, 311–316 and
  339–384. Small HTML/PDF snippets with a known expected chunking would cover these.
- **`topic_cards.py` (72.5%).** Mostly fine; the survivors are spread thinly.
