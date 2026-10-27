# Policy advisor and conversation handling

The API uses the ACTIVE official policy snapshot and local CPU Ollama. The model
remains `qwen2.5:3b`. The finals synthesis benchmark can compare it with larger
local models. The resale price formatter and its numeric verifier retain their
existing prompt and inference limits.

## What happens for a policy question

1. The rule-based router recognises housing loans, mortgages, financing and
   questions such as “Can a Singapore PR couple buy a resale flat?”. General
   questions about HDB ask which topic the user wants.
2. Retrieval is hybrid (updated 2026-10-17, replacing this PR's keyword-only
   ranker): a keyword ranker that removes filler, folds plurals, expands
   abbreviations (PR, EHG, HFE, OTP), weights official pages above explainers
   and removes duplicate text, fused with EmbeddingGemma vectors in ChromaDB.
   Build the index once with `scripts/build_policy_index.py`; without it the
   keyword ranker serves alone. See `components/policy_retrieval.py`.
3. Personal EHG and loan-eligibility requests use the relevant topic card's
   `required_fields`. Missing details produce a clarification before inference.
   Household type is available in the profile sidebar. Having those details does
   not establish complete eligibility or replace an HFE assessment.
4. General PR-couple purchase questions use the retrieved citizenship table's
   Standard/unclassified and Plus/Prime columns directly, with separate citations
   and scopes. The app explains these published conditions; it does not issue a
   personal eligibility decision. Other policy questions send up to three complete
   passages (at most 800 source words by default) to Ollama. Well-formed tables are passed as
   explicit row/column/cell objects. It requests structured JSON selecting at most
   three short, self-contained source quotes with citations for ordinary questions.
   Questions naming multiple grants can use five passages / 1,200 words and six
   claims, with explicit grant coverage and prerequisite instructions. Each request's
   JSON schema enumerates only its supplied citation IDs. Free-form model
   paraphrases are never displayed as policy facts. Its context is
   4,096 tokens and output limit is 850 tokens; CPU-only inference is retained.
5. Deterministic checks reject unknown/superseded citations, invented supporting
   quotes and numbers absent from the supporting quote. A selected table cell is
   rendered from the source together with its row condition and column scope,
   instead of using a potentially misleading model paraphrase. A PR resale answer
   must cover both relevant citizenship columns. Finals checks also score quote
   relevance, reject clearly opposite household scopes, and require the requested
   grants, a supported combination/exclusion rule, and supplied resale prerequisites.
   A failed draft gets one
   repair attempt. A second failure or model-engine error abstains.

Source wording and the relevance heuristic do not establish full relevance or
completeness. A model can still select an incomplete excerpt, and a
malformed source table may have lost context during scraping. Review household
scope and answer relevance separately. The corpus itself also needs review;
these changes do not rewrite or certify scraped policy text.

## Follow-up context

`POST /chat` accepts up to 12 recent `history` turns with `role` (`user` or
`assistant`) and `content`. Each content is bounded to 12,000 characters. The
frontend sends the most recent 12 turns by default; `VITE_SEND_HISTORY=false`
disables that feature. History stays client-owned: requests do not share server
state, and assistant replies never become policy evidence.

The backend can resume a clarification using replies such as “Yishun, 4-room”,
an age, household income, or a household type. A hypothetical question about a
PR couple is not saved as the user's own citizenship/household profile. This is
bounded clarification handling, not unrestricted conversational reasoning.

## Provenance and testing

The default API reports `mode: "snapshot"`; injected demo graphs still report
`demo`. The frontend consequently does not label official snapshot answers as
fictional. Saved messages retain their original metadata; start a new chat to
see the new behaviour consistently.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q tests\test_policy_advisor.py
```

Live examples to try after starting Ollama, the backend and the frontend:

- `Can a Singapore PR couple buy a resale flat?`
- `may i know about loans`
- `Am I eligible for the Enhanced CPF Housing Grant?` (asks for missing details)
- `i want to know about HDB` (asks for a topic)
- `What is the resale price?`, followed by `Yishun, 4-room`

Policy excerpt selection uses real inference and can take much longer than the former
copied-passage output. Record latency and verifier repairs when comparing models.

Routing support is not a guarantee of a verified answer. In the live review on
18 October 2026, `how do I buy a resale flat?` abstained on two runs after both
allowed generation attempts. A raw-response diagnostic found that the model
cited `CHUNK_RESALE_26` instead of the supplied `CHUNK_BTO_26`. The answer-level
allowlist rejected the entire draft. The finals changes now restrict IDs during
decoding and pass the actual JSON validation error into the repair prompt.
This fixes the error-feedback gap; it does not guarantee every buying-guide
question will be answered. Automated routing tests do not establish end-to-end success.

## Model comparison and optional policy model

Qwen3:4b was downloaded and compared locally on the PR table question. Both 3B
and 4B misinterpreted the columns; 4B was slower and its drafts were rejected by
the verifier. This single diagnostic case is not a general model benchmark.
The default remains Qwen2.5:3b. Critical citizenship-table facts use the deterministic path
above rather than relying on either model to interpret columns.

For the repeatable finals benchmark and guardrail details, see
[Nisha's finals implementation](finals-nisha.md). This benchmark isolates synthesis
with fixed evidence; it does not measure the retriever or use held-out questions.

To experiment with a separate policy model, without changing the price model:

```powershell
.\scripts\setup_ollama.ps1 -Model qwen3:4b
```

Then set `KOPI_POLICY_MODEL=qwen3:4b` in your local `.env` and restart the backend.
Qwen3 thinking is disabled by the wrapper for these short grounded answers.
Leave that variable unset to use the existing model. The downloaded Qwen3 model
can remain installed without changing the application's default.

Production retrieval is scored on the committed dev set with:

```powershell
.\.venv\Scripts\python.exe -m kopi_keys.evaluation.run_eval --retriever hybrid
```

On the combined 30-question dev set (2026-10-17) Recall@5 is 60% (12/20) for the
hybrid retriever and 45% for the keyword ranker alone (this PR's original keyword
ranker scored 35% on the same set). This is development evidence, below the 85%
target, not a held-out result. See `backend/kopi_keys/evaluation/README.md`.
