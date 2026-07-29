# Roadmap

## Where this repository stands

Phases 1–6 are the scope of this public repository and are **complete**: the
pipeline runs end to end, offline, from a fresh clone.

### Phase 1 — Local ingestion and manual documents ✅
- SQLite storage, migrations, dedup (external id / DOI / URL / content hash).
- Manual collector for `.pdf/.txt/.md/.html`; PDF page markers; chunking.
- `init`, `ingest`, `status` CLI commands.

### Phase 2 — API collectors ✅
- arXiv (Atom API + PDF download), OpenAlex (inverted-abstract reconstruction),
  Semantic Scholar (Graph API), GitHub (repo search + README fetch, research-term
  re-ranking).
- Shared `SourceCollector` interface, retry/backoff, injectable HTTP clients,
  fully mocked tests.

### Phase 3 — LLM extraction ✅
- `LLMClient` abstraction; deterministic mock; Anthropic/OpenAI-compatible provider
  client; prompts in `prompts/`; pydantic validation; failures recorded in
  `rejected_items`.

### Phase 4 — Hypothesis generation ✅
- Crypto adaptation of extractions; deterministic hypothesis ids; `rejected_hft`
  quarantine for non-adaptable latency-edge ideas.

### Phase 5 — Ranking and reporting ✅
- 12-dimension weighted scoring, hard filters, CSV/JSONL/MD exports, ranked report,
  research digest.

### Phase 6 — Backtest handoff ✅
- `backtest_spec` MD/JSON export with rejection criteria and acceptance metrics;
  export blocked for rejected hypotheses.

## Where the work actually went

The original MVP roadmap continued with an optional dashboard and an optional
scheduler. Neither was built, and neither is planned — running the pipeline was
never the bottleneck.

The bottleneck was the stage *after* the handoff artifact: deciding whether a
generated hypothesis is true, without the process quietly rescuing it. Development
moved there, into a separate research-process layer that has since gone through 34
released iterations. Its design — admission control, pre-freeze identity gates, data
semantics certification, immutable snapshot materialization, preregistration,
execution accounting, independent reconciliation, terminal closure — is documented
in [11_process_architecture.md](11_process_architecture.md), and its results so far
in [12_research_outcomes.md](12_research_outcomes.md).

That layer is coupled to a specific data estate and strategy corpus and is not
published.

## Backlog for this repository

Things that would genuinely improve the public layer, in rough priority order:

- Real LLM prompt evaluation harness over the golden extractions (the benchmark in
  `eval_sources/batch_v1/` is scored today, not regression-gated).
- Backtest result ingestion — close the loop by attaching an outcome to a
  `hypothesis_id`, so scoring can eventually be calibrated against verdicts.
- Embedding-based dedup of near-identical hypotheses arriving from different sources.
- OCR fallback for scanned PDFs.
- Additional collectors: Crossref, SSRN, RSS.
