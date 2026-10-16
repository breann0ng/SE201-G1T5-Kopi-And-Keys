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
  - **History:** with `VITE_SEND_HISTORY=true` (in `frontend/.env.local`), each request also carries
    `history`: the last 6 turns as `{role, content}`, oldest first. It is **off by default**, because
    the current backend rejects unknown fields. Turn it on once `ChatRequest` has
    `history: list[HistoryTurn]` (see below).
  - **Saved chat:** the conversation is saved in this browser (`kk:chat`, last 60 messages), so it
    survives a reload. **New chat** and Settings → **Clear my data** wipe it.
- **Quick replies:** when a clarifying reply includes `asking_for` (e.g. `"citizenship"`), buttons
  appear under it. Tapping one fills in the sidebar profile and sends the answer as a message.
  `asking_for` is a **proposed** backend field, so nothing shows until it exists.

### Proposed backend contract (for the orchestration owner)
```python
class HistoryTurn(Contract):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)

class ChatRequest(Contract):
    ...
    history: list[HistoryTurn] = Field(default_factory=list, max_length=12)

class ChatResponse(Contract):
    ...
    asking_for: Literal["citizenship", "age", "household_income", "first_timer"] | None = None
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

## Scaffolded, not finished

- **Feedback:** 👍/👎 is saved in the browser only. It is meant to feed the evaluation dataset later.
- **Sources page:** reads `data/policy_snapshots/` at build time. Move it to an API endpoint once the
  retriever serves snapshots.
- **Later:** saved conversations, language options and more profile fields (see `data/topic_cards/README.md`).
