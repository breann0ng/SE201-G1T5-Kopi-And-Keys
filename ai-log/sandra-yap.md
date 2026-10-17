# AI Use Log: Sandra Yap

## 2026-10-15 · Scrape official HDB/CPF pages into a policy snapshot
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** scripts/scraping/*, data/policy_snapshots/2026-10-15/, data/policy_chunks/,
  data/schema/vocab.json
- **Outcome:** Changed

### What I asked for
A polite scraper for HDB and CPF pages (robots.txt, rate limit, cache, log), then
clean text, chunks with stable IDs, and a validation script.

### How I checked it
Agreed the scope (88 pages, 6 PDFs) and source ranking myself. Spot-checked
cleaned pages against the live sites. validate.py passes all checks, and raw
files match their checksums.

### What I kept or changed
I approved a browser-like User-Agent for hdb.gov.sg after HTTP 403s, and raised
the fetch cap from 30 to 200. Kept the rest.

## 2026-10-16 · Topic cards, React UI and PR #3
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** data/topic_cards/, backend/kopi_keys/topic_cards.py, frontend/,
  data/evaluation/, tests/test_topic_cards.py and others
- **Outcome:** Changed

### What I asked for
12 rule-based topic cards, a React chat UI with sources and a profile sidebar,
and a merge of my branch with PRs #1 and #2.

### How I checked it
Ran the UI against the backend and read each card against its HDB page. Fixed
the review findings on PR #3 (byte-exact raw files, stable chunk IDs, held-out
questions moved out of the repo). All tests passed before merging.

### What I kept or changed
Kept Breann's graph and added a thin adapter for the real cards rather than
changing her loader.

## 2026-10-16 · Verify income ceilings against HDB
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** backend/kopi_keys/rules/income_ceilings.json
- **Outcome:** Changed

### What I asked for
Check the grant income ceilings, which cited a property blog.

### How I checked it
Compared each figure with HDB's own page in our snapshot. Four matched current
HDB values; the blog had older ones.

### What I kept or changed
Switched the sources to HDB and updated the values. Left PHG unverified because
no HDB page in the snapshot states its income rule.

## 2026-10-17 · Hybrid retrieval and evaluation harness
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** components/policy_retrieval.py, policy_index.py,
  scripts/build_policy_index.py, backend/kopi_keys/evaluation/*,
  data/evaluation/development/
- **Outcome:** Kept

### What I asked for
Better retrieval than keywords alone, one combined 30-question dev set, and a
harness that scores the real app.

### How I checked it
Recall@5 rose from 35% (old keyword ranker) to 60%. Every dev-set evidence quote
resolves word for word to a chunk. Ran the full evaluation end to end.

### What I kept or changed
Kept the hybrid ranker. Recall is still below the 85% target, noted as open work.

## 2026-10-17 · Show more of the official source in answers
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** frontend/src/components/*, frontend/src/lib/sourceContent.ts,
  scripts/scraping/build_cards.py, validate.py, data/topic_cards/*.json
- **Outcome:** Changed

### What I asked for
Tables, charts and overviews in answers, using shadcn components.

### How I checked it
Tested in the browser: full source tables, the EHG band chart, overview table,
related passages. Overview quotes are checked verbatim by validate.py.

### What I kept or changed
Chose the order (tables, overview, charts, related passages). Asked for related
passages to render as proper tables, and for "(PDF, 198KB)" labels to be hidden.

## 2026-10-17 · Connect topic cards; clarifying questions only when needed
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** components/topic_cards.py, graph.py, schemas.py, state.py,
  synthesiser.py, tests/test_discovery_connections.py, test_overview.py
- **Outcome:** Changed

### What I asked for
Use the cards for suggestions and income notes, and stop asking clarifying
questions that the sidebar already covers.

### How I checked it
Asked broad, discovery and grant questions in the browser and read each reply.
New tests cover hints, suggestions and income notes.

### What I kept or changed
I chose option (ii): discovery questions are answered with a sidebar hint, never
a clarifying question. Restricted income notes to grant questions after one
appeared on an HFE question.

## 2026-10-17 · Fix wrongly declined and unsafe answers
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** query_router.py, state.py, verifier.py, graph.py,
  policy_retrieval.py, tests/test_router_dates.py, test_graph.py
- **Outcome:** Kept

### What I asked for
Why my EHG question ("22, 5000" as the reply) was declined, and why a 2012 price
question got recent prices.

### How I checked it
Replayed my own conversation until it answered with a cited quote. The fixes:
dates read from the question, several values in one reply, PDF hyphenation,
quotes ending in ":" rejected, verified quotes kept when another fails, HDB
worked examples ranked below rules. Evaluation over four runs: unsafe answers
25% to 0%, over-abstention 15% to 8% (target 10%).

### What I kept or changed
Kept all fixes. Nothing unverified is shown; the app still declines when no
quote passes.

## 2026-10-17 · Speed up answers
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** policy_synthesis.py, llm.py, main.py, .env.example,
  frontend/src/components/Progress.tsx, lib/adapter.ts, lib/api.ts
- **Outcome:** Changed

### What I asked for
Faster answers, and something to show while waiting.

### How I checked it
Timed 8 dev questions per setting, plugged in. The median fell from about 103 s
to 37 s with 8/8 still verified; 2 passages was faster but lost 3 answers. A
repeated question returns in 0 s. Watched the progress steps in the browser.

### What I kept or changed
Chose 8 threads and 3 passages / 800 words. Added live progress, a warm model and
an answer cache rather than switching to a hosted model.

## 2026-10-17 · Income ceiling variants and recent chats
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** rules/income_ceilings.json, rules/income.py,
  tests/test_income_conditions.py, frontend/src/lib/history.ts, Layout.tsx
- **Outcome:** Kept

### What I asked for
Apply Tasha's open checks myself, and keep past conversations.

### How I checked it
Every ceiling condition is tested word for word against HDB's page. Reopened and
deleted chats in the browser.

### What I kept or changed
Showed HDB's variants (e.g. $24,000 for extended families) rather than guessing
which applies. Values and verified flags unchanged.

## 2026-10-17 · Documentation and project guide
- **Tool (model):** Claude Code (Claude Opus 5.5)
- **Files:** data/README.md, backend/kopi_keys/evaluation/README.md,
  frontend/README.md, the team project guide
- **Outcome:** Changed

### What I asked for
A top-down data README, a change log of edits to teammates' files, and a project
guide for the whole team.

### How I checked it
Checked the PR history against git. Corrected PR #4's author (Tasha, not Breann).

### What I kept or changed
Dropped the status column, used names instead of "Person N" labels, and removed
names from change notes in code. Kept owners and decisions named.
