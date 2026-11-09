# Chat editing, stopping and copying

Branch: `fix/chat-edit-copy-and-responsiveness`, 6 November 2026. This follows
the safety-evaluation branch and includes that work if it has not merged yet.

## User-facing behaviour

- Existing saved conversations and New chat are preserved. Sandra's
  `1fa9f84` introduced recent chats; this change does not clear or migrate them.
- When an answer is running, **Stop** cancels the browser request. The streaming
  endpoint marks that request cancelled and closes its internal Ollama HTTP
  operation, including during prefill. The runtime determines how quickly its
  underlying compute stops. Interrupted drafts are not cached or displayed.
- After stopping, **Edit** appears below user messages. It opens a prefilled
  composer with **Cancel edit** and **Save and send**. Resending uses the edited
  conversation branch and current sidebar profile, not later turns from the old
  branch. The view explains when a response was stopped.
- **Copy answer and sources** copies the main answer, overview/income notes when
  present, numbered citations, source URLs and source dates. A synthetic-evidence
  warning is retained. Collapsed related passages and execution traces are not
  presented as sources used in the answer.
- The loading text no longer promises an answer within a minute on a CPU.

Updating code does not rewrite old saved answers. Edit/resend a question or start
a new chat to obtain a new result. For profile testing, change **Your situation**
controls; "Change the profile values" in the test guide was an action instruction.
Chat history and profile persistence have not been changed here.

## Grant-combination responsiveness

For a narrow stacking question, the synthesiser can use one complete retrieved
passage if it states the requested relationship, includes a supplied EHG
prerequisite when present, and does not conflict with household scope. Source
text is never cut or rewritten. Questions asking about amounts, eligibility
details, income, employment, lease/proximity conditions or new flats retain the
broader context. The same verifier and single repair still apply.

This is source selection, not a hard-coded grant answer. It cannot supply missing
rules or establish personal eligibility. Tests cover narrow and qualified queries.

## Verification

- Backend: 440 tests passed, four existing expected router failures.
- Frontend: five clipboard-format tests passed, lint passed with existing
  fast-refresh warnings, and production build passed with the existing bundle warning.
- Cancellation tests cover no headers/prefill, a partial stream, total timeout,
  reconstruction of a complete draft, independent request events and cache safety.
- A fresh local HTTP request for the user's multiline EHG/PHG phrasing answered
  and verified in 26.903 seconds with a fictional test profile and the real dated
  retriever. This is one observed request, not a controlled speedup benchmark.
- Closing a real HTTP stream after topic-card retrieval took 0.214 seconds; a
  subsequent deterministic policy request answered in 0.149 seconds. This is a
  transport/responsiveness check, not proof about all model workloads.
- Visual Stop/Edit/Copy testing was attempted, but the browser automation host
  was unavailable and native Edge app access timed out. Manual UI verification
  remains pending; successful builds/API checks are not a visual click-through.

Reproduce automated checks:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm test
npm run lint
npm run build
```

Manual check at `http://127.0.0.1:5173`:

1. Start a new test chat and ask an HDB grant question.
2. Press Stop while it is choosing quotes. Check the stopped explanation appears.
3. Press Edit under the user message, change the question to the PR-couple resale
   example and press Save and send. Check the displayed question and new answer.
4. Press Copy answer and sources and paste into a text editor. Verify that source
   numbers match the answer and each source has a URL and verification date.
5. Reopen an earlier saved chat and verify its previous messages remain available.

## Profile scope and source tables (7 November 2026)

The sidebar now distinguishes first-timer households, second-timer households and mixed
first-/second-timer couples. The legacy `first_timer` boolean remains supported, while
`subsidy_status` preserves the household distinction. Contradictory API status/boolean fields
are rejected. Sidebar updates apply to the next question immediately; old answers retain their
original profile context. Existing saved boolean choices are migrated to the labelled choices.

