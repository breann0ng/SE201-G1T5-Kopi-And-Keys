# Testing the price tool: mutation score

Owner: Tasha. Scope: `backend/kopi_keys/components/price_query.py` and `price_display.py`,
tested by `tests/test_price_*.py` and `tests/test_resale_db.py`.

Mutation testing makes many small changes to the code, one at a time ("mutants": `<` becomes
`<=`, `60` becomes `59`, `min` becomes `max`, a string gets `XX` added), and runs the tests once
for each. A mutant is **killed** if a test fails and **survives** if every test still passes. A
survivor is either **equivalent** (no input the program can receive gives a different output)
or a **missing test**.

## Result

| | Mutants | Killed | Score |
|---|---|---|---|
| Before (main at `7a73847`) | 390 | 259 | **66.4%** |
| After (two new test files) | 390 | 374 | **95.9%** |
| After, excluding the 16 equivalent mutants | 374 | 374 | 100% |

By module after: `price_query.py` 239/247, `price_display.py` 135/143.

## How to rerun

```bash
python scripts/mutation_test.py          # prints the score and each survivor
python scripts/mutation_test.py --list   # just list the mutants
```

The script uses only the standard library (no new dependency). It copies `backend/` to a temp
folder per worker, writes one mutant into the copy, and runs a fresh `pytest -x` on the test
files above with that copy first on `PYTHONPATH`. The working tree is never modified.
mutmut was not used. mutmut 3 derives module names by stripping a `src/` prefix (we use `backend/`)
and only mutates code inside functions, so it would skip the band constants.

**What gets mutated:** comparisons (`<`/`<=`, `>`/`>=`, `==`/`!=`, `in`/`not in`, `is`/`is not`),
arithmetic (`+`/`-`, `*`/`/`, `//`→`/`, `%`→`*`), `and`/`or`, dropping `not`, integers ±1,
`True`/`False`, `min`/`max`, and non-empty strings. **Not mutated:** docstrings, type annotations,
the `main()` CLI, exception classes, the `Protocol` stub, and float/`Decimal` literals other than
by their string (e.g. the `difflib` cutoff `0.6` is not varied).

## The 16 equivalent survivors (ignore)

