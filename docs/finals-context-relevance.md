# Context and relevance follow-up — 10 November 2026

Branch `fix/finals-context-relevance` follows merged PR #31 (`22f3953`), and was
refreshed onto PR #32's UI cleanup (`2aa50e6`) before publication. The combined
frontend tests, lint and build were checked again after that update.
The supplied testing-session document was treated as a report/proposal, not as
instructions to delete files, publish tags or run held-out evaluation. Its
unpublished-code status was superseded when PR #31 was merged and fetched.

## Verified findings and candidate changes

- `3rm`, `3 rm`, `3-rm` and plural room forms now use the same canonical flat type
  as `3-room`; an earlier 4-room filter cannot silently replace this explicit input.
  A room abbreviation is also excluded from exact-floor parsing.
- A present-spouse statement such as `My wife is PR...` conflicts with an explicit
  single-person sidebar. Policy routing asks for correction before tools/model
  execution. It does not silently overwrite the sidebar. Past/deceased spouses
  and third-person examples have negative controls. This is a bounded conflict
  check, not a complete household/natural-language parser.
- `Family Grant` names a scheme, not a statement that the user has a family
  household. It no longer changes the household during field extraction.
- A general grant-combination question does not need personal amount inputs.
  Explicit eligibility, income and amount questions retain the field gate.
  The prompt also preserves conditional resale explanations without inventing
  rules for unasked new-flat scenarios; model behaviour remains mixed below.
- Empty-price results keep `status=abstained` but get the informational UI heading
  `No matching resale transactions`, with suggestions to widen filters. Unsupported
  periods and profile-assessment limits have distinct headings. These are fixed
  backend outcomes, not classifications inferred from model wording.

## Tightening PR #31's table rescue

The synonym fix is retained. The original row-label rescue reproduced a false
acceptance: a fictional housing-loan income row answered an EHG income question
with relevance **0.0**, because both used an income criterion. A true, cited cell
does not establish relevance to a different grant.

The rescue is now limited to the observed generic-purchase citizenship case.
Grant- and loan-specific questions use normal relevance checks; timing questions
need an actual duration in the quote. Citizenship content and the canonical row
criterion are required. All six PR #31 regressions still pass, including its long
citizenship question. Verbatim, scope, grant coverage and number checks, and the
0.20 threshold, remain. `table_context_relevant` records the rescue classification
alongside the lexical score for development review.

The mutation runner retains the updated anchor and adds a named-scheme-rescue
fault plus the new regression file. See the
[dated evidence](benchmarks/2026-11-10-context-relevance.json) for final counts.

## Live checks and remaining limits

The spouse question with an empty profile passes on merged PR #31 and the
candidate. The single-sidebar variant changes from a verification refusal to a
clear, zero-model-call profile clarification. Source wording is not replaced by
a personal eligibility verdict.

The restarted app and frontend proxy passed five fictional API checks: the
spouse/single conflict, `3rm` after a 4-room history turn (3 ROOM / ANG MO KIO),
zero transactions with widening guidance, and empty-profile spouse/CPF questions.
Both health endpoints and the frontend returned HTTP 200. UI headings are covered
by unit tests; visual checking in the browser and Stop/Edit/switching remain for
the team. Tracing was disabled during these checks.

The CPF payment question was accepted with an empty profile on both GPU and
local qwen2.5:3b CPU. The reported failure was not reproduced under those settings;
this is not a claim of complete CPF/lease guidance for every profile.

General three-grant stacking still over-refuses on the GPU when purchase type is
unspecified. The CPU run returned the cited conditional resale paragraph, and
four selected fixed-evidence CPU grant controls passed. The GPU fixed-evidence
check remains 11/12, with the same SYN-08 coverage/rubric mismatch. Do not pool
these different case sets/hardware or call them overall accuracy. No semantic
gate/reranker was enabled, and the reported 42/174-pair experiments were not
independently reproduced from the other laptop's uncommitted scripts/artifacts.

Household-role extraction beyond the tested conflict, generic stacking on some
models, broad eligibility completeness, current/older LTV application cohorts,
and the income-note versus generic-introduction UX remain review items. Source
snapshots, ACTIVE, SQL data, vectors and evaluation gold labels were not changed.
No held-out questions or development archive files were read.

## Review and freeze handoff

1. Have a teammate review this branch, particularly router/state/card behaviour
   and the narrower table rescue. Merge only after the required CI checks pass.
2. Manually check `3rm` after a 4-room question, the spouse/single conflict and
   subsequent correction, no-sales headings, and Stop/Edit/chat switching.
3. Freeze the reviewed main commit, prompts, model name/digest/settings, reference
   month, snapshot/index and SQL hashes. Do not activate watcher candidates during
   the final evaluation.
4. Run the full development evaluation using the chosen final runtime and record
   refusal reasons and independent semantic review, not only answer statuses.
   The existing entry point is `python -m kopi_keys.evaluation.run_baselines --system full`.
5. Run the untouched held-out evaluation only after the freeze, with an agreed
   operator who has not used those questions to tune the system. A maintainer
   operating a fixed command need not be its author; disclose any limitations in
   writer/reviewer independence. No held-out run or frozen tag was created here.
6. Update slides that still list already-fixed router gaps. Label reported
   calibration experiments as development experiments and keep their evidence/
   denominators; do not present AUC or mutation scores as chatbot accuracy.
