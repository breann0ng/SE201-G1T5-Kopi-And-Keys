# Data integration (not connected yet)

Planned local directories, excluded from Git:

- `raw/`: downloaded official policy snapshots and resale transaction CSVs.
- `processed/`: normalized policy chunks, topic cards and the resale SQLite database.
- `chroma/`: generated vector index.

Policy records should preserve stable IDs, source URL, effective date, snapshot
version and superseded status. Do not infer an effective date from a crawl date;
decide how unknown dates are represented before loading official pages.

Transaction imports should record their source, download date, coverage and schema.
The SQLite adapter will accept validated filters and use parameterised read-only
queries. An absent dataset must not be replaced with invented price figures.

The only evidence shipped with this scaffold is fictional and lives in
`backend/kopi_keys/tools/policy.py`.
