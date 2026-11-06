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
