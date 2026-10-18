# Kopi & Keys — frontend

React 19, Vite, Tailwind CSS v4 and assistant-ui. There is no login. Profile,
conversations, feedback and theme preferences are saved in this browser.

## Run locally

Complete the [root setup](../README.md#first-time-setup) first: Python dependencies,
Ollama models, SQLite database, vector index and `npm ci`. Use Node.js 22 or newer.

Two terminals are needed while Ollama is running:

```powershell
# Terminal 1: repository root
.\.venv\Scripts\python.exe -m uvicorn kopi_keys.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

Use `.venv/bin/python` on macOS/Linux.

```sh
# Terminal 2
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open http://127.0.0.1:5173. Vite proxies `/api/*` to the backend on port 8000.
The backend is Python; there is no `backend/package.json`. Production hosting
is not configured; `npm run build` checks and builds frontend assets.

## Pages

| Route | Purpose |
| --- | --- |
| `/` | Chat, profile sidebar, recent conversations and price refinements. |
| `/sources` | ACTIVE policy snapshot and captured pages, read at build time. |
| `/settings` | Theme, developer details and clearing browser data. |

## Requests and responses

`src/lib/adapter.ts` sends the latest question, current profile, optional price
filters and recent history through `streamChat` in `src/lib/api.ts`.

- Primary endpoint: `POST /api/chat/stream`. The backend returns one JSON line per
  finished graph node and a final `response`. `Progress.tsx` displays completed
  steps and elapsed time. A missing stream endpoint falls back to `POST /api/chat`.
- Profile: `citizenship`, `age`, `household_income`, `first_timer` and
  `household_type`. Clarification buttons can also request `flat_type`.
- History: up to 12 previous user/assistant turns, each capped at 12,000
  characters. Set `VITE_SEND_HISTORY=false` in `frontend/.env.local` to disable it.
  History is clarification context, not policy evidence.
- Price refinements: town, flat type, dates and optional lease/floor bands are
  sent as `price_filters`. **Narrow it down** submits updated filters with
  **Update figures**; it does not produce an individual-flat valuation.
- `ChatResponse` includes status, mode, route, message, citations, price result,
  suggestions, trace and optional overview/income/progress-related UI fields.
  Keep `src/lib/api.ts` aligned with `backend/kopi_keys/schemas.py`.

The adapter numbers citations for display and attaches the backend response as
message metadata. `Thread.tsx` and `AnswerExtras.tsx` render it. Clarifications
and abstentions get status badges; `mode: "demo"` shows the fictional-evidence
footer. The real snapshot app reports `snapshot`.

## Saved conversations and privacy

`src/lib/history.ts` stores up to 20 conversations in `kk:chats`, each with up to
60 completed messages. **Recent chats** can reopen or delete them. **New chat**
keeps the old conversation and starts another. An older `kk:chat` conversation
is migrated automatically. Settings can clear local data.

Only the active conversation's last 12 turns are included in chat requests.
There is no server conversation database. The backend has an in-memory response
cache; optional LangSmith tracing can record requests and outputs when enabled.
Feedback buttons save locally and are not connected to an evaluation service.

## Sources and price displays

The UI uses source text and tool results, with display cleanup; it does not
generate new policy figures.

- Overview tables contain cited official sentences from topic cards.
- Source tables and EHG income-band charts are extracted from cited passages.
  The income highlight is a comparison with the published band, not eligibility.
- Related retrieved passages can be expanded separately from cited claims.
- Verified grant income-ceiling notes and cited suggestions are shown when
  applicable; suggestions are included in the answer text.
- Price cards show matching volume and the summary, with lease/floor breakdowns
  and recent sales. Fewer than five matching sales hide median summaries and
  list the transactions. The backend's verified text retains its numeric precision;
  some compact UI figures are rounded for display.
- Developer details expose route and graph trace when enabled.

An in-scope question can still abstain after verification failure; passing the
frontend build does not establish policy-answer relevance.

## UI components and checks

The UI uses copied shadcn-style Collapsible, Table and Chart components,
recoloured to the project's palette. Parsing is in `src/lib/sourceContent.ts`;
source Markdown is rendered by `MarkdownText.tsx`.

```sh
npm run build
npm run lint
```

As checked on 18 October 2026, build passes. Lint reports no errors and four
existing React Refresh warnings. The build reports a large-bundle warning.
Language options and a server-side feedback workflow are not implemented.
