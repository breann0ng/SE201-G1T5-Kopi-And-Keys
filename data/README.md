# Data integration

Planned local directories, excluded from Git:

- `raw/`: downloaded official policy snapshots and resale transaction CSVs.
- `processed/`: normalized policy chunks and the resale SQLite database.
- `topic_cards/`: committed, reviewed discovery cards (placeholder for now).
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
`backend/kopi_keys/components/policy_retrieval.py`. Topic cards go in
`topic_cards/` (see its README).

## Resale transactions (Price Query Tool)

1. Download the CSV from data.gov.sg: [Resale flat prices based on registration
   date from Jan-2017 onwards](https://data.gov.sg/datasets/d_8b84c4ee58e3cfc0ece0d773c8ca6abc/view).
   Use only this file: the older files in the collection use approval dates
   (1990 to Feb 2012) or a different / missing `remaining_lease` format.
2. Save it as `data/raw/2017-onwards-resale-prices.csv`.
3. Build the database, recording the date the CSV was downloaded:

   ```bash
   python scripts/build_resale_db.py --downloaded-on YYYY-MM-DD
   ```

   Every row is validated first; one bad row rejects the import and leaves any
   existing database untouched. Output: `data/processed/hdb_prices.db`
   (override with the `KOPI_RESALE_DB` environment variable). Team snapshot:
   downloaded 2026-10-14, 242,737 sales, 2017-01 to 2026-10 (October partial).
4. Query it (dates default to the last 12 months, as in the graph):

   ```bash
   python -m kopi_keys.components.price_query --town TAMPINES --flat-type "4 ROOM"
   python -m kopi_keys.components.price_query --town TAMPINES --flat-type "4 ROOM" \
       --question "What are 4-room prices in Tampines?" --output .local/tampines.json
   python -m kopi_keys.cli --input .local/tampines.json   # full graph with Ollama
   ```

`SqlitePriceTool.query()` returns `PriceResult` (`schemas.py`). Quartiles use
inclusive linear interpolation (Excel `QUARTILE.INC`); mean, median and IQR are
rounded once to cents. Zero matches return `volume: 0`. Unknown towns / flat
types and dates outside the data raise `InvalidPriceFilterError` (a
`ToolUnavailableError`, so the graph stores it in `price_error`), with
suggestions. `is_low_volume()` flags fewer than 10 sales.

## Income ceilings

`backend/kopi_keys/rules/income_ceilings.json` holds grant income ceilings with
source URL and dates; `kopi_keys.rules.check_income_ceiling()` compares an
income against them and never states eligibility. **All figures are
`verified: false`** (secondary source after the August 2026 changes) until
checked against HDB's grant pages or the policy snapshot.
