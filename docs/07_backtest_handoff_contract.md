# Backtest Handoff Contract

The handoff artifact is the boundary between this platform and the
backtesting agent. It must be implementable **without reading the original
paper** or this platform's database.

## Producing a spec

```bash
research-intel export-backtest-spec --hypothesis-id <id> [--format md|json]
```

Writes `exports/backtest_specs/backtest_spec_<id>.md|json` and records the
export in `backtest_handoff_specs`. Rejected hypotheses (HFT or hard-filter
failures) cannot be exported — the command fails with the rejection reason.

## Required fields (both formats)

- Strategy Name, Research Source(s), Core Hypothesis
- Target Market, Target Assets, Timeframe
- Required Data (canonical dataset names)
- Feature Definitions
- Entry Rules / Exit Rules / Risk Rules (each independently codable)
- Position Sizing
- Fees and Slippage Assumptions (bps per side, maker vs taker)
- Optimization Parameters (the full allowed grid — nothing outside it)
- Walk-Forward Validation Plan
- Expected Weaknesses
- Rejection Criteria — when to declare the hypothesis falsified:
  - negative OOS expectancy after fees in majority of walk-forward folds,
  - edge concentrated in a single parameter cell or single regime,
  - performance indistinguishable from a randomized-entry baseline.
- Minimum Acceptance Metrics (defaults; tighten per strategy):
  - OOS Sharpe ≥ 1.0 after fees,
  - OOS profit factor ≥ 1.15,
  - max drawdown ≤ 25%,
  - ≥ 200 trades across the backtest,
  - ≥ 60% of walk-forward folds positive.

## Contract rules for the backtesting agent

1. Implement exactly the rules in the spec; deviations go back as feedback,
   not silent changes.
2. Search only the declared optimization grid.
3. Report against the rejection criteria and acceptance metrics explicitly —
   a spec is a falsification experiment, not a success mandate.
4. Return results keyed by `hypothesis_id` so outcomes can be recorded
   against the originating research.

Example: `examples/sample_backtest_spec.md`.
