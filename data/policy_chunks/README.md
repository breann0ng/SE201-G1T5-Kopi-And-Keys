# Policy chunks

`<YYYY-MM-DD>/chunks.jsonl` holds one JSON object per line, built from
`data/policy_snapshots/<YYYY-MM-DD>/clean/` by `scripts/scraping/chunk.py`.
**Load the date named in `data/policy_snapshots/ACTIVE`, never simply the newest folder.**

## Fields

| Field | Meaning |
|---|---|
| `chunk_id` | `CHUNK_<POLICY>_<NN>`. It stays the same across reruns while the page, heading and content are unchanged (`chunk_id_registry.json`). Changed content gets a new ID |
| `source_url`, `source_slug` | The official page, and its file in the snapshot |
| `source_tier` | 1 = HDB/CPF scheme page or HDB PDF, 2 = MyNiceHome guide, 3 = CPF explainer. Prefer lower |
| `policy_name`, `section_heading` | Topic, and the heading path within the page (`H1 > H2 > …`) |
| `snapshot_date` / `verified_on` | When this text was seen live on the official site |
| `page_last_updated` | The page's own "Last updated …" line, verbatim, or null |
| `effective_date`, `effective_date_text` | Set only when the chunk states exactly one date such as "From 20 August 2024" (`effective_date_text` is verbatim). Otherwise null |
| `low_priority` | From a thin page (navigation or link hub). Rank it below other chunks; topic cards never use it |
| `superseded` | Set to true in review when a newer snapshot changes this content |
| `eligibility_tags` | `{field: [values]}`, using values from `data/schema/vocab.json`. Added only where the chunk's wording explicitly matches |
| `content`, `content_sha256` | Verbatim text from the clean markdown, and its hash |

## Chunking rules

- **Splitting.** Text is split by heading. Sections over ~300 words are then split between paragraphs,
  lists or tables, never inside one. A line ending in `:` stays with what follows it.
  Tables over ~600 words are split between rows, with the header row repeated.
- **Embedding.** `content` does not repeat the heading. Retrieval should embed
  `section_heading + "\n" + content`.
- **Known limits:**
  - 12 chunks exceed 600 words. These are tables that trafilatura put on one line, so there is no
    safe row boundary to split on.
  - Tags come from keyword rules, so treat them as retrieval hints, not eligibility decisions.

Rebuild: `cd scripts/scraping && python chunk.py && python build_cards.py && python validate.py`.
