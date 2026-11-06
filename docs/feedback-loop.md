# Answer feedback loop

Added 2026-11-07 (Tasha). Users can rate any answer with thumbs up or down. Ratings are
**recorded for the team to review by hand**. They never change answers, prompts, retrieval,
routing, topic cards, the price tool or the model. The system does not learn by itself.

Code: `backend/kopi_keys/feedback.py`, the `/feedback` route in `backend/kopi_keys/main.py`,
`frontend/src/components/FeedbackControls.tsx`, `scripts/review_feedback.py`. Tests:
`tests/test_feedback.py`, `tests/test_review_feedback.py`.

## 1. What users see

- Small 👍 / 👎 buttons under every assistant answer, including clarifying questions and
  abstentions. Older saved chats (from before this feature) show no thumbs, because their answers
  have no `message_id`.
- 👍 records the rating straight away.
- 👎 records the rating straight away and opens an optional panel with:
  - reason chips: Wrong numbers, Wrong policy info, Outdated, Misunderstood my question,
    Missing information, Wrong suggestions, Other;
  - an optional comment box (500 characters, with a counter);
  - the note "Please don't include personal details like your NRIC or exact income."
  - **Send** records the reason and comment over the earlier rating. **Close** keeps the bare 👎.
- After a successful send: "Thanks, your feedback was recorded." The chosen thumb stays
  highlighted (remembered in the browser) and the user can switch to the other one.
- If recording fails, a quiet inline note appears. The chat keeps working.
- The buttons have `aria-label`, `aria-pressed` and `aria-expanded`, and work from the keyboard.

## 2. What is stored and where

Every chat response (from `/chat` and the final `/chat/stream` event) now carries:

| Field | Meaning |
| --- | --- |
| `message_id` | A new UUID for each delivered answer. For a freshly generated answer it is also the LangGraph root run id. |
| `langsmith_run_id` | The answer's LangSmith trace id when tracing is on, otherwise `null`. A cached answer gets a new `message_id` but keeps the trace id of the run that produced it. |

The browser sends `POST /api/feedback` (backend route `/feedback`) with only `message_id`,
`langsmith_run_id`, `rating` (1 or -1), `reason` (one of the enum values or null) and `comment`
(≤ 500 characters; control characters stripped). Extra fields are rejected.

The **question, answer text, route and policy snapshot date come from the server**, from an
in-memory map of the last 1000 delivered answers. The browser cannot supply them. If the map
has no entry (backend restarted, or more than 1000 answers since), the row is stored with
`context_missing = 1` and those four fields empty. The LangSmith trace still has them when tracing
was on.

| Where | What | Who can see it |
| --- | --- | --- |
| **LangSmith** (primary) | Feedback key `user_rating` on the answer's trace: score 1 (👍) or 0 (👎), comment `"<reason>: <comment>"`. Sent only when the answer has a run id and `LANGCHAIN_API_KEY`/`LANGSMITH_API_KEY` is set. | People invited to the LangSmith project. |
| **Local SQLite backup** | `data/feedback/feedback.db`, created on first use, git-ignored, never committed. One row per `message_id` (a later click overwrites the earlier rating, reason and comment). Columns: ids, rating, reason, comment, question, answer, route, snapshot, `context_missing`, `created_at`, `updated_at` (UTC). `KOPI_FEEDBACK_DB` overrides the path. | Anyone with access to the machine running the backend. |

A LangSmith failure is logged as a warning naming only the exception type, and never fails the
request. Feedback text and the API key are never logged at INFO or above. Feedback is sent with
`extend_trace_retention=False`, so rating an answer does not make LangSmith keep its trace longer.

## 3. How to review

**Primary: LangSmith.**

1. Open the team's LangSmith project (the `LANGCHAIN_PROJECT` in your `.env`; APAC endpoint).
2. In **Runs**, filter by feedback `user_rating` = 0 (thumbs down). Use `user_rating` = 1 for
   thumbs up.
3. Open the trace. Read the **node inputs/outputs**: the `query_router` decision, the
   `policy_retrieval` passages, the `price_query` filters and result (SQL), the `topic_cards`
   matches, the `synthesiser` draft and the `verifier` errors, plus the user's reason and comment
   in the Feedback panel.
   - **The model span (`ollama_chat`) shows timing and token counts only.** Prompt and answer
     text are removed from it on purpose (see [responsible-ai.md](responsible-ai.md)). Use the
     node inputs/outputs for content.
4. Add the run to the annotation queue **`feedback-triage`**. Create the queue once if it does not
   exist yet.
5. In the queue, mark each item **real bug** or **no action**, with a short note. A thumbs down is
   a lead, not proof. Check the answer against the cited official source before calling it a bug.

