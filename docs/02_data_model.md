# Data Model

SQLite database at `data/research_intel.db` (path configurable). All models
in `src/research_intel/storage/models.py`. JSON payload columns hold the
pydantic-validated records from `extraction/schemas.py`.

## sources

One row per external research source. Deduplicated on
(`source_type`, `external_id`), then DOI, URL, and content `checksum`.

| Field | Notes |
|---|---|
| id | PK |
| source_type | `arxiv` / `openalex` / `semantic_scholar` / `github` / `manual` |
| external_id | arXiv id, OpenAlex work id, S2 paper id, `owner/repo`, or absolute path |
| url, title, authors (JSON), published_date, abstract | metadata |
| doi, citation_count | when available |
| retrieved_date | UTC timestamp of ingestion |
| raw_text_path, pdf_path | files under `data/` |
| checksum | sha256 of extracted text (dedup) |
| extra (JSON) | source-specific: stars, venue, concepts, pdf_url, ... |

## documents

Parsed textual content attached to a source. `kind` is `fulltext`,
`abstract`, or `readme`. Deduplicated on `content_hash`. `text_path` points
to the parsed text file; `num_pages` set for PDFs; `parse_status` records
failures explicitly.

## document_chunks

Semantic-section (markdown heading) or windowed chunks with `chunk_index`,
`section_title`, `page_number` (from `[[page:N]]` PDF markers), and
`char_start`/`char_end` offsets into the parsed text.

## extractions

One structured extraction per document. `payload` = `ExtractionRecord`
(docs/04). Denormalized query columns: `hft_dependency`, `backtestability`.

## strategy_hypotheses

`hypothesis_id` is a deterministic content-derived slug (`hyp-<sha1[:10]>`),
unique. `payload` = `HypothesisRecord` (docs/06). `status` lifecycle:
`candidate → scored | rejected | rejected_hft`. `priority_score` mirrors the
latest weighted score for cheap ordering.

## scores

Append-only score events per hypothesis: `dimensions` (JSON, 0–10 each),
`weighted_total` (0–100), `excluded`, `exclusion_reason`,
`hard_filter_flags` (JSON list). The latest row per hypothesis wins.

## backtest_handoff_specs

Record of every exported spec: `hypothesis_id`, `format` (`md`/`json`),
`path`, full `payload` snapshot.

## ingestion_runs

Audit of every collect/ingest invocation: collector, query, timestamps,
`num_found`, `num_new`, `status` (`running`/`done`/`failed`), `error`.

## rejected_items

Every failure or policy rejection, never silent: `stage`
(`ingestion`/`extraction`/`hypothesis`/`scoring`), `entity_type`,
`entity_ref`, `reason` (e.g. `requires_hft_or_low_latency_edge`,
`fetch_failed: ...`, validation errors).

## tags

Free-form labels: (`entity_type`, `entity_ref`, `tag`) unique. Reserved for
curation workflows (watchlists, themes); not used by the MVP pipeline.

## schema_version

Single-row marker written by `storage/migrations.py` (`SCHEMA_VERSION = 1`);
the seed for future Alembic migrations.
