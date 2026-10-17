# Kopi & Keys — frontend

React 19, Vite, Tailwind CSS v4 and [assistant-ui](https://github.com/assistant-ui/assistant-ui).
There is no login: the buyer profile, feedback and theme are stored only in the browser.

## Run (development)

You need two terminals.

```powershell
# 1. Backend, from the repo root
.\.venv\Scripts\python.exe -m uvicorn kopi_keys.main:app --port 8000 --app-dir backend

# 2. Frontend
cd frontend
npm install
npm run dev        # http://localhost:5173
```

Vite proxies `/api/*` to the backend on `:8000`, so the backend needs no CORS change in
development. Production hosting is not set up yet.

## Pages

| Route | What |
|---|---|
| `/` | **Chat** (core). The sidebar profile (citizenship, age, income, first-timer) is sent with every question as `BuyerProfile` |
| `/sources` | Sources and methodology: the ACTIVE snapshot date and every captured page, grouped by source tier |
| `/settings` | Theme (system, light or dark) and "Clear my data" |

## How chat maps to the API

- `src/lib/adapter.ts` sends the latest message plus the profile to `POST /chat`.
- **Conversation memory (frontend half, built):**
  - **History:** each request carries the last 12 turns as `{role, content}`, oldest first.
    The backend accepts these as clarification context, never as policy evidence.
    Set `VITE_SEND_HISTORY=false` in `frontend/.env.local` to disable sending history.
  - **Saved chat:** the conversation is saved in this browser (`kk:chat`, last 60 messages), so it
    survives a reload. **New chat** and Settings → **Clear my data** wipe it.
- **Quick replies:** when a clarifying reply includes `asking_for` (e.g. `"citizenship"`), buttons
  appear under it. Tapping one fills in the sidebar profile and sends the answer as a message.
  The backend returns `asking_for` for profile clarifications. Household type is also
  available in the sidebar.

### Backend conversation contract
```python
class HistoryTurn(Contract):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=12000)

class ChatRequest(Contract):
    ...
    history: list[HistoryTurn] = Field(default_factory=list, max_length=12)

class ChatResponse(Contract):
    ...
    asking_for: Literal["citizenship", "age", "household_income", "first_timer", "household_type"] | None = None
```
History is context for the Advisor, **not evidence**. Policy claims must still cite passages retrieved
for the current answer, and the verifier should keep enforcing that.
- The response is attached to the message as `metadata.custom` and rendered by `Thread.tsx` and `AnswerExtras.tsx`:
  - `status`: *answered* shows a normal reply; *clarifying* shows an amber "need more information" style;
    *abstained* shows a grey "can't answer reliably" style with a link to HDB.
  - `citations`: a numbered source list with "Verified on official site <verified_on>", the page's own
    "last updated" line, and an effective date only when one is stated.
  - `price_result`: a lowest / median / highest card.
  It shows `volume` transactions; prices arrive as Decimal strings and are formatted as SGD.
- `src/lib/api.ts` mirrors `backend/kopi_keys/schemas.py`. Update it when the contract changes.
  It was last synced in the merge of `main` on 2026-10-16:
  - `PriceResult` now has `volume` (was `count`) and gains `mean` and `iqr`;
  - `ChatResponse` gains `route` and `suggestions`.

  `suggestions` is typed but not shown in the UI yet.
- Citizenship options come from `data/schema/vocab.json` (DRAFT).

## Source material under answers

Everything below is shown exactly as captured from the official pages; nothing is written by the AI.

- **Overview table** (`components/Overview.tsx`): for broad questions ("What grants are there?") the
  backend returns `overview`, one row per scheme with its verbatim official sentence and source number.
- **Full source tables** (`components/SourceMaterial.tsx`): any table in a cited passage, collapsed
  under "Show full table from source [n]". Tables missing the `|---|` line are still recognised.
- **Grant-band charts:** HDB's EHG amount-by-income tables become a bar chart; the user's income band
  is highlighted when the sidebar has an income, with a reminder that only the HFE letter confirms it.
- **Related official passages:** retrieved passages the answer didn't quote (`related`), collapsed.
- **Income ceilings:** for grant questions with an income in the sidebar, a highlighted note compares it with each
  grant's HDB-verified ceiling (`income_notes`), linking to HDB; it never says the user qualifies.
- **Suggestions:** matched topic cards appear in the answer text as "You may also want to look into", with sources.

Adding more shadcn components: `npx shadcn add` produces classes using shadcn's own colour tokens
(`bg-background`, `text-muted-foreground`, ...), which `index.css` does not define. Swap them for the palette
classes used in `src/components/ui/` (slate, brand, coral), as was done for Collapsible, Table and Chart.

UI components come from [shadcn/ui](https://ui.shadcn.com) (Collapsible, Table, Chart), copied into
`src/components/ui/` and recoloured with the brand palette; charts use Recharts. Parsing lives in
`src/lib/sourceContent.ts`.

## Scaffolded, not finished

- **Feedback:** 👍/👎 is saved in the browser only. It is meant to feed the evaluation dataset later.
- **Sources page:** reads `data/policy_snapshots/` at build time. The backend's retriever now serves the
  snapshot's chunks, so this could move to an API endpoint.
- **Later:** saved conversations, language options and more profile fields (see `data/topic_cards/README.md`).

## Recent chats (added 2026-10-17)

`src/lib/history.ts` now keeps up to 20 conversations in this browser (`kk:chats`, 60 messages each) instead of one. They are listed under **Recent chats** in the sidebar, where you can reopen or delete them; **New chat** starts a fresh one and keeps the old one in the list. A chat saved by the earlier single-chat version (`kk:chat`) is moved into the list automatically. Only the open chat's last 12 turns go to the backend, as before. Nothing is stored on the server.

## Progress while answering (added 2026-10-17)

The chat calls `POST /api/chat/stream` (`streamChat` in `src/lib/api.ts`). The backend sends one JSON line per finished graph step, then the answer. `src/components/Progress.tsx` ticks each finished step, names the current one, and counts seconds. Nothing is simulated: a step appears only when the backend reports it. Against an older backend without the endpoint, the chat falls back to `POST /api/chat`.
