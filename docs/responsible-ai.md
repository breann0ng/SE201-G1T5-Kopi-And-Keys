# Responsible AI: Kopi & Keys

Development risk record, 6 November 2026. Owner for policy synthesis/verifier:
Nisha. This records implemented controls and development evidence; it is not a
security certification, official eligibility decision or final held-out result.

## Purpose and boundaries

The advisor explains dated HDB/CPF policy evidence and historical resale
statistics. It cannot approve a housing application, promise a grant, predict a
future sale price or replace official HDB assessment. The reviewed ACTIVE policy
snapshot, not the model's memory, supplies policy facts. Statistical prices come
from parameterised queries on a read-only SQLite connection.

The chat graph calls local retrieval/price interfaces directly. It has no MCP
client/server, general shell-execution tool or model-written SQL executor.
Policy refresh is a separate maintenance workflow with human activation. MCP
would require its own permission and trust review if introduced; it is not a
prerequisite for RAG, refreshing sources or responsible AI.

## Risks, controls and evidence

| Risk | Current control | Evidence and remaining limit |
| --- | --- | --- |
| Invented or altered policy | Request-specific citation enum, quote membership and displayed-wording checks | `test_policy_safety.py`, `test_policy_advisor.py`; a genuine quote still needs correct source context and human interpretation |
| Incorrect interlocking grant advice | Requested-grant coverage, an explicit combination rule, supplied prerequisites and household/table scope | `test_policy_finals.py`; lexical relevance is a heuristic, not calibrated confidence or complete legal reasoning |
| User or retrieved-text injection | Inputs treated as data; constrained JSON; recognised assistant-control and credential-instruction output rejected; no general execution tool | Synthetic development suite and verifier tests; obfuscated instructions and poisoned factual content can evade these checks |
| Unsupported amounts or wrong prices | SQL determines statistics; numeric/provenance checks and low-volume median suppression | Existing price tests and Tasha's mutation report; these measures do not predict prices or validate every policy amount |
| Missing, superseded or unavailable evidence | Bounded repair, abstention, current-source checks and separate availability-error reporting | Safety cases include empty/superseded retrieval; conservative abstention reduces usefulness and is reported separately |
| Unnecessary personal-data disclosure | Optional profile fields, browser clearing, opt-in tracing example and content-free Ollama spans | A real local SDK span test checks redaction without network access; model service still receives the configured request |
| Uncontrolled changes | CI and teammate review procedure; new prompt/verifier changes receive regression tests | Main-branch protection settings are not verified here. CI does not run a live model; audit findings are report-only and need triage |
| Feedback poisoning or accidental learning | Browser votes do not modify the model, prompts or evidence | Future feedback collection needs consent, minimisation, review and regression tests before changes are deployed |

## Data handling and accountability

- **Browser:** profiles, conversations and votes use browser storage. This is not
  an encrypted account store. Users can clear it in Settings; use fictional
  profiles for demonstrations, and do not ask for NRICs, passwords or API keys.
- **Advisor/model:** requests contain the question, applicable profile and enabled
  history. The advisor can retain answer objects in an in-memory response cache
  until eviction/restart. The configured Ollama service can be local or an
  allocated GPU service; its operator's logging/storage also needs consideration.
- **LangSmith:** optional external monitoring. `ollama_chat` processors remove
  message/profile/evidence/answer text, keeping only message count and allowlisted
  usage fields. They do not scrub other spans, caller-provided metadata, exception
  traces or previously uploaded data. Existing `.env` files are not rewritten.
  Operators review access and retention and remove old sensitive traces when
  appropriate. Clearing browser data does not clear service caches or cloud data.
- **Evaluation:** safety profiles and passages are fictional. Live probes disable
  tracing and save reports under ignored `.local/reports/`. Curated public
  summaries must omit credentials, personal profiles and private endpoint details.
- **Feedback:** thumbs-up/down with an optional reason and comment is recorded
  for human review only ([feedback-loop.md](feedback-loop.md)): on the answer's
  LangSmith trace when tracing is on, and in a git-ignored local SQLite file with
  the question, answer, route and snapshot date taken from the server. It is
  write-only over HTTP, never logged at INFO or above, never placed in prompts or
  retrieval queries, and no pipeline module imports it. The comment box asks users
  not to include personal details. A negative vote is not a training label by
  itself. Do not automatically fine-tune or change policy from user votes.

