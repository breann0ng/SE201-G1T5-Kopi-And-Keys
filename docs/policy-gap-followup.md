# Policy answer follow-up — 9 November 2026

This follow-up starts at `3ae6558` (PR #28) on the separate
`fix/policy-answer-coverage` branch. PR #28 is left unchanged for team review.
This is development evidence, not final accuracy or eligibility certification.

## Reproduced failures and changes

Two fictional single-profile requests (`Resale eligibility` and `What resale
eligibility conditions apply to my sidebar profile?`) abstained on the baseline.
The model prefixed its excerpts with table column names; the resulting string
was not continuous source wording. The sidebar request additionally received
zero lexical relevance because UI-profile wording was treated as policy content.

The table resolver now accepts a prefixed excerpt only when the prefix matches
that source's column and the remaining words identify a unique source cell. It
then restores the complete original cell, including qualifications omitted by
the model. Changed words, invented or wrong column names, empty excerpts and
ambiguous matches still fail. Normal source, scope and number checks still run.

Relevance focus removes narrow references such as `based on my sidebar profile`
and `apply to my sidebar profile`. Actual policy aspects remain: an employment
question still rejects a citizenship-only quote. The 0.20 threshold is unchanged.
Explicit `my sidebar profile` wording also reaches the existing personal-profile
scope guard.

User testing confirmed that the sidebar alerts and local change notices work.
It also exposed an answer-context gap: changing subsidy history left the same
general EHG/PHG excerpts without explaining the changed profile. Profile notes
now include first-timer, second-timer or mixed household status. For a general EHG
answer with a second-timer sidebar, the note explicitly says the excerpts do not
assess that household and explains the mixed-household selector. General source
information may remain the same; this does not produce a personal grant decision.
Direct personal second-timer EHG requests retain the existing scope refusal.

## Verification and limits

See [dated evidence](benchmarks/2026-11-09-policy-quote-context.json) for the final
test counts and before/after outcomes. Local reports retain fictional profiles,
drafts and verifier errors with tracing disabled. No held-out file was read.

Both reproduced refusals passed verification after the change. The EHG/PHG
combination positive control continued to pass. This is not proof that a broad
eligibility answer covers every condition: the retrieved tables can have missing
cohort context or blank cells, which must not be treated as permission to infer a
rule. Retrieval/chunk scope and independent semantic review remain team work.

The 12-case fixed-evidence development synthesis check has the same automatic
quote-coverage result before and after: 11/12. SYN-08 remains a mismatch: its
family-loan question's gold groups also require extended-family and singles
wording. A teammate should review that rubric against the question and sources;
the labels were not changed to improve the score. Missing-evidence and irrelevant
evidence controls still abstain. This small check is neither held-out evaluation
nor a controlled latency comparison.

Policy snapshots, ACTIVE, index contents, SQL data, model prompts and verifier
thresholds are unchanged. Public hosting, privacy/retention, repository protection,
watcher hosted runs and final frozen evaluation remain in the
[readiness checklist](finals-readiness.md).

## Browser checks after loading this follow-up

Use fictional details and start a new chat for each independent scenario.

1. Select Single Singapore Citizen + Couple/family: expect an amber warning and
   local profile notice. Change household type to Single: expect the warning to
   disappear. The user reported this working on PR #28.
2. Select a consistent household and First-timer; ask `Can EHG and PHG be combined
   for a resale flat?`. Change only subsidy history to Second-timer and repeat.
   Expect different profile notes and an explicit second-timer scope limitation,
   even if the general conditional source excerpt is unchanged. No approval or
   personal entitlement should be promised.
3. Select Single Singapore Citizen + Single, leave age blank, and ask `What resale
   eligibility conditions apply to my sidebar profile?`. Expect source conditions
   and an age-not-supplied note, not confirmation that the buyer qualifies. Check
   cited column scope and omitted conditions, not just the answered status.
4. Start an answer, Stop, edit/resend, then switch chats during generation. Replies
   should remain in their own chat. This browser interaction is still unreported;
   runtime regression tests alone do not establish visual correctness.

## Short grant-combination wording follow-up

The user then tested `Can EHG and PHG be combined?` as Single Singapore Citizen +
Single, first as First-timer and then Second-timer, with age/income blank. Both
attempts refused. This was a valid test, distinct from the earlier wording that
explicitly mentioned a resale flat.

The exact profile replay retrieved the relevant singles passage. The model split
the prerequisite and its adjacent PHG sentence into separate claims, so neither
excerpt contained the complete relationship the verifier requires. Synthesis now
restores the selected sentences as one continuous original excerpt only when all
selections uniquely match one source, have only whitespace between them and
explicitly connect the requested grants. Original source order and every selected
word are retained. Opposite household scope is checked before joining. Distinct
sources, gaps containing omitted conditions, repeated/altered text and adjacent
descriptions without a connection remain unjoined. Explicit missing evidence
still blocks the answer. This does not weaken the verifier's relationship rule.

Afterwards both actual localhost API requests answered with one cited source;
the second-timer response retained the explicit profile limitation. First-timer
family and mixed-family general-information controls also passed. See the
[connected-quote evidence](benchmarks/2026-11-09-connected-grants.json): 909 backend
tests and 20/20 curated mutations pass, and the fixed-evidence check remains 11/12
with the same SYN-08 mismatch. No additional age/income input was needed for these
general-information questions. Personal eligibility and broader completeness are
still separate checks.

## Distinct eligibility criteria and loan subject scope

A later browser replay passed the price filter-memory and Copy-with-sources
checks, but reproduced a sidebar eligibility refusal with a second-timer profile.
The model explicitly reported missing conditions. Context sampling had removed
different table chunks because they shared the same section heading. The source
was present in retrieval but absent from the model's evidence budget.

Sampling now prioritises chunks that add table criteria under the same heading.
Same-criterion variants are deferred, then retained if budget remains; equal
criterion names are not treated as proof of equal conditions. Exact duplicate
text is omitted. The existing passage/word limits remain. This is synthesis
context selection, not a change to the retrieval ranker, chunks or vectors.

The broad loan follow-up also selected an EC-purchase restriction from a genuine
loan source. A new scope check rejects that unrequested financing subject and
allows the existing verifier salvage to retain the relevant loan-options quote.
Explicit EC questions still accept relevant EC evidence, and EC mentions in past
subsidy lists are not caught by this restriction. Personal single-profile answers
also reject a selected rule requiring another co-applicant, unless the question
explicitly asks about that scenario. No policy boundary values are added by code.

The profile replay now answers with and without the preceding personal EHG scope
refusal. A first-timer control also answers after the contradictory co-applicant
quote is removed. The loan replay retains the cited HDB/FI options sentence
without the EC restriction. These are selected source conditions, not a complete
eligibility checklist or a full loan comparison. Cohort metadata, blank source
cells and independent semantic completeness remain review tasks.

See the [dated criteria/scope evidence](benchmarks/2026-11-09-policy-criteria-scope.json)
for final validation. The user has not yet reported Stop/Edit/chat-switch results.
