# Final integration, safety and evaluation checklist

Initial status checked 8 November 2026; integration update below dated 9 November.
This records work remaining, not a security certification or approval to deploy.
The pasted generic AI-development checklist
was treated as a proposal, not repository instructions or verified course text.

## Integration update — 9 November 2026

PRs #16–#22 are now merged. The removed SYN-08 evidence mapping, source
table test IDs, router scope restrictions and feedback record/trace ownership
fixes are on main. PR #23 contains the separate New chat selection fix; PR #24 is
the candidate-only price watcher. This mutation branch has merged current main:
700 backend tests passed (1 skipped, 2 expected failures), 109 selected baseline
tests passed and 20/20 curated faults were detected without errors/timeouts.
These are branch-specific development checks, not a combined final evaluation.

The policy watcher is being prepared separately, reconciling candidate pre-builds
with draft-PR publication. It still requires teammate review and a hosted run to
check permissions/source access. Historical findings below describe the earlier
revisions and should not be read as the current PR status. GPU/manual UI checks,
semantic answer review, code/data freeze and independent held-out evaluation
remain separate tasks.

## Recommended demo

Use a local laptop demo for finals, with a short recording as backup. Use an
allocated GPU privately through SSH tunnelling if the live model needs it. Keep
Ollama/Jupyter bound to private/loopback interfaces; do not expose their ports
publicly. Do not put model/trace credentials into frontend variables or commits.
This choice avoids adding a public-service security scope during the freeze.

The GPU helps actual inference speed/model comparisons. It is unnecessary for
unit tests, SQL fixtures, mutation tests, CI lint/build, source validation and
most negative security checks. A faster/larger model does not repair a bad
router, missing evidence, wrong household scope or an unverified policy snapshot.
Do not reuse an expired cluster allocation, old node/port or notebook token.

## Work in order

1. **Resolve the reviewed PR findings.** At the checked revisions #16/#18 still
   reference removed SYN-08 chunk IDs. In isolated review copies, replacing them
   with CHUNK_LOAN_49/50/51/52 preserved every gold quote and removed all seven
   failures. Authors must commit the mapping and rerun CI. #18 contains #16;
   merge/rebase in that order. Its hybrid benchmark must detect embedding failure
   rather than silently publish keyword-only results labelled hybrid. #17 still
   needs stable/updateable LangSmith feedback records and trusted server-side
   message-to-trace association for unknown/expired message contexts.
2. **Integrate Nisha's branches.** Finish the UI/profile PR, this dependent mutation
   PR, and the independent watcher PR through teammate review. Sandra's rechunking
   removes EHG IDs used in the new UI test fixtures, so update their selectors
   to stable source/quote identity and rerun the frontend tests. Reconcile Sandra's
   candidate pre-build step with the watcher's draft-PR workflow. Keep ACTIVE fixed.
3. **Run checks on the combined commit.** Full pytest, frontend tests/lint/build,
   snapshot/card validation, price and policy mutation checks, and dependency/
   secret scans. Triage audit findings; the current audit is report-only. Do not
   add branch test counts together and call the sum an integrated test result.
4. **Check runtime boundaries.** Use fictional profiles and mock services. Cover
   injection in a user message and retrieved passage; invented/stale citations;
   missing grant prerequisites; unrelated true quotes; wrong household and
   specialised PDF scope; altered numbers; SQL filter mismatch; malformed API
   inputs; model/embedding failures; cancellation; feedback failure/forgery and
   privacy redaction. Use positive controls so refusing everything cannot pass.
   The scraper currently follows redirects before checking the destination;
   validate each hop before fetching it as a focused hardening follow-up.
5. **Verify the human controls.** Owner checks required teammate approval, passing
   Backend/Frontend/Secret checks, stale-approval handling and bypass settings.
   GitHub protection settings have not been verified from code inspection. A
   workflow and AGENTS.md can be edited by a coding agent; protect workflow changes
   through server-enforced review. AI logs here are Git-versioned, not immutable.
   Never claim an append-only/external audit store without implementing it.
6. **Review privacy.** Decide whether tracing is needed. Redaction of `ollama_chat`
   does not scrub root/node spans, errors, other metadata or old traces. Review
   LangSmith access/retention with fictional test data. Document feedback question/
   answer/comment retention and deletion. Clearing the browser does not clear
   server/cloud records. No secrets or real personal profiles in screenshots/evals.
7. **Run live dev checks, with GPU if useful.** Reconnect VPN, obtain a current
   allocation, inspect its actually allocated GPU/MIG memory, start the server and
   a private tunnel. Verify the model is GPU-loaded before reporting GPU latency.
   Use the agreed model/digest/settings across comparisons; check outputs, source
   dates, abstentions and latency, not speed alone. Compare with the CPU baseline
   separately. Test live Stop/Edit/Copy, profile changes, scrolling and charts.
8. **Freeze and evaluate.** Record code commit, prompts, model digest, inference
   settings, ACTIVE version, chunk/index and SQL dataset versions. Have someone
   independent review semantic correctness and qualifications. Only then run the
   team's fresh held-out set. Do not use it while implementing these fixes. If a
   held-out finding leads to tuning, disclose the change and arrange a fresh final
   assessment rather than reclassifying a tuned score as untouched performance.
9. **Prepare evidence and handoff.** Report denominators, error/timeout counts,
   manual-review rubric and known limits. Keep a demo recording and the local
   fallback. Stop the GPU job when finished; closing the laptop/tunnel alone is
   not evidence that the scheduler allocation stopped.

## Before considering public hosting

Define authentication/session isolation, rate and concurrency limits, request/
model budgets, TLS/network exposure, server-held secrets, safe links/output
rendering, dependency findings, feedback abuse controls, storage/trace retention
and monitoring. Test those controls before opening access. These are not completed
by a prompt, by adding MCP, by a high mutation score or by connecting a GPU.

For the presentation, distinguish AI-assisted development controls (branches,
restricted access, PR review, CI and disclosure) from runtime controls (bounded
tools, parameterised read-only SQL, source checks, verifier and abstention).
Demonstrate a rejected invalid citation or SQL write on a disposable fixture and
a valid answer passing. Do not attempt a real destructive/protected action just
to manufacture a screenshot of a blocked permission request.

References: [OWASP prompt-injection mitigations](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
and [GitHub protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).
