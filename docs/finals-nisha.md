# Nisha's finals: policy synthesis, verifier and CPU model comparison

Branch: `feat/nisha-finals-policy-guardrails`. Work started 26 October 2026
(Asia/Singapore). The router, retrieval ranking, topic-card income rules, price
queries, UI and the team's expanded evaluation set remain their owners' tasks.

## Implemented behaviour

`components/policy_synthesis.py` selects source excerpts rather than displaying
model-written policy facts. Its finals prompt requires all named grants, their
relationship, and any supplied prerequisite. It distinguishes household types
and new versus resale purchases, disallows adding maximum amounts, and allows
`missing_evidence` instead of inventing a rule.

Ordinary questions retain three passages / 800 source words / three claims.
Questions naming multiple supported grants use up to five complete passages /
1,200 source words / six claims. The policy model retains a 4,096-token context
and 850-token output limit. Passage selection uses only the retrieved evidence;
it does not fetch missing policy. Breann's backtracking can supply more passages
through the existing `GraphState.passages` contract.

The request-specific Ollama JSON schema enumerates the supplied citation IDs.
Pydantic checks them again after decoding. JSON errors, including an unknown ID,
are returned through `SynthesisResult.validation_errors` to
`GraphState.synthesis_errors` and the normal verifier repair loop. They do not
become an `engine_unavailable` error. Validation details are local to each request.

## Verifier guardrails

The existing exact numeric SQL checks, source provenance checks, superseded-source
rejection, scoped table rendering, and PR citizenship-column checks remain.
Additional checks in `components/policy_guardrails.py` and `verifier.py` include:

- A per-quote lexical relevance score. Generic housing terms do not establish
  relevance. Named grants and requested aspects such as income, employment or
  proximity matter; a matching heading alone cannot satisfy an aspect question.
- Rejection below `KOPI_POLICY_MIN_RELEVANCE` (default 0.20). This is an initial
  development threshold, not a calibrated probability or a measured accuracy.
- Coverage of every explicitly named supported grant. When asked about stacking,
  separate grant descriptions do not prove the relationship: a continuous source
  excerpt must connect the grants. New-flat questions can instead quote an explicit
  exclusion rule. Supplied resale EHG qualification prerequisites must be retained.
- Rejection of clearly opposite household scopes, with an exception for explicit
  comparisons and mixed first/second-timer or non-resident-spouse questions.
- Presentation-only normalization of Markdown bold and HTML emphasis, whitespace
  and PDF hyphen wraps. Words, amounts, qualifiers and list content are preserved;
  stitched or changed policy wording is rejected.

Each score and its matched terms are available in `GraphState.relevance_scores`.
The lexical component is the fraction of specific query terms found in the quote,
with one-quarter credit for additional heading matches. For named grants, the
score weights grant coverage at 0.7 and that lexical component at 0.3. A requested
policy aspect absent from the quote/criterion forces the score to zero. Complete
multi-grant coverage is checked separately, so an average cannot hide a missing grant.
Low scores use the existing single synthesis repair. A second failure abstains.
The graph may drop an unrelated claim only if the remaining answer passes all
checks, including multi-grant coverage. It cannot salvage a partial grant answer
as a complete one. No additional verifier model call is needed.

These checks cannot prove semantic entailment or final eligibility. Source tables
with missing headers, ambiguous household scope, unfamiliar grant names and
paraphrased questions can still cause misses. Legacy offline test drafts without
`supporting_quote` bypass quote relevance; the real policy engine always supplies
quotes. Human policy review and fresh held-out evaluation are still required.

For a UI check, fill in the profile (for example, a first-timer couple/family)
and ask `Can EHG and PHG be combined for a resale flat?`. A successful answer
must cite a grant relationship and preserve the resale qualification prerequisite;
two unrelated grant descriptions are insufficient. `Compare EHG and PHG` does not
require a stacking verdict. A new-flat question must preserve the source's exclusion
instead of applying a resale combination. Missing source rules can still produce
abstention until retrieval/backtracking supplies them.

## Reproduce the synthesis benchmark

`data/benchmarks/synthesis_cases.json` contains 12 development cases covering
multi-grant families and singles, three-grant prerequisites, new-flat exclusions,
income and employment conditions, proximity, a loan control, missing relationship
evidence, and irrelevant evidence. Gold quote groups resolve against the dated
ACTIVE snapshot. A different ACTIVE snapshot requires reviewing these labels.
These cases are not an addition to the team's 50-dev / 40-held-out dataset and
are not unseen final evaluation data.

With Ollama running and the models installed:

```powershell
.\.venv\Scripts\python.exe -m kopi_keys.evaluation.synthesis_benchmark --validate-only
$env:LANGSMITH_TRACING = 'false'
$env:LANGCHAIN_TRACING_V2 = 'false'
.\.venv\Scripts\python.exe -m kopi_keys.evaluation.synthesis_benchmark --device cpu --models qwen2.5:3b qwen3:4b --threads 8 --repeats 1
```

For a model not installed yet, use the existing setup script before running:

