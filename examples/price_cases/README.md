# Extra synthetic SQL cases

Each JSON file represents a pretend Price Query Tool result. These are hand-authored
fixtures, not actual HDB transactions or a held-out evaluation dataset. No SQL
query is executed by this suite. Each case runs through the full graph
(router, synthesiser, verifier) with the file's `sql_result` standing in for the
Price Query Tool.

## Run all six checks

```powershell
# Run from the project root; the model/server must already be available.
.\.venv\Scripts\python.exe scripts\run_price_cases.py

# Check only input validation, without a model/server.
.\.venv\Scripts\python.exe scripts\run_price_cases.py --validate-only
```

Expected live summary: `6/6 checks passed. Mode: live_ollama.` The validation-only
mode checks accepted/rejected inputs; it does not test model generation.

| File | Expected live behaviour | What to inspect |
| --- | --- | --- |
| `zero_transactions.json` | `no_data` (abstains with a fixed message); zero model calls | No price values should be invented |
| `single_transaction.json` | `answered`; verifier passes | All prices 450,000.00, IQR 0.00, volume 1 |
| `decimal_rounding.json` | `answered`; verifier passes | Mean 612,345.13; median 610,000.01; IQR 33,333.34 |
| `large_amounts.json` | `answered`; verifier passes | Median 1,400,000.00; volume 1,250; no `1.4m` shorthand |
| `invalid_missing_median.json` | Input rejected before inference | A non-empty result cannot omit its median |
| `invalid_price_range.json` | Input rejected before inference | A minimum above the maximum cannot be accepted |

An invalid fixture is a **passing test when it is rejected as expected**. The
runner distinguishes this from a failed check. Live reports include each final
response, verification errors, model-call count and timing; find them under
`.local/reports/synthetic_cases_live_ollama.json`.

## Run and inspect one example yourself

```powershell
.\.venv\Scripts\python.exe -m kopi_keys.cli --input examples\price_cases\decimal_rounding.json
```

For valid non-empty results, look for `status: answered`,
`verification_passed: true`, an empty error list, and the values in the table.
For invalid fixtures, the individual CLI deliberately exits with an input
validation error. That is the expected outcome.

## Create another case

1. Copy a valid JSON file and give it a distinct query ID.
2. Change the statistics and keep `data_origin: synthetic_fixture`.
3. Write down the expected displayed values before running the model. Use
   two decimal places with ROUND_HALF_UP; retain more precision in the input.
4. Keep the statistics internally consistent: mean/median within minimum and
   maximum, IQR no greater than the range, and integer volume.
5. Run the CLI with the new file and compare its final response with your
   expected values. The runner's `CASES` list is explicit; add the file there
   if you also want it included in the batch run.

Changing a valid SQL input should change the expected answer. To test a wrong
generated answer against unchanged SQL, use the rejection tests in
`tests/test_synthesiser_verifier.py`; changing SQL itself does not simulate hallucination.
