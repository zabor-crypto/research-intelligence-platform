# Research Intelligence Platform

A local-first pipeline that continuously turns external research material
(papers, repos, notes) into **structured, ranked, backtest-ready crypto
trading strategy hypotheses**.

It is explicitly **not** a trading bot, not an HFT platform, and not an
execution system. It is a research intelligence and hypothesis-generation
tool that feeds a separate backtesting workflow. Ideas that depend on
HFT/low-latency edge are detected, penalized, and excluded from candidate
exports (`requires_hft_or_low_latency_edge`).

Everything runs offline and deterministically by default: the LLM layer is
replaceable and ships with a mock, all HTTP is mocked in tests, and the entire
quickstart below works from a fresh clone with no API key.

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

## What happens after the handoff

This repository ends where the hard part begins. A generated hypothesis is a
claim, and the value of a research pipeline is decided by what stops a plausible
claim from surviving a bad result.

That stage lives in a separate research-process layer — admission control,
pre-freeze market-identity gates, data semantics certification, immutable snapshot
materialization, preregistration and freeze, execution accounting, independent
reconciliation against a differential oracle, and mechanically irreversible
terminal closure. The engines are not published; the enforcement logic partly is.

- **[docs/11_process_architecture.md](docs/11_process_architecture.md)** — the
  full lifecycle, the enforcement mechanisms, and what each one prevents.
- **[docs/12_research_outcomes.md](docs/12_research_outcomes.md)** — everything it
  has measured, built and decided.
- **[docs/13_current_status.md](docs/13_current_status.md)** — where the project is
  at iteration 34, and the open questions with what would resolve them.
- **[`src/research_process/`](src/research_process/)** — eight of those gates as
  working, dependency-free code with 95 tests: the pre-freeze identity, contradiction,
  dataset-intersection and authority gates, the historical-backtest artifact contract,
  the insolvency and replay taxonomies, and the terminal closure registry. Each module
  docstring names the concrete failure that motivated it.

### Results in brief

**The extraction layer is benchmarked, not asserted.** On a blind 13-document,
134-field set: evidence-link presence 100%, link validity 97.8%, unsupported
assertions 2.1%, unsupported evidence links **0**, zero critical errors. When a
source genuinely does not close a field, the pipeline says so 84% of the time
instead of filling the gap — which is what makes every downstream gate meaningful.

**Eighteen components, validated by two complete vertical slices** — a source
carried from discovery through preregistered backtest to terminal closure, twice,
in two different strategy families. Fourteen are generic and reusable; four are
strategy-family specific, and the split is tracked so the distinction stays honest.

**A federated data catalog of 183 logical datasets across 221 replicas**, plus the
path from a catalogued dataset to something a backtest may legitimately read:
semantics certification with an explicit evidence hierarchy, controlled
materialization off read-only sources, bounded acquisition from free official
publishers, and immutable content-hashed snapshots. First dataset carried all the
way: 401 760 rows, 109 partitions, `screen_ready`, content hash recorded.

**The second one deliberately did not pass.** A funding dataset materialized
cleanly, then stopped one step short — the venue's documentation does not say
whether its funding timestamp marks the *effective* or the *published* instant, no
local evidence settles it, and those are different instants for anything that has to
know what was knowable at decision time. Relaxing one confidence threshold would
have produced a second green result. The gate held instead.

**Two strategies have been through a preregistered backtest; both were falsified**
and both are terminally closed, with full cost decomposition and failure attribution
published — including one run that ends insolvent, reported rather than dropped.
Neither can re-enter a promotion path: the closure registry fails closed and
`reopen()` raises. A research process whose published output is only its successes
provides no evidence that it can produce a negative result at all.

**Where it stands:** the machinery is built and proven end to end; the data estate
it runs on is 1% certified. That, and not strategy generation, is the current work.

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

- **Tests:** 324 passing pytest cases (264 `def test_` functions; the difference
  is test parametrization), run fully offline. CI runs ruff + pytest.
- **What is public here:** the pipeline, the replaceable LLM layer, the
  code-enforced non-HFT filters, the 12-dimension scoring, the evaluation
  benchmark, eight enforcement gates from the research-process layer, the CLI,
  docs and tests.
- **What is intentionally not here:** the private research corpus and source
  registry, strategy implementations and parameters, the backtest and execution-
  accounting engines, run outputs, positions, or account data. The private layer
  is roughly eight times this repository by source lines (~70k vs ~8.5k), carries
  ~3 500 test functions, and has gone through 34 released iterations — its design
  and results are documented above, its engines are not published.
- **Limitations:** this is a research-triage / hypothesis-generation tool, not a
  trading bot and not an execution system; it produces backtest *specifications*,
  not profitability claims. Ideas depending on HFT/low-latency edge are detected
  and excluded by design.

## Related repository

[**zaBor**](https://github.com/zabor-crypto/zaBor) sits downstream of this one: the
engineering toolkit where surviving ideas become running components. It contains a
multi-exchange emergency risk-control engine with a portfolio-level Regime Guard, a
wallet-tagged Hyperliquid microstructure recorder with a per-counterparty adverse-
selection toolkit, and a multi-venue funding-carry research stack that ships an
explicit REJECT verdict alongside its code.

The division of labour is deliberate: this repository decides **what is worth
building**, that one contains **what was built**.

## Disclaimer

This platform generates, ranks, and exports research hypotheses for later
backtesting. Nothing it outputs is a claim of live trading profitability.
