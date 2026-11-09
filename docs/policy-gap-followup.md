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
