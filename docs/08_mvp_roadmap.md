# MVP Roadmap

## Phase 1 — Local ingestion and manual docs ✅ (implemented)
- SQLite storage, migrations, dedup (external id / DOI / URL / content hash).
- Manual collector for `.pdf/.txt/.md/.html`; PDF page markers; chunking.
- `init`, `ingest`, `status` CLI commands.

## Phase 2 — API collectors ✅ (implemented)
- arXiv (Atom API + PDF download), OpenAlex (inverted-abstract
  reconstruction), Semantic Scholar (Graph API), GitHub (repo search +
  README fetch, research-term re-ranking).
- Shared `SourceCollector` interface, retry/backoff, injectable HTTP clients,
  fully mocked tests.

## Phase 3 — LLM extraction ✅ (implemented; mock default)
- `LLMClient` abstraction; deterministic mock; Anthropic/OpenAI-compatible
  provider client; prompts in `prompts/`; pydantic validation; failures
  recorded in `rejected_items`.

## Phase 4 — Hypothesis generation ✅ (implemented)
- Crypto adaptation of extractions; deterministic hypothesis ids;
  `rejected_hft` quarantine for non-adaptable latency-edge ideas.

## Phase 5 — Ranking and reporting ✅ (implemented)
- 12-dimension weighted scoring, hard filters, CSV/JSONL/MD exports,
  ranked report, research digest.

## Phase 6 — Backtest handoff ✅ (implemented)
- `backtest_spec` MD/JSON export with rejection criteria and acceptance
  metrics; export blocked for rejected hypotheses.

## Phase 7 — Optional dashboard (future)
- Read-only local web UI (FastAPI + HTMX or Streamlit) over the SQLite DB:
  browse sources, extractions, ranked candidates; one-click spec export.

## Phase 8 — Optional automation scheduler (future)
- Cron/launchd wrapper running saved queries from the query catalog on a
  schedule: `search → extract-all → generate-hypotheses → score --all →
  report`, with digest diffs ("what's new this week").

## Hardening backlog (any phase)
- Real LLM prompt evaluation harness (golden extractions).
- OCR fallback for scanned PDFs.
- Crossref/SSRN/RSS collectors.
- Embedding-based dedup of near-identical hypotheses across sources.
- Backtest result ingestion (close the loop: outcome per hypothesis_id).
