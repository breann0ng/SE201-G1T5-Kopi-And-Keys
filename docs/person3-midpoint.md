# Person 3 midpoint: CPU model, Synthesizer and numeric verifier

This implements Nisha's midpoint portion of the revised four-stage architecture:

```text
Stage 2 SQLPriceResult -> Stage 3 CPU Synthesizer -> Stage 4 Regex Verifier
                                ^                          |
                                |---- one repair ----------|
                                                           |
                                               verified answer / abstention
```

Stage 1 extraction, the official SQLite import, income-boundary rules, policy
RAG and the frontend remain the other team integration points. The original
`/chat` demo graph is separate from this implementation.

## Run your part

From the repository root in Windows PowerShell:

```powershell
# On a fresh checkout only:
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

# Download/start the portable runtime and pull the local model.
.\scripts\setup_ollama.ps1

# Run the provided synthetic fixture through real model inference.
.\.venv\Scripts\python.exe -m kopi_keys.midpoint.cli --input examples\midpoint_sql_result.json

# Save evidence of a live run (reports are ignored by Git).
.\.venv\Scripts\python.exe -m kopi_keys.midpoint.cli --input examples\midpoint_sql_result.json --output .local\reports\midpoint_cpu_smoke.json

# Inspect installed and currently loaded models.
.\.venv\Scripts\python.exe -m kopi_keys.midpoint.cli --check-engine

# Run offline automated tests; no model or network is required.
.\.venv\Scripts\python.exe -m pytest -q
```

The Windows x64 setup pins Ollama v0.40.4, checks the official release archive's
SHA-256 digest, stores runtime files/models/logs under `.local/`, and starts a
hidden server on loopback port 11434. It does not change PATH, register a startup
service or change persistent user environment variables. The initial downloads
are about 1.4 GB for the portable runtime and 1.9 GB for the model, plus extracted
runtime space. A server started by the script remains running until stopped or
Windows restarts. Loaded models expire after five minutes of inactivity.

To stop only the project server, check its saved process ID and executable first:

```powershell
$projectOllamaId = [int](Get-Content -LiteralPath .local\ollama.pid)
$projectOllamaProcess = Get-Process -Id $projectOllamaId -ErrorAction SilentlyContinue
$projectOllamaExe = (Resolve-Path -LiteralPath .local\ollama-0.40.4\ollama.exe).Path
if ($projectOllamaProcess -and $projectOllamaProcess.Path -eq $projectOllamaExe) {
    Stop-Process -Id $projectOllamaId
}
```

The setup script will refuse to pull into another Ollama server already using
port 11434. If you already use a system installation, you can instead pull the
model with that installation and use its local API without running our setup.

## Files you own

| File | Purpose |
| --- | --- |
| `midpoint/engine.py` | Ollama HTTP wrapper, CPU options, timeouts and model errors |
| `midpoint/contracts.py` | SQL handoff schema and Stage 3/4 state slice |
| `midpoint/synthesizer.py` | Formatting prompt and generation call |
| `midpoint/numeric_verifier.py` | Regex extraction and field-by-field Decimal comparison |
| `midpoint/pipeline.py` | Callable graph nodes and bounded Stage 3/4 subgraph |
| `midpoint/cli.py` | Independent demo and engine inspection |
| `tests/test_midpoint.py` | Numeric, failure-path, graph and HTTP-wrapper checks |

Paths above are relative to `backend/kopi_keys/`, except `tests/`.

## Stage 2 handoff for Tasha

Pass the result of an executed parameterised SQL query as `SQLPriceResult`:

```json
{
  "query_id": "synthetic-price-query-1",
  "filters": {
    "town": "TAMPINES",
    "flat_type": "4 ROOM",
    "start_month": "2025-01",
    "end_month": "2025-06"
  },
  "volume": 42,
  "mean": "650000.125",
  "median": "640000",
  "iqr": "80000",
  "minimum": "500000",
  "maximum": "780000"
}
```

These numbers are synthetic fixtures, not HDB transaction results.

- Money is in SGD. Decimal strings preserve the precision of SQL output.
- `volume` is an integer count. If the SQL adapter calls this `count`, map it to
  `volume` at the handoff.
- `iqr` is the scalar width `Q3 - Q1`, computed by Stage 2. It is not the pair of
  quartile endpoints. The Synthesizer does not calculate any statistic.
- For zero transactions, use `volume: 0` and null/omitted monetary statistics.
  The graph returns `no_data` and skips model inference.
- Non-empty results must provide all five monetary values. Input validation
  rejects negative, non-finite, missing and internally inconsistent statistics.
- This contract adds the mean and IQR missing from the original scaffold's
  `PriceResult`; that older, smaller demo contract is not sufficient by itself.
