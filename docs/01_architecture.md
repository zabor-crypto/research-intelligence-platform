# Architecture

## Module diagram

```
                       ┌──────────────────────────────────────────┐
                       │                 cli.py                   │
                       └───┬──────────┬───────────┬──────────┬────┘
                           │          │           │          │
              ┌────────────▼───┐  ┌───▼──────┐ ┌──▼───────┐ ┌▼──────────┐
              │  collectors/   │  │extraction│ │hypotheses│ │ reports/  │
              │ arxiv openalex │  │ extractor│ │ generator│ │ digest    │
              │ s2 github      │  │ schemas  │ │ scorer   │ │ ranked    │
              │ manual         │  │ validators│ │ exporter │ └───────────┘
              └───────┬────────┘  └───┬──────┘ └──┬───────┘
                      │               │           │
               ┌──────▼─────┐   ┌─────▼───────────▼─────┐
               │  parsing/  │   │        llm/           │
               │ pdf html   │   │ base mock provider    │
               │ text chunk │   │ prompt_loader         │
               └──────┬─────┘   └─────────┬─────────────┘
                      │                   │ prompts/*.md
               ┌──────▼───────────────────▼──────┐
               │           storage/              │
               │  models · db · repositories ·   │
               │  migrations   (SQLite + files)  │
               └─────────────────────────────────┘
```

`ingestion.py` orchestrates collectors → parsing → storage.
`config.py` (pydantic-settings, `.env`) and `logging_config.py` are shared.

## Data flow

1. **Collect** — a `SourceCollector.search()` returns normalized
   `RawSourceRecord`s; `fetch()` returns full content (`RawDocument`).
2. **Ingest** — `ingestion.ingest_records()` dedups sources (external id →
   DOI → URL → content hash), writes raw files to `data/raw/`, parsed text
   to `data/parsed/`, creates `documents` and `document_chunks`.
3. **Extract** — `extraction.extractor` feeds document text + JSON schema to
   the `LLMClient`, validates the output (`pydantic`), stores `extractions`.
4. **Hypothesize** — `hypotheses.generator` converts extractions into
   crypto-testable `strategy_hypotheses`; HFT-dependent, non-adaptable ideas
   get status `rejected_hft` and are logged in `rejected_items`.
5. **Score** — `hypotheses.scorer` collects 12 dimension scores from the LLM
   layer, applies **code-level hard filters** (non-HFT, data availability,
   signal clarity, falsifiability), computes the weighted 0–100 score.
6. **Export/report** — ranked CSV/JSONL/MD in `exports/`, backtest specs in
   `exports/backtest_specs/`, digest in `reports/`.

## CLI flow (MVP)

```
init → ingest/search → extract-all → generate-hypotheses → score --all
     → export-ranked → export-backtest-spec → report
```

Each stage is idempotent: re-runs only process items that lack downstream
artifacts (documents without extractions, extractions without hypotheses,
unscored hypotheses), and ingestion dedups at both source and document level.

## Extension points

- **New collector**: subclass `SourceCollector`, register in
  `collectors.get_collector()`. HTTP goes through `request_with_retries`
  and accepts an injected `httpx.Client` for testing.
- **New LLM provider**: implement `LLMClient` (3 methods), wire into
  `llm.get_llm_client()`. Prompts stay in `prompts/`.
- **New scoring dimension**: add to `SCORING_DIMENSIONS`, `WEIGHTS`
  (must still sum to 1.0), and the scoring prompt.
- **New export format**: extend `hypotheses/exporter.py`.
- **Scheduler/dashboard** (roadmap phases 7–8) sit on top of the CLI and DB
  without touching the pipeline.

## SQLite → PostgreSQL migration path

The MVP is local-first by design. To migrate later:

1. Models are standard SQLAlchemy 2.0 declarative — swap the engine URL in
   `storage/db.py` for `postgresql+psycopg://...`.
2. Replace `storage/migrations.py`'s create-all + version stamp with Alembic,
   seeding from `SCHEMA_VERSION`.
3. JSON columns map to `JSONB`; add GIN indexes on `extractions.payload` and
   `strategy_hypotheses.payload` for querying.
4. Move `data/raw/` and `data/parsed/` to object storage if multi-machine;
   the `*_path` columns become URIs.
