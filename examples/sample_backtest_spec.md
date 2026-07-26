# Backtest Spec — Realized-Volatility Regime Filter (from: Volatility Regime Conditioning of Intraday Momentum in Crypt)

Hypothesis ID: `hyp-d5c0c27510`
Priority Score: 76.0/100
Non-HFT Compatible: Yes
Parameter Source Quality: explicit
Parameterization Status: source_parameterized

## Research Source(s)

- **Volatility Regime Conditioning of Intraday Momentum in Crypto Markets**; type: manual; location: examples/sample_manual_source.md; source_id: 1, document_id: 1

## Core Hypothesis

Volatility regimes condition the profitability of directional signals; use a vol-regime classifier as an overlay that gates entries and scales size.

## Source Reported Metrics

- sharpe after costs: 1.4
- sharpe unconditional: 0.4
Source reports Sharpe 1.4 after costs (vs Sharpe 0.4 unconditional).

## Target Market

crypto

## Target Assets

BTC, ETH perpetuals

## Timeframe

Bar timeframe: 1m-15m

## Required Data

- ohlcv
- volume
- funding_rates

## Feature Definitions

- ohlcv
- volume
- funding_rates

## Feature Formulas

- `ret_30m` = close / close.shift(30) - 1 (on 1m bars)
- `rv_60m` = std(1m log returns over 60 bars) * sqrt(60)
- `vol_ratio` = rv_60m / rv_240m (short/long realized volatility)
- `trend_strength` = abs(ret_30m) / rv_60m
- `atr_60m` = average true range over 60 1m bars

## Strategy Parameters

| Parameter | Value | Provenance |
|---|---|---|
| rv_window_minutes | 60 | source |
| vol_expansion_ratio | 1.2 | source |
| vol_contraction_ratio | 0.8 | source |
| momentum_lookback_minutes | 30 | source |
| trend_strength_entry | 0.5 | source |
| trend_strength_exit | 0.2 | source |
| time_stop_minutes | 120 | source |
| stop_loss_atr_mult | 1.5 | source |
| fee_slippage_bps_per_side | 7 | source |

Parameters marked `source` were extracted from the research source;
`default` values are platform defaults and must be treated as free
parameters, not findings.

## Order Assumptions

market (taker) orders at next 1m bar open after signal; no partial fills modeled; execution latency tolerance >= 1 bar (non-HFT by construction)

## Entry Rules

- Long entry: vol_ratio > 1.2 AND ret_30m > 0 AND trend_strength = abs(ret_30m) / rv_60m > 0.5
- Short entry: vol_ratio > 1.2 AND ret_30m < 0 AND trend_strength > 0.5

## Exit Rules

- Exit when trend_strength < 0.2
- Exit on regime transition: vol_ratio < 0.8 (expanding -> contracting)
- Time stop: exit after 120 minutes in position
- Stop-loss at 1.5x ATR_60m from entry price

## Risk Rules

- max position risk 1% of equity per trade
- portfolio-level volatility target 15% annualized
- de-risk 50% when 30-day drawdown exceeds 10%

## Position Sizing

size = (1% equity risk) / (stop distance) with stop at 1.5x ATR; scaled down when realized vol exceeds the 15% annualized portfolio target

## Fees and Slippage Assumptions

taker 7 bps per side (fees + slippage); maker 1 bp where passive fills are realistic

## Optimization Parameters

Grid keys reference the strategy parameter / rule names above.

- rv_window_minutes: [30, 60, 90]
- vol_expansion_ratio: [0.6, 1.2, 1.8]
- vol_contraction_ratio: [0.4, 0.8, 1.2]
- momentum_lookback_minutes: [15, 30, 45]
- trend_strength_entry: [0.25, 0.5, 0.75]
- trend_strength_exit: [0.1, 0.2, 0.3]
- time_stop_minutes: [60, 120, 180]
- stop_loss_atr_mult: [0.75, 1.5, 2.25]

## Optimization Constraints

The backtester MUST enforce these when combining grid values; grid
combinations violating any constraint are invalid and must be skipped.

- vol_expansion_ratio > vol_contraction_ratio
- trend_strength_entry > trend_strength_exit
- time_stop_minutes > momentum_lookback_minutes

## Baseline Comparisons

- buy-and-hold on the same universe
- randomized-entry baseline with identical exits and sizing
- unconditional variant (same rules without the regime/filter condition)

## Walk-Forward Validation Plan

Rolling walk-forward: 12-month train / 3-month test, stepped quarterly; require positive OOS expectancy in >=60% of folds.

## Minimum Viable Backtest

Backtest on BTC and ETH 1m-15m bars over >=3 years including one bear market; compare vs the baseline set (buy-and-hold, randomized-entry, unconditional variant).

## Expected Weaknesses

- edge is an artifact of survivorship or lookahead bias
- signal decays after fees at the target timeframe
- regime dependence: works only in trending/high-vol samples

## Rejection Criteria

- negative OOS expectancy after fees in majority of walk-forward folds
- edge concentrated in a single parameter cell or single market regime
- performance indistinguishable from randomized-entry baseline

## Minimum Acceptance Metrics

- oos_sharpe: >= 1.0 after fees
- oos_profit_factor: >= 1.15
- max_drawdown: <= 25%
- min_trades: >= 200 across the full backtest
- walk_forward_folds_positive: >= 60%
