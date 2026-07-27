# Research Intelligence Platform

A local-first pipeline that continuously turns external research material
(papers, repos, notes) into **structured, ranked, backtest-ready crypto
trading strategy hypotheses**.

It is explicitly **not** a trading bot, not an HFT platform, and not an
execution system. It is a research intelligence and hypothesis-generation
tool that feeds a separate backtesting workflow. Ideas that depend on
HFT/low-latency edge are detected, penalized, and excluded from candidate
exports (`requires_hft_or_low_latency_edge`).

## Pipeline

```
collect (arXiv / OpenAlex / Semantic Scholar / GitHub / local files)
  → store (SQLite + local files)
  → parse & chunk
  → extract tradable components (LLM, replaceable; mock works offline)
  → generate crypto-testable hypotheses
  → score (12 dimensions, weighted, hard non-HFT filters)
  → export ranked candidates (CSV / JSONL / Markdown)
  → export backtest handoff specs for a backtesting agent
```

## Install

Requires Python 3.11+.

```bash
git clone https://github.com/zabor-crypto/research-intelligence-platform.git
cd research-intelligence-platform
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # optional; everything runs offline by default
```

## Quickstart (fully offline, mock LLM)

```bash
research-intel init
research-intel ingest --path examples/sample_manual_source.md
research-intel ingest --path examples/sample_hft_source.md   # gets rejected, by design
research-intel extract-all
research-intel generate-hypotheses
research-intel score --all
research-intel export-ranked --top 10 --format md
research-intel export-backtest-spec --hypothesis-id <id-from-generate-step>
research-intel report --output reports/research_digest.md
```

Search external sources:

```bash
research-intel search --source arxiv --query "crypto momentum volatility regime" --limit 50
research-intel search --source openalex --query "order flow imbalance cryptocurrency" --since 2023-01-01
research-intel search --source github --query "crypto backtest research" --fetch-fulltext
```

Global flags: `--verbose`, `--dry-run`.

## LLM providers

The LLM layer is replaceable (`src/research_intel/llm/`). Set in `.env`:

- `LLM_PROVIDER=mock` (default) — deterministic keyword heuristics, no network.
- `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` (+ optional `LLM_MODEL`).
- `LLM_PROVIDER=openai` + `OPENAI_API_KEY` (+ `OPENAI_BASE_URL` for any
  OpenAI-compatible endpoint).

Prompts live in `prompts/*.md` and explicitly instruct the model to reject
HFT/latency-dependent ideas.

## Development

```bash
pytest        # offline; all HTTP is mocked
ruff check .
```

## Documentation

Start with [docs/00_project_brief.md](docs/00_project_brief.md). Architecture,
data model, extraction schema, scoring framework, hypothesis spec, backtest
handoff contract, roadmap, and the non-HFT scope policy are in `docs/`.
The starter research query catalog is in
[docs/03_source_catalog.md](docs/03_source_catalog.md).

## Project status & scope

This repository is a **curated, self-contained public release** of the
infrastructure-and-methodology layer of a larger private research system. It is
authored and maintained by one person (Boris Zabavnikov).

- **Tests:** 197 passing pytest cases (169 `def test_` functions; the difference
  is test parametrization), run fully offline. CI runs ruff + pytest.
- **What is public here:** the pipeline, the replaceable LLM layer, the
  code-enforced non-HFT filters, the 12-dimension scoring, the evaluation
  benchmark, the CLI, docs and tests.
- **What is intentionally not here:** any private research corpus, proven
  strategy parameters, run outputs, positions, or account data. The full private
  system is considerably larger and is not published.
- **Limitations:** this is a research-triage / hypothesis-generation tool, not a
  trading bot and not an execution system; it produces backtest *specifications*,
  not profitability claims. Ideas depending on HFT/low-latency edge are detected
  and excluded by design.

## Disclaimer

This platform generates, ranks, and exports research hypotheses for later
backtesting. Nothing it outputs is a claim of live trading profitability.