"Explain EHG conditions for a person like me" counts as a personal question. Missing profile
inputs are requested; contradictory single/family selections need correction. A second-timer
household asking for a personal EHG assessment is not answered with first-timer conditions or
amount tables. The app explains the scope limitation before retrieval/model execution and asks
users with a first-timer co-applicant to select the distinct mixed option. This is not a blanket
verdict about eligibility for other schemes. Legacy false-only profiles require clarification.

The verifier also checks explicit opening qualifications in PDF amount tables, since a page's
generic title can hide a non-resident-spouse or mixed-household restriction. First-timer grant
ceiling comparisons are suppressed for second-timer/mixed profiles. An explicit general
hypothetical about first-timer families remains possible without sending contradictory subsidy
status to the model. These are scope checks, not a complete eligibility rule engine.

Grant charts are generated by frontend code from source tables; the LLM selects cited source
excerpts for policy text. The chart no longer compares current sidebar income with past answers
or implies a personal award. Split PDF headers are read together, so a table stating **half of
average monthly household income** is labelled that way. Explicit specialised source scope is
shown. Amounts and range labels remain source values. Unknown income bases show a table only;
overlapping or multiple separate band blocks are not combined into one chart.

Complete source-band blocks quoted in an answer are reflowed into Markdown tables, including
when copied. Conditions surrounding the block and citation references remain. Partial, changed
or uncited number lists are not reconstructed. Saved answers with response metadata receive the
same display formatting on reopening; stored evidence and chat data are not rewritten. Source
tables and charts in the supporting-material section are collapsed by default. The app constrains
outer document overflow and gives the thread/sidebar their own bounded scrolling regions.

Additional manual checks (browser automation could not complete the visual check):

1. Set household citizenship to Two Singapore Citizens, household type Couple/family, and subsidy
   history to Second-timer household. Ask "Explain EHG conditions for a person like me". Expect a
   scope explanation, no grant amount table and no model delay. Changing the sidebar does not
   retroactively change an earlier answer; send/edit the question to assess the new profile.
2. Set Single Singapore Citizen with Extended family and repeat. Expect a request to correct the
   inconsistent household fields. Use matching fields for a real assessment question.
3. Open the earlier saved EHG answer containing a complete amount table. Check it has two columns
   with its correct income basis, and that copying retains all displayed amounts and source URLs.
4. Expand the source chart. Its bars describe the source table; no "your band" highlight or inferred
   grant award should appear. Changing sidebar income must not change the historical chart.
5. Scroll long chat content to both ends at normal and enlarged browser zoom. The composer should
   stay within the viewport with no outer document scroll into a large blank area. Confirm Sources
   and Settings still scroll within their page areas, including on a narrow window.

### New chat selection (9 November 2026)

An empty conversation is shown as a selected **New chat** row in Recent chats.
It is a draft, not another saved empty conversation: repeated clicks do not fill
history or remove earlier saved chats. Its first question supplies its title.
The browser tab follows the selected conversation title on Chat, and shows
Sources or Settings on those pages.

Switching conversations cancels the client request, clears the unsent composer
text and pauses history writes during runtime replacement. This prevents an
intermediate reset notification from copying the previous thread under the next
thread's ID. Clicking an already-selected conversation preserves its draft and
running request. Saved profile values remain separate and unchanged.

Switching away while generation is running intentionally cancels that client
request. The old saved chat may keep the user question without a reply because
running assistant drafts are not saved as completed answers. This is not a claim
that remote GPU execution stops immediately. Two regression tests use the actual
installed assistant-ui runtime with a stream that sends a late chunk after
cancellation: neither a new draft nor a reopened saved chat receives that chunk.

Manual check: open an existing chat, type an unsent draft, then click New chat.
Expect the welcome screen, an empty composer, selected New chat row and browser
title `New chat | Kopi & Keys`. Send a new question: only that conversation should
take the new title. Reopen the earlier conversation and confirm its messages and
title remain intact. Reload while the draft is empty; New chat should stay selected.