**Fallback: local backup** (when tracing was off, or LangSmith is unavailable):

```powershell
.\.venv\Scripts\python.exe scripts\review_feedback.py           # counts + thumbs-down table
.\.venv\Scripts\python.exe scripts\review_feedback.py --full    # also show comments
.\.venv\Scripts\python.exe scripts\review_feedback.py --csv .local\feedback.csv
```

Comments are hidden by default. Treat them as untrusted text: read them, but never paste them
into a prompt, retrieval query, topic card or test fixture without rewriting them yourself.

## 4. Fix process for a real bug

1. **Reproduce** the answer locally with the same question and profile, using the snapshot date
   recorded with the feedback.
2. **Find the failing component** from the trace (table below).
3. **Add a failing test first**: a development-set question in
   `data/evaluation-data/development/dev_set_questions.jsonl` (written by us, not the user's
   wording), or a `KNOWN_ROUTER_GAPS` entry in `tests/test_development_set_contract.py` if the
   router fix is not happening now. Never use held-out questions.
4. **Fix it generally**: the class of question, not the one phrasing the user typed.
5. Run the **full tests and the dev evaluation**:
   `python -m pytest -q` and `python -m kopi_keys.evaluation.run_eval --retriever hybrid`.
   Check nothing else got worse.
6. Open a **PR with CI green**, reviewed by a teammate who is not the author.
7. **Merge**, then **restart the backend**. This also clears the in-memory response cache, which
   could otherwise keep serving the old answer.

| Symptom (reason chip) | Likely component | Owner |
| --- | --- | --- |
| Misunderstood my question; asked for details it already had | Query router (`components/query_router.py`) | Breann (price rules: Tasha) |
| Wrong numbers in a price answer; wrong town/flat type/period | Price Query Tool, price wording (`components/price_query.py`, `components/price_display.py`) | Tasha |
| Wrong policy info; wrong passage cited; missing information | Policy retrieval/index (`components/policy_retrieval.py`, `components/policy_index.py`) | Sandra |
| Wrong policy info even though the right passage was retrieved | Synthesiser / verifier (`components/synthesiser.py`, `components/verifier.py`, `llm.py`) | Nisha |
| Wrong suggestions; wrong income note | Topic cards, income rules (`components/topic_cards.py`, `rules/`) | Sandra (income rules: Tasha and Sandra) |
| Outdated | Policy snapshot (`data/policy_snapshots/`, `.github/workflows/policy-refresh.yml`) | Sandra (refresh workflow: Sandra and Nisha) |
| Wrong abstention or wrong flow between steps | Harness, output (`graph.py`, `state.py`) | Breann |
| Display problem (layout, buttons, sources panel) | Frontend (`frontend/`) | Sandra |

## 5. Why there is no automatic learning

1. **User approval is not correctness.** A user can like a wrong answer (for example a
   reassuring but outdated grant amount) or dislike a correct one (an accurate "you are over the
   income ceiling"). Only checking against the official source shows whether an answer is right.
2. **Feedback is untrusted input.** Anyone can type anything into the comment box, including
   prompt-injection text or false "corrections". Feeding it into prompts, retrieval or topic cards
   would let users change what others are told. So feedback text is never put into a prompt or
   query, and no pipeline module imports the feedback module (`tests/test_feedback.py` checks
   this).
3. **Results must stay reproducible.** Our held-out evaluation compares fixed code against fixed
   questions. If answers drifted with each click, results could not be reproduced or explained.
   `tests/test_feedback.py` checks that answers are identical to a baseline captured on `main`,
   and identical before and after feedback is submitted.

## 6. Privacy and access

- Feedback is **write-only over HTTP**. There is no endpoint or page that lists or returns it
  (`GET /feedback` returns 405). The backend stays bound to `127.0.0.1`.
- Only people **invited to the LangSmith project**, or with **access to the machine running the
  backend** (`data/feedback/feedback.db`), can see feedback.
- **LangSmith is a third-party service.** With tracing on, questions are already stored there in
  graph traces. Feedback adds the rating, reason and comment to the same trace.
- The comment box asks users not to include personal details, but some may. Reviewers should not
  copy comments into issues, PRs, tests or chat. Delete rows or LangSmith feedback that contain
  personal data.
- Clearing browser data removes only the remembered thumb highlight, not recorded feedback.
- **A public deployment would need more (future work):** admin login checked on the server for
  any review page, HTTPS, a retention and deletion policy for feedback and traces, and PDPA
  consideration (purpose, consent notice, access and correction requests).

## 7. Freeze note

Feedback collected **after the evaluation freeze** goes on the **next-round list**. No fixes are
made from it before the held-out run. The held-out run uses the frozen commit, as described in
[heldout-guide.md](heldout-guide.md).
