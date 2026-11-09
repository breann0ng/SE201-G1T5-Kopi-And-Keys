# Dependency audit and exposure review — 9 November 2026

Three scopes were checked separately; none is a security certification.

| Scope | Result / action |
| --- | --- |
| Frontend lockfile | Eight moderate entries initially. Compatible updates fixed Vite; a scoped `@typescript-eslint/typescript-estree` override to minimatch `^11.0.1` fixed the remainder. Zero reported entries after installation. Node 22, 20 tests, lint and build checked. |
| Fresh Python core/dev resolution | Zero reported entries. This alone excludes optional RAG packages and an older laptop environment. |
| Actual laptop `.venv`, including RAG/tooling | Initially 31 advisory records across five packages, including duplicate advisory records. Updated pip 23.1.2 → 26.3, setuptools 65.5.0 → 84.2.1, certifi 2026.7.22 → 2026.10.23, oauthlib 4.0.0 → 4.0.1. Chroma 1.5.9 remains for the reviewed local index; its findings remain visible. |

The post-update actual-environment scan reports **five records in Chroma only**
(four distinct advisory IDs, with a duplicate record). No ignore rule was used.
The complete local regression suite passed after these compatible updates.

The CI audit now installs `.[dev,rag]` and retains the Python/npm JSON findings
as a 14-day artifact. It remains **report-only**, as the team configured; a green
audit job is not proof that its output contains no findings.
The backend test job still installs core/dev only and skips the real-vector check
when Chroma is unavailable. No CVE ignore rule was added.

## Chroma findings

The observed package index offers Chroma 1.5.9 as the newest compatible release.
The reviewed [pre-authentication collection-configuration advisory](https://github.com/advisories/GHSA-f4j7-r4q5-qw2c)
and [collection-update advisory](https://github.com/advisories/GHSA-36p7-vc44-83pf)
list no patched version. The audit also reports cross-tenant authorisation issues
([CVE-2026-45830](https://github.com/advisories/GHSA-2wm9-hf6c-p5cr),
[CVE-2026-45831](https://github.com/advisories/GHSA-xph7-9rjv-w5fr)).

Repository inspection shows an embedded `chromadb.PersistentClient` with local
storage. There is no Chroma HTTP server, remote `HttpClient`, collection-management
endpoint or user/model-supplied embedding-function configuration in this app.
Vectors are computed through the configured Ollama embedding service and supplied
explicitly. This is an **exposure assessment**, not a package patch or proof of
immunity. The [upstream report also describes a client path](https://github.com/chroma-core/chroma/issues/6717),
so importing untrusted Chroma stores/configurations is not acceptable.

Keep the reviewed local store under the operator's control. Do not expose or
introduce a Chroma service/tenant API or accept arbitrary model repositories or
`trust_remote_code` configurations. Public deployment requires a fresh dependency
review and a supported remediation (patched library or reviewed alternative).
Do not claim these CVEs have disappeared or silently suppress the scanner.

## Reproduce

```powershell
# Frontend audit (from frontend/)
npm audit

# In a disposable Python environment, using the same scope as CI
python -m pip install -e ".[dev,rag]" pip-audit==2.10.1
python -m pip_audit --skip-editable
```

Audit the actual demo environment as well as fresh requirements. Record package
versions, advisory IDs and fix decisions. The compatible local package updates
are environment changes; teammates must refresh their own environments. No model,
database, snapshot or index was upgraded by the dependency fixes.
