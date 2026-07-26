# Backtest Spec Authoring Prompt

You are preparing a handoff document for a separate backtesting agent. The
agent will implement the backtest **without reading the original paper**, so
the spec must be self-contained and unambiguous.

## Requirements

- Every rule must be codable as written: exact feature formulas, lookbacks,
  thresholds, bar timeframe, rebalance cadence, and order type assumptions.
- State fees and slippage explicitly (bps per side, maker vs taker).
- Include rejection criteria: the concrete conditions under which the
  hypothesis is declared falsified and abandoned.
- Include minimum acceptance metrics (OOS Sharpe, profit factor, max drawdown,
  minimum trade count, walk-forward fold pass rate).
- Confirm non-HFT compatibility: the strategy must be executable with
  seconds-to-minutes order latency on a standard exchange API. If it is not,
  the spec must not be produced — flag `requires_hft_or_low_latency_edge`
  instead.

## Sections (in order)

Strategy Name, Research Source(s), Core Hypothesis, Target Market,
Target Assets, Timeframe, Required Data, Feature Definitions, Entry Rules,
Exit Rules, Risk Rules, Position Sizing, Fees and Slippage Assumptions,
Optimization Parameters, Walk-Forward Validation Plan, Expected Weaknesses,
Rejection Criteria, Minimum Acceptance Metrics.

## Hypothesis

{{hypothesis_json}}
