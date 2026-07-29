# Project Brief

## What the platform does

The Research Intelligence Platform continuously converts external research
material — academic papers (arXiv, OpenAlex, Semantic Scholar), GitHub
research repositories, and local documents (PDF/MD/TXT/HTML) — into
structured, testable trading strategy hypotheses for **crypto markets at
non-HFT timeframes (1 minute to daily)**.

For each ingested source it produces:

1. a structured **extraction** of tradable components (signal, entry/exit
   logic, data requirements, regime conditions, limitations, HFT dependency);
2. a crypto-adapted **strategy hypothesis** with concrete rules, failure
   modes, and a validation plan;
3. a 12-dimension **score** with hard feasibility filters;
4. ranked **exports** (CSV/JSONL/Markdown) and a **backtest handoff spec**
   detailed enough for a separate backtesting agent to implement without
   reading the original paper.

## What it does not do

- No live trading, order execution, or exchange connectivity.
- No HFT/low-latency research: ideas whose edge is queue position,
  co-location, latency arbitrage, or speed competition are ingested for
  background knowledge only, marked `requires_hft_or_low_latency_edge`,
  and excluded from candidate exports.
- No backtesting itself — it produces backtest *specifications*. Validation
  happens in a separate research-process layer, described in
  [11_process_architecture.md](11_process_architecture.md) and not published here.
- No claim of profitability: outputs are hypotheses to be falsified.

## Why it exists

Strategy R&D throughput is bottlenecked by idea sourcing and triage, not by
backtesting capacity. Reading papers end-to-end is slow, and most academic
results are either not transferable to crypto, not executable without HFT
infrastructure, or too vague to falsify. This platform industrializes the
triage: it extracts only tradable mechanics, adapts them to crypto at
realistic timeframes, and ranks them by practical testability.

## Where it fits in the R&D pipeline

```
[Research Intelligence Platform]      [Research process engine]      [Portfolio]
 discover → extract → hypothesize ──► preregister → backtest ──►  allocate to
 → score → rank → backtest spec       → reconcile → adjudicate      survivors
                                       → close                      (if any)
```

The handoff artifact is `exports/backtest_specs/backtest_spec_<id>.md|json`
(see docs/07_backtest_handoff_contract.md). Everything upstream of the backtest
lives here. Everything downstream lives in a separate, larger research-process
layer that is not published — its design is documented in
[11_process_architecture.md](11_process_architecture.md) and its results to date in
[12_research_outcomes.md](12_research_outcomes.md).
