# Data integration (not connected yet)

Local directories, excluded from Git:

- `raw/`: downloaded official files.
  - `raw/2017-onwards-resale-prices.csv`: data.gov.sg resale transactions.
  - `raw/policy_pages/`: saved official policy page snapshots (registered in `policy/sources.yaml`).
- `processed/`: generated artifacts, e.g. `resale.db` from `scripts/build_resale_db.py`
  and normalized policy chunks.
- `chroma/`: generated vector index.

Reviewed, versioned inputs (source registry, topic cards) live in `policy/`, not here,
so they are committed and reviewed like code.

Policy records should preserve stable IDs, source URL, effective date, snapshot
version and superseded status. Do not infer an effective date from a crawl date;
decide how unknown dates are represented before loading official pages.

Transaction imports should record their source, download date, coverage and schema.
The SQLite adapter will accept validated filters and use parameterised read-only
queries. An absent dataset must not be replaced with invented price figures.

The only evidence shipped with this scaffold is fictional and lives in
`backend/kopi_keys/tools/policy.py`.
