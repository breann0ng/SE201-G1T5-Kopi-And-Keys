# Policy website watcher

Owner: Nisha (monitoring/review workflow), with Sandra reviewing extraction, chunks and cards.

The answer verifier checks a draft against retrieved evidence. This watcher checks whether the
stored evidence differs from official policy sources. Neither proves a person's eligibility.
The watcher needs no LLM, MCP server, Tavily subscription or GPU.

## Schedule and outcomes

`.github/workflows/policy-refresh.yml` runs each Monday at approximately **10:17 SGT**. A maintainer
can also select **Actions > Policy refresh > Run workflow** on the default branch. GitHub schedules
can be delayed; this is periodic polling, not real-time notification from HDB. Coverage is limited
to the configured HDB/CPF/MyNiceHome sources and discovered in-scope pages/PDFs.

The existing scraper checks robots rules, throttles requests and stops on access restrictions.
`diff.py` compares extracted text rather than raw HTML, prioritising changed amounts/ages/years.
Non-numeric conditions and URL/status changes also count. This process executes no policy text
and does not send website content to an LLM.

The watcher checks the manifest against the HTML/PDF seed lists, clean files, extraction
verification and the diff against ACTIVE. A missing extracted figure requires investigation:
it may reflect page chrome or a layout defect rather than a policy change.

| State | Meaning | Result |
| --- | --- | --- |
| `unchanged` | Complete required evidence; checked text/URLs/statuses match ACTIVE | Summary/artifacts only |
| `changed` | Complete candidate contains changes | Draft review PR; no direct push to main |
| `blocked` | Recorded access restriction prevented checking | Attention issue; retain ACTIVE |
| `incomplete` | Missing/failed pages, clean files or extracted figures | Attention issue; no candidate PR |
| `failed` | Missing/inconsistent evidence or unexpected failure | Attention issue where possible; failed workflow |

Notification/publication errors appear as `publication_error` and fail the reporting step without
replacing the source-check status. If GitHub issue permissions fail too, inspect the red Actions
run/artifacts; there is no independent alert-delivery guarantee. Dependency/runner failures can
stop before checking begins; they are not successful freshness checks.

Repeated problems update one open attention issue rather than creating weekly duplicates.
GitHub edits do not guarantee new notifications, so someone must monitor Actions and the issue.
Reviewers close it after investigating resolution; a successful check does not erase earlier findings.
If a candidate PR is already open, a later changed check preserves its new evidence in artifacts and
links the pending PR in the attention issue. It does not overwrite the candidate. Review the latest
evidence, finish or close the older candidate, then rerun if a newer candidate PR is needed.

## Evidence dates and frozen evaluation

The workflow never changes ACTIVE, the served chunks/topic cards, income rules, SQLite prices,
prompts, model settings or the vector index. Sandra's candidate pre-build step is retained:
new chunks and cards are built and validated only in the candidate date's folders. On success,
the draft PR also includes these inactive folders and the chunk-ID registry updates. On failure,
it includes only the snapshot/seeds and an explicit build warning; activation must wait for a
successful local rebuild and review. Missing supposedly successful build outputs fail publication.
Detection can run during held-out evaluation; activation and tuning wait
until the frozen evaluation is complete. Record the code commit, ACTIVE date, model and retrieval
configuration alongside evaluation results.

Artifacts are retained for 30 days. `source_checked_at` records refresh completion, while
`checked_at` in the watcher report records analysis time. Per-page manifest `fetched_at` fields
show when pages were actually fetched. Same-day cache reuse means rerunning may not fetch anew.
These dates are not policy effective dates. A blocked attempt does not make stored evidence newly
verified, change citation dates or update a public freshness indicator. No new freshness UI is added.
The refresh refuses to run against ACTIVE or an older date, preserving the active evidence.

## GitHub setup

The built-in `GITHUB_TOKEN` needs contents, issues and pull-request write permissions. The owner
must allow **GitHub Actions to create pull requests** in Settings > Actions > General; organisation
policy may restrict this. Keep main-branch protection and required reviews/checks enabled.
Do not grant the watcher a branch-protection bypass.

GitHub may display **Approve workflows to run** for a PR created by the built-in token. A maintainer
must approve those CI runs when prompted and inspect required checks before merging. The watcher
does not approve, merge or enable auto-merge. See GitHub's
[workflow-trigger rules](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)
and [schedule limitations](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## Review and separate activation

1. Read the candidate's full diff and original official pages/PDFs. Check conditions, table row/header
   relationships, dates, removals and redirects. Figure-set comparisons cannot establish semantics.
2. Add a candidate README recording reviewer, review date, findings, limitations and acceptance/rejection.
   A deprecated URL or 404 needs investigation, not silent source removal or an access-bypass workaround.
3. After CI and normal review, merge an accepted inactive candidate. During held-out evaluation,
   leave ACTIVE and running application data unchanged.
4. Prepare activation in an isolated checkout/worktree. From its repository root, substitute the
   reviewed date and use the project Python environment:

   ```powershell
   python scripts/scraping/chunk.py YYYY-MM-DD
   python scripts/scraping/build_cards.py YYYY-MM-DD
   python scripts/scraping/validate.py YYYY-MM-DD
   python -m pytest -q
   ```

   Review obsolete chunk references, new card evidence and any affected deterministic income rules.
   Do not rewrite historical snapshot evidence just to mark it obsolete. Ensure replacement chunks
   exclude superseded content and preserve table labels/conditions.
5. Set ACTIVE to the reviewed date **in that isolated activation checkout**, then run
   `python scripts/build_policy_index.py` (requires RAG dependencies and Ollama's EmbeddingGemma).
   Run dev regression checks for retrieval, grant combinations, profile scope and citation/numeric
   verification. Record outcomes in the separate activation PR.
6. After activation approval, stop each local backend before pulling the activation change, rebuild
   its gitignored index using the same command, then restart and smoke-test dates and answers.
   The retriever loads chunks at startup: editing ACTIVE alone does not reload it. Keep the prior
   snapshot/index for rollback, with a compatible prior code/cards checkout if those changed too.

User 'outdated information' reports complement monitoring. They lead to team investigation and a
maintainer-run check; they do not change policy data, fetch arbitrary submitted URLs or train the
model automatically. Tasha's feedback implementation is separate. LangSmith visibility depends on
tracing settings/privacy filters: do not promise raw questions, profiles, sources or answers if
they are deliberately redacted.

## Local checks

From the repository root, using the project environment:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_policy_watch.py tests/test_policy_refresh.py -q
```

Tests construct temporary snapshots and simulate GitHub responses. One test commits and pushes
to a temporary local bare Git repository; none fetch live sites, create real issues/PRs or activate data.
After an authorised refresh, run
`python scripts/policy_watch.py` to inspect its report locally. This writes
`.local/reports/policy-watch-status.json` without GitHub calls. A missing prior refresh report
correctly fails. Only `--publish` invokes git/gh.

The first GitHub-hosted run is still required to check actual permissions and live source access.