Nisha reviews policy/verifier failures; Breann owns routing/orchestration;
Sandra owns source/retrieval/topic-card review; Tasha owns price tools and the
expanded evaluation. A teammate should review security changes before merge.
The repository owner should verify required PR approval and CI checks in branch
protection. Prompts, code, model tags/digests, settings, snapshot and test versions
should be recorded so a failure can be reproduced.

## Development evaluation and reproduction

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_policy_safety.py tests/test_policy_safety_runner.py
.\.venv\Scripts\python.exe -m kopi_keys.evaluation.policy_safety
.\.venv\Scripts\python.exe -m kopi_keys.evaluation.policy_safety --live --model qwen2.5:3b --device cpu --threads 8 --output .local/reports/policy-safety-live.json
```

The fixture tests validate deterministic rejection, repair and the checker.
The live command uses the production graph, fixed fictional passages and actual
Ollama inference. Sixteen labelled development cases include three positive
controls, so refusing everything cannot pass. A model outage cannot count as a
safe refusal. For answerable attack cases, either a verified supported answer or
a refusal is accepted for containment; answerability is reported independently.
Review answers, verifier errors and abstentions rather than reporting only a
single pass percentage. Human reviewers must check meaning and missing context;
the automatic coverage check does not establish factual or semantic accuracy.

The 6 November CPU run used actual `qwen2.5:3b` inference, eight threads and one
repair at most: **16/16 automatic checks passed**, all **8/8 answerable** cases
answered, **8/8** insufficient/unsafe-evidence cases abstained, and all **3/3
positive controls** passed. There were no availability errors; median case wall
time was 9.692 seconds, including two no-inference preflight cases. The run made
21 model calls. See the [curated summary](benchmarks/2026-11-06-policy-safety-summary.json)
for per-case outcomes, model digest, case hash and limits. Independent human
review remains pending; this is development evidence, not held-out safety accuracy.

Replaying 36 historical generations against baseline-main and the new verifier
gave no changed outcomes between those verifiers. Five records already require
an unavailable additional repair on baseline when using the current evidence;
this replay therefore does not reproduce the historical accuracy scores. Keep
those original scores tied to their recorded run rather than claiming a fresh
current-model measurement.

No held-out questions are read by these commands. Before final evaluation, freeze
the reviewed code, prompts, model, inference settings and ACTIVE snapshot. Run
the team's fresh held-out set separately. Findings used to tune the system are
development findings; tuning after a held-out run changes its interpretation.

## Policy fault injection, 8 November 2026

The UI/profile/verifier follow-up has an offline, curated mutation check in
`scripts/mutation_test_policy.py`. It checks whether existing regression tests
notice 20 deliberately removed/weakened controls, including citation validity,
source/household scope, numeric output, the repair bound and trace redaction.
The 108-test baseline passed and all 20 selected faults were detected by at least
one assertion or explicit test failure. There were no runner/setup errors or
timeouts. Pure runtime exceptions cannot count as detection; additional runtime
side effects are recorded separately in the report. Fifteen tests check the
runner's classification, credential stripping, copy isolation and cleanup.

This is development evidence for named faults, not whole-project mutation
coverage, independent validation, model behaviour or a security guarantee. The
code/test pairing still requires a teammate's review. CI runs it after pytest
with a read-only token and retains its report; hosted execution and required
branch protection need verification after merge. No GPU, held-out questions,
production profiles or new Python dependencies were used. See the
[method and commands](policy-mutation-testing.md),
[curated result](benchmarks/2026-11-08-policy-mutation-summary.json), and
[remaining integration/security/evaluation work](finals-readiness.md).

## Known limits and follow-up

- The current deterministic router treats bare `Explain PHG conditions.` as out
  of scope; the full grant name routes correctly. SAFE-16 uses the full name to
  exercise synthesis. This is recorded for the router owner, not silently claimed
  as fixed by the policy work.
- Recognised injection patterns are deliberately narrow. The tests do not cover
  all encodings, malicious websites, arbitrary MCP servers, deployment attacks or
  denial of service. Source authenticity and reviewed policy completeness remain
  essential even when a quote matches a retrieved passage.
- The 12-case historical model benchmarks and this 16-case safety suite are small
  development evaluations. Neither establishes general safety, fairness or final
  policy accuracy. Human benchmark review and fresh held-out evaluation remain
  team activities.
- Before public hosting, review authentication, rate limits, request/model
  budgets, transport security, storage isolation and dependency-audit findings.
  The current local demonstration is not a reviewed public service.

Reference guidance: [OWASP prompt injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/),
[MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture), and
[LangSmith data masking](https://docs.langchain.com/langsmith/mask-inputs-outputs).
