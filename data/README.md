# Data integration (not connected yet)

Planned local directories, excluded from Git:

- `raw/`: downloaded official policy snapshots and resale transaction CSVs.
- `processed/`: normalized policy chunks, topic cards and the resale SQLite database.
- `evaluation/`
    - `development/`: committed development questions and Stage 1 gateway labels.
    - `held-out/`: private final-evaluation questions; kept outside the repository
- `chroma/`: generated vector index.

Generated, imported and private evaluation data are excluded from Git. The
development set is the exception: it is committed so the team can reproduce
gateway and routing tests. See `evaluation/development/README.md` for the
relationship between the rich semantic questions and the machine-readable
Stage 1 labels.

The held-out set must not be used while tuning routing, extraction or prompts.
Git ignore rules only prevent accidental commits; they are not a security
boundary. Keep held-out questions and labels outside the workspace or provide
them only during final evaluation.

Policy records should preserve stable IDs, source URL, effective date, snapshot
version and superseded status. Do not infer an effective date from a crawl date;
decide how unknown dates are represented before loading official pages.

Transaction imports should record their source, download date, coverage and schema.
The SQLite adapter will accept validated filters and use parameterised read-only
queries. An absent dataset must not be replaced with invented price figures.

The only evidence shipped with this scaffold is fictional and lives in
`backend/kopi_keys/tools/policy.py`.