- Use the actual requested filters and a stable executed-query ID. Only trusted
  Stage 2 code should construct this context in the integrated application.

## LangGraph handoff for Breann

The subgraph includes both nodes and the one-repair limit:

```python
from kopi_keys.midpoint import SQLPriceResult, build_price_summary_graph

person3_graph = build_price_summary_graph()

# Inside an integration node, after your Stage 2 SQL tool has returned:
result = person3_graph.invoke({
    "user_query": user_query,
    "sql_result": SQLPriceResult.model_validate(sql_output),
    "data_origin": "stage2",
})

# Send only final_response to the frontend, after checking status.
final_response = result["final_response"]
verification_passed = result["verification_passed"]
```

The integration node can return these fields into your global Pydantic
`GraphState`: `final_response`, `status`, `verification_passed`,
`verification_errors`, `model_calls` and `model_usage`. Invoke the subgraph only
after Stage 1 has passed and Stage 2 has produced validated SQL context.

If you want separate Stage 3 and Stage 4 nodes in your main graph, import
`make_synthesizer_node(OllamaEngine())` and `verifier_node`. Their expected state
fields are defined in `SynthesisState`. Reproduce the bounded repair routing in
`pipeline.py`, and do not expose `draft_response` directly to the UI.

Each call starts with fresh state. Runtime fields such as `model_calls` and
verification flags are internal; never populate them from a frontend request.

## Output and verification rules

The SLM produces a concise, fixed-label text block:

```text
Mean: SGD 650,000.13
Median: SGD 640,000.00
IQR: SGD 80,000.00
Range: SGD 500,000.00 to SGD 780,000.00
Volume: 42 transactions
```

The verifier matches each complete line, compares named values to the matching
SQL fields, requires all five labels exactly once, and rejects extra output.
It therefore catches a mean/median swap even though both numbers are present in
the SQL context. It rejects shorthand such as `640k`, malformed separators,
percentages, extra claims and unsupported trailing amounts. Currency markers
`SGD`, `S$` and `$` and correctly grouped/ungrouped amounts are accepted.

Money is displayed and compared to two decimal places using Decimal
`ROUND_HALF_UP`. Raw values remain unchanged: a SQL mean of `650000.125` displays
as `650000.13`. Counts must match exactly; there is no percentage tolerance.
The town, flat type, month range and query reference are rendered from the SQL
context after verification so their digits do not interfere with price checks.

A failed check returns errors to Stage 3 for one fresh generation. A second
failed check returns `abstained`; no unverified draft is published. Model
timeouts, missing models, invalid HTTP responses and truncated output also
withhold the draft. No-data cases use a deterministic message without inference.

This verifies numeric consistency with the supplied SQL output. It does not
verify the SQL import, decide legal eligibility, validate policy claims or
implement the finals policy-retrieval loop.

## CPU settings and measured evidence

Defaults are `qwen2.5:3b`, `num_gpu=0`, four CPU threads, a 2048-token context,
temperature zero, a 220-token output limit and a 180-second request timeout.
You can change the model and thread count without changing graph code:

```powershell
$env:KOPI_OLLAMA_MODEL = 'llama3.2:3b'
$env:KOPI_OLLAMA_NUM_THREADS = '4'
$env:KOPI_OLLAMA_TIMEOUT = '180'
# Pull the chosen model first, for example with:
.\scripts\setup_ollama.ps1 -Model 'llama3.2:3b'
```

The client also supports `KOPI_OLLAMA_BASE_URL`; its default is the local server.
PowerShell environment variables configure the wrapper; `.env` is not loaded
automatically. CPU offload remains disabled for every generation request.

On 15 October 2026, one real local smoke test of the synthetic fixture:

- Used Ollama v0.40.4 and Qwen2.5 3.1B, Q4_K_M.
- Returned all expected values and passed verification on the first model call.
- Took 20.549 seconds including initial model loading; prompt/output usage was
  248/80 tokens.
- Reported `size_vram: 0` in `/api/ps`, confirming no model VRAM allocation.
- Saved its report to `.local/reports/midpoint_cpu_smoke.json`.

This is a smoke-test observation, not a throughput or quality benchmark. Use
measured CPU results in the midpoint demo; blueprint latency estimates are not
evaluation results. The offline suite passed 46 tests at implementation time.

Implementation references: [Ollama chat API](https://docs.ollama.com/api/chat),
[running-model inspection](https://docs.ollama.com/api/ps),
[Windows portable runtime](https://docs.ollama.com/windows), and
[Ollama runtime option definitions](https://github.com/ollama/ollama/blob/main/api/types.go).