```powershell
.\scripts\setup_ollama.ps1 -Model qwen2.5:7b
.\.venv\Scripts\python.exe -m kopi_keys.evaluation.synthesis_benchmark --device cpu --models qwen2.5:3b qwen2.5:7b --threads 8 --repeats 3
```

Larger models require more local disk and memory. The benchmark does not download
models or change `.env`. It pins each requested model even if `KOPI_POLICY_MODEL`
is set, forces CPU (`num_gpu=0`), uses temperature 0 / seed 42, and gives both models
the same evidence and limits. Each model batch has an unscored policy-budget warm-up;
other compared models are unloaded between batches to avoid memory pressure, and
alternating repeats reverse model order. Generation logs retain load time, prompt
evaluation time, output tokens, generation time, repairs and total answer latency.

The later [GPU cluster setup](gpu-cluster.md) adds opt-in GPU runs using
`--device gpu`. Keep CPU and GPU results separate and verify actual offload.

Reports are saved after each case under `.local/reports/`. They include dataset
and evidence hashes, settings, hardware description, raw outputs, scores and errors.
The report records planned model/case IDs and `completed`; an interrupted run must
not be treated as a completed comparison.
Use `--case-ids SYN-01 SYN-03` for a smaller diagnostic or `--output` for a fixed path.
Do not run the app or other inference workloads during a timed comparison.

Automatic quality checks require both the expected answer/abstention outcome and
the labelled quote coverage. An engine failure is an error, not a correct abstention.
An answer passing the verifier can still fail coverage. These scores measure a
bounded quote-selection task, not unrestricted writing quality or legal accuracy.
`first_attempt_verifier_passes` includes production's safe pruning;
`raw_first_attempt_passes` counts only initially clean drafts, and
`answers_after_claim_pruning` reports the distinction explicitly.
The report includes blank human-review fields for scope, grant logic, relevance
and clarity (0 = wrong/missing, 1 = partial, 2 = complete); a reviewer should read
each answer against its evidence before drawing a model-quality conclusion.
Qwen3:4b differs in family as well as size, so this is not a controlled parameter-count
experiment. Use the optional Qwen2.5:7b command for a same-family comparison.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest tests/test_policy_finals.py tests/test_synthesis_benchmark.py -q
```

The new tests exercise real graph repair/abstention paths with controlled model
outputs, multi-grant completeness, wrong-topic and wrong-aspect quotes, household
scope, presentation normalization, request-local citation enums, explicit benchmark
model selection, source-resolved benchmark labels and independent coverage scoring.
The existing price and API tests continue to cover integration regressions.
Previously saved live loan and PR-couple drafts were also replayed against the
current sources and verifier and passed. This replay did not call a model and
does not establish that a new inference run will always return the same answer.

## Measured development results (26 October 2026)

The complete exploratory comparison used 12 fixed-evidence cases per model,
eight CPU threads, no GPU, one repeat, and a 240-second request timeout:

| Check | Qwen2.5:3b | Qwen3:4b |
| --- | --- | --- |
| Expected outcome and required quote coverage | 10/12 | 9/12 |
| Answered among 10 answerable cases | 8/10 | 7/10 |
| Correct abstentions on 2 insufficient-evidence cases | 2/2 | 2/2 |
| Engine timeouts | 0 | 1 |
| Observed median wall time | 38.1 s | 56.2 s |
| Initially clean drafts, before safe pruning/repair | 4/12 | 6/12 |

These timings are **exploratory**, not an isolated speed comparison. The shared
Windows laptop had 16 logical CPUs and approximately 16 GB physical RAM. Models
initially remained resident together; the unused 3B model was released during the
4B batch. Memory load reached 91%, and one 4B case took 218.7 seconds. Test work
also overlapped the first 3B case. The revised runner unloads compared models between
batches. A follow-up 4B diagnostic with the 3B model unloaded timed out on its first
case (240.7 seconds); its remaining two extra cases were stopped and are not
reported as completed. Power, thermals and other desktop workloads were not controlled.

Both models answered the family and three-grant stacking cases, but withheld the
singles stacking answer after failing quote/relationship checks. The 3B model also
withheld the proximity case after rewriting a source list. The 4B model withheld
the new-flat exclusion case and timed out on the employment case. The larger
model therefore did not establish an overall quality advantage on this small
development set. Keep Qwen2.5:3b as the default; this does not establish that it
is generally better than larger models.

All 24 original model outcomes were replayed against the final verifier with no
changed outcomes. The distinct-heading fix also leaves all 12 benchmark evidence
selections unchanged. The reviewable [summary JSON](benchmarks/2026-10-26-synthesis-summary.json)
includes settings, hashes, per-case outcomes and limitations. Full raw outputs
remain in `.local/reports/finals_synthesis_benchmark.json`.

The final application smoke check returned an answered, verified PR-couple response
in 4.6 seconds. A multi-grant request through the actual hybrid-retrieval graph
timed out after 181 seconds and safely abstained (`engine_unavailable`). Ollama's
log showed CPU prompt processing still underway, not a verified policy answer.
This is a material live-demo limitation. Fixed-evidence benchmark success does
not guarantee low-latency end-to-end answers with retrieved context.
