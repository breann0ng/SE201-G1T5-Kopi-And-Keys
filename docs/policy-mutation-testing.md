# Policy/verifier mutation checks

Nisha, initially checked 8 November 2026 and rerun against integrated main on
9 November. The UI/profile prerequisite is already merged. These curated
fault-injection checks complement Tasha's price-tool mutation tests.

## What is measured

`scripts/mutation_test_policy.py` removes or weakens 20 specific controls, one at
a time, in private copies of the code. Existing independent expected outputs in
five regression modules act as the oracle. It does not generate answers, call
Ollama, use a GPU, open the held-out set or train a model. The cases cover:

- Missing/invented citations, superseded sources and quotes absent from sources.
- Changed displayed wording, assistant-control output and low relevance.
- Multi-grant completeness, missing-evidence flags and household/PDF scope.
- SQL comparison, complete numeric-line grammar, duplicates and missing fields.
- Second-timer/mixed profile restrictions and the one-repair limit.
- Prompt/answer redaction in the Ollama trace span.

No new runtime dependencies are installed. Each child gets a fresh backend copy,
selected public test data and a minimal environment without inherited API/cloud
keys or proxy credentials. No `.env`, feedback DB, model files, private questions
or vector index is copied. Tests assert the copied verifier was actually imported
and deny real HTTPX transports; existing mock transports remain usable. These
test controls are not a general-purpose OS/network sandbox.

The HTTP blocker records a marker outside test results and raises a runtime
exception. Any attempted live HTTP invalidates the run as an isolation error,
even if a test catches the exception or another assertion fails. It never counts
as a killed mutant. A real subprocess regression exercises this containment path
without making a network connection.

The baseline must pass first. Every mutant runs the same complete selected suite
without `-x`, so execution count can be checked against the baseline. A pytest
assertion failure (including explicit `pytest.fail`) counts as killed. A mutant
that only causes runtime exceptions does not count; mixed assertion/runtime
failures are recorded separately and require at least one actual assertion.
Collection/setup errors, skipped tests,
missing/malformed JUnit, changed test counts and timeouts are reported separately
and fail the run; they do not inflate the score. A survivor also fails the run.
AST syntax and exact anchors are checked up front. Code drift requires reviewing
the mutation definitions rather than silently running fewer cases.

## Commands and evidence

```powershell
.\.venv\Scripts\python.exe scripts\mutation_test_policy.py --list
.\.venv\Scripts\python.exe scripts\mutation_test_policy.py --jobs 2
.\.venv\Scripts\python.exe -m pytest tests\test_policy_mutation_runner.py -q
```

The full local report is `.local/reports/policy-mutations.json`. It records the
baseline, mutations, failing test names/reasons, source/runner/test hashes, snapshot,
Python version and separate error counts. CI runs the check inside the existing
Backend tests job after pytest for PRs to the default branch and explicit manual
CI runs; it is skipped on the duplicate main push after merge. Unit tests still
run on main pushes. The mutation JSON artifact is retained for 14 days. The
upload action is pinned to the official v6 tag's immutable SHA. The repository
owner must make that Backend job a required branch-protection check if it is not
already required; merely committing a workflow does not enforce merging rules.

The initial run passed **108 baseline tests**, and **20/20 selected faults were
detected**, with zero survivors or infrastructure errors/timeouts. The first
baseline attempt exposed a missing copied policy-chunk fixture and stopped with
zero mutants scored; the copying boundary was corrected before the reported run.
Fifteen runner tests check classification, credential stripping, private-copy
mutation and cleanup, including a timeout case. No production module was changed
to increase this score; existing regression tests detected these faults. One
profile test was strengthened to assert a non-null clarification before indexing
it, so detection is an explicit failed requirement rather than a TypeError.

After merging main through PR #22 on 9 November, **109 baseline tests passed** and
all **20/20 faults were detected**, with zero survivors/errors/timeouts. The full
backend suite on this branch passed **700 tests**, with 1 skipped and 2 existing
expected failures. The isolated checkout had no built vector index and used the
documented keyword fallback in relevant tests. This is not a live hybrid-RAG or
held-out evaluation. The dated summary is
[`2026-11-09-policy-mutation-summary.json`](benchmarks/2026-11-09-policy-mutation-summary.json).

## How to present the result honestly

Say: "Our deterministic regression tests detected all 20 deliberately injected
verifier/profile/trace faults in this run." Do not call this 100% security,
whole-project mutation coverage, model safety accuracy or a held-out result.
Known-fault detection does not establish complete test coverage; code and tests
were AI-assisted and still need an independent teammate's review. Genuine source
text can be stale, poisoned or applied in the wrong context despite quote checks.
Lexical relevance is not a calibrated factual confidence score.

This check does not test public hosting, authentication, cross-user isolation,
feedback persistence, website access rules, dependency CVEs, browser layout,
actual model behaviour or the GPU tunnel. Those are separate review/test areas.
Tasha's existing runner treats nonzero test exits/timeouts as detected mutants;
inspect its raw results before comparing its price score with this stricter run.