| # | Line | Change | Why no output can differ |
|---|---|---|---|
| 17 | price_query.py:61 | under_60 lower bound `0` → `-1` | Lease months are never negative (the importer's pattern only accepts digits). |
| 39 | price_query.py:61 | 80_plus upper `100*12` → `101*12` | The importer rejects leases over 99 years (1,188 months), so 1,200 and 1,212 exclude the same nothing. |
| 41 | price_query.py:61 | 80_plus upper `100*12` → `100*13` | Same: 1,300 > 1,188. |
| 47 | price_query.py:62 | low floor band `(1, 6)` → `(0, 6)` | The importer rejects a storey range starting `00` (team decision, 2026-11-05; `test_storey_00_is_rejected_naming_the_row`), so no stored sale has lower storey 0. Rebuilding from the current CSV still gives 242,737 rows, identical to before. |
| 56 | price_query.py:62 | high floor upper `99` → `100` | Storey ranges are `NN TO NN`, so the lower storey is at most 99. |
| 136, 139 | price_query.py:226, 228 | `r[0]` → `r[-1]` on `SELECT DISTINCT town` / `flat_type` | One-column rows: the first and last element are the same. |
| 178 | price_query.py:277 | `source[0]` → `source[-1]` | `SELECT source_sha256` returns a one-column row. |
| 316 | price_display.py:79 | `len(bands) < 2` → `< 1` | With exactly one band, low and high are the same band, so `high < low × 1.1` holds and the note is still hidden. It would only show if the median were 0, but prices are at least $10,000 (importer bound). |
| 337, 368, 381, 385 | price_display.py:112, 125, 127, 128 | `groups[0]` → `groups[-1]` for volume, median, mean, IQR | Each of those regexes has one group. |
| 374, 375, 376 | price_display.py:126 | `'sale' if sales == 1` → `== 2` / `== 0` / `'XXsaleXX'` | Dead branch: this line only runs with 5+ sales, so `sales == 1` is never true. (Could be simplified to `sales`, but that's a code change, not a test.) |

## The 115 survivors killed by new tests, and what each test pins

All expected values are literals worked out by hand in the test comments, never from the
function under test. The last column is the survivors each test was written for; the rerun confirms all 115 are now killed. Some edges (lower storey 06, 12 or 99, a 0- or 99-year lease) don't occur
in the 2017+ snapshot: its lower storeys are 01, 04, 07, … 49 and leases start at 39 years.
The importer accepts them, though, so the bands must still place them correctly.

### `tests/test_price_boundaries.py` (price_query.py)

| Test | Pins | Written for mutants |
|---|---|---|
| `test_lease_bands_at_exactly_60_and_80_years`, `test_each_lease_band_filter_selects_its_two_sales` | 0 and 719 months → under_60; 720 (60 y) and 959 → 60_79; 960 (80 y) and 1,188 (99 y) → 80_plus. Even-count medians: (300k+400k)/2 = 350k, 550k, 800k | #16, 19–21, 24–26, 40 |
| `test_floor_bands_at_storey_6_7_12_13_and_99` | Lower storey 1, 6 → low; 7, 12 → mid; 13, 99 → high, inclusive. Medians 420k / 460k / 500k | #49, 51, 53, 55, 57, 205 |
| `test_recent_sales_are_the_five_newest_with_every_field` | Exactly 5 recent sales, newest first, with block, street, storey, area, lease and price in the right fields | #11, 12, 222–225, 232 |
| `test_low_volume_flag_is_one_to_nine_sales` | Thin-sample flag for 1–9 sales, not 0 or 10 | #9, 10, 123 |
| `test_query_id_is_the_documented_hash` | `price-` + first 12 hex of SHA-256 over the sorted-key JSON of version, CSV hash, params and bands (stable across rebuilds) | #126, 173–176, 179, 181–183 |
| `test_hyphenated_and_multi_generation_flat_types_are_normalised` | `5-room` → `5 ROOM`; `Multi-Generation` keeps its hyphen | #146, 147, 149, 150 |
| `test_unknown_value_messages` | Exact "Unknown town/flat type" messages; at most 3 suggestions | #151, 152, 154, 155, 157–161 |
| `test_outside_dataset_message_and_the_last_month_is_inside` | Exact out-of-coverage message; a period starting in the last data month is allowed | #164, 165, 168 |
| `test_unconfigured_and_missing_database_messages` | Exact messages | #58, 130 |
| `test_unreadable_database_message_from_info_and_from_query` | "could not be read" from both `info()` and `query()` | #141, 170 |
| `test_missing_metadata_message_from_info_and_from_query` | "no import metadata" from both | #143, 172 |
| `test_dataset_info_cannot_be_changed_by_callers` | `DatasetInfo` is frozen (it is cached and shared) | #106 |
| `test_database_path_defaults_to_data_processed_and_honours_the_env_var` | Default `data/processed/hdb_prices.db` under the repo root; `KOPI_RESALE_DB` overrides | #4, 5, 7, 8 |
| `test_bands_from_the_router_reach_the_filters` | Router lease/floor bands are kept | #97, 98 |
| `test_the_latest_month_and_jan_2017_are_inside_the_data` | `start == latest month` and `end == 2017-01` are not out of range | #102, 103 |
| `test_a_one_month_period_with_a_missing_town_is_not_called_a_future_period` | A one-month period with bad filters gives "couldn't work out", not the future-period message | #99, 100 |
| `test_before_2017_message_without_a_known_latest_month` | "…from Jan 2017 onwards…" wording | #94 |

### `tests/test_price_wording.py` (price_display.py)

| Test | Pins | Written for mutants |
|---|---|---|
| `test_subject_label_for_every_band` | Label text for all 6 bands | #287, 288, 290, 291, 293, 294, 296, 297 |
| `test_lease_note_names_the_lowest_and_highest_lease_band_medians` | Exact note; uses lease bands only (floor bands ignored); min and max the right way round | #308, 309, 313, 317, 318, 321–326 |
| `test_lease_note_counts_bands_with_5_sales_but_not_4` | A band needs 5+ sales | #310–312 |
| `test_lease_note_needs_two_bands` | Exactly 2 eligible bands is enough; 1 is not | #314, 315 |
| `test_lease_note_threshold_is_a_gap_of_at_least_10_percent` | Ratio exactly 1.10 shows the note; 1.05 doesn't | #319, 320 |
| `test_summary_answer_exact_text`, `test_summary_answer_with_the_lease_note` | Full answer text, with and without the note | #382, 386, 388–390 |
| `test_sales_count_with_a_thousands_separator` | "1,234 transactions" parses | #338 |
| `test_four_sales_exact_text`, `test_one_sale_exact_text` | Full low-volume text: "sale"/"sales", "It sold"/"They sold", a single price when low = high | #343, 347, 348, 351–358, 361 |
| `test_unexpected_layout_lists_each_verified_line` | Fallback: one bullet per non-blank line | #330, 332–334 |
