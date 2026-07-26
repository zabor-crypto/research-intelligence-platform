# Non-HFT Scope Policy

This platform researches strategies executable with **seconds-to-minutes
order latency on standard exchange APIs**. Speed is never the edge.

## Allowed strategy types

- 1-minute to daily timeframe crypto strategies
- intraday momentum / reversal systems
- liquidation / capitulation strategies
- funding-rate and basis strategies
- volatility regime strategies
- statistical arbitrage (hourly+ spread reversion)
- cross-sectional rotation
- order-book/flow features **aggregated to 1m+ intervals**
- volume imbalance and liquidity regime features
- event-driven crypto strategies
- trend-following, mean-reversion, breakout systems
- risk overlays, position-sizing frameworks, portfolio construction
- non-HFT market making (see below)

## Rejected strategy types

Anything whose profitability depends mainly on being faster than other
participants:

- nanosecond/microsecond/millisecond latency edge
- co-location / matching-engine proximity
- queue-position alpha
- latency arbitrage, direct-feed arbitration
- sub-second market making, quote racing, tick-to-trade competition
- FPGA / network-stack optimization
- exchange-specific matching-engine exploitation

Such ideas are still ingested for background knowledge, but they are flagged
`hft_or_low_latency_dependency = true` with
`non_applicable_reason = "requires_hft_or_low_latency_edge"`, receive
`non_hft_compatibility ≈ 0`, are hard-filtered out of ranked candidate
exports, and cannot be exported as backtest specs.

## Classifying borderline market-making ideas

Ask: **if every order were delayed by 5 seconds, would the edge survive?**

Accept (edge = inventory/risk management):
- slow inventory-aware quoting; volatility-adjusted spread control
- regime-aware passive quoting; maker/taker fee-aware rebalancing
- prediction-market MM with low-to-moderate latency needs
- quote placement at seconds/minutes cadence

Reject (edge = speed):
- queue-position-dependent MM; high-frequency spread capture
- maker alpha requiring continuous quote racing
- any MM whose paper shows profits vanishing above sub-second latency

## How penalization works (enforced in code, not just prompts)

1. **Extraction**: `hft_or_low_latency_dependency` + `non_applicable_reason`
   set per document. Detection uses HFT keywords *plus* semantic phrase
   patterns ("loses edge if delayed", "first in the book", "cancel and repost
   before competitors", "immediate response to depth changes", ...); provider
   prompts instruct real models explicitly.
2. **Hypothesis generation**: `hft_or_low_latency_dependency = true` on a
   hypothesis means the hypothesis itself needs latency edge → status
   `rejected_hft`, always. Genuinely adapted ideas (e.g. flow signals
   aggregated to 1m bars, quoting slowed to minutes) set the flag to false
   and document provenance: `original_source_has_latency_dependency = true`,
   `adapted_to_non_hft = true`, `adaptation_validity = "strong"`,
   `non_hft_adaptation = "<what changed>"`.
3. **Scoring**: `non_hft_compatibility` is weighted 0.11, and
   `scorer.apply_hard_filters()` excludes any hypothesis with the HFT flag —
   **unconditionally, with no adaptation escape hatch** — and any hypothesis
   whose `adaptation_validity` is `weak` or `invalid`.
4. **Export**: `export-backtest-spec` refuses rejected hypotheses; ranked
   exports list them only under "Rejected / Low Priority Ideas".

## Examples

| Idea | Verdict |
|---|---|
| Volatility-regime filter gating 1h trend entries | ✅ accepted |
| Funding-rate percentile carry on perps, rebalanced every 8h | ✅ accepted |
| Order-flow imbalance aggregated to 5m bars | ✅ accepted (adaptation documented) |
| Inventory-skewed quoting updated every 30s | ✅ accepted |
| Queue-position MM profitable only under 500µs latency | ❌ `requires_hft_or_low_latency_edge` |
| Cross-venue latency arbitrage | ❌ `requires_hft_or_low_latency_edge` |
