# Strategy Hypothesis Spec

Defined as `HypothesisRecord` in `src/research_intel/extraction/schemas.py`.
A hypothesis is **not** a reproduction of the source strategy — it is the
closest realistic crypto implementation at non-HFT timeframes, inspired by
the source's alpha mechanism.

## Adaptation doctrine

| Source idea | Becomes |
|---|---|
| volatility clustering paper | volatility-regime filter candidate |
| order imbalance / microstructure paper | 1m/5m aggregated flow-imbalance strategy |
| market making paper | slow inventory-aware quoting/risk module (only if non-HFT compatible) |
| cross-sectional equity anomaly | crypto cross-sectional ranking hypothesis |
| pure latency-edge paper | `rejected_hft` — kept for background, never exported |

## Fields

| Field | Notes |
|---|---|
| hypothesis_id | deterministic slug `hyp-<sha1[:10]>` — re-runs don't duplicate |
| source_ids | provenance (DB source ids) |
| hypothesis_name, one_sentence_idea | human-readable summary |
| market, asset_universe, timeframe, strategy_style | scope |
| core_alpha_hypothesis | why the edge should exist |
| required_data, features | canonical data names + feature definitions |
| entry_rules, exit_rules, risk_rules | lists of concrete, codable rules — validators reject hypotheses without entry AND exit rules |
| position_sizing | e.g. ATR-normalized fixed-fractional |
| fees_slippage_model | explicit bps assumptions per side |
| expected_failure_modes | how this most likely dies |
| minimum_viable_backtest | smallest falsifying experiment |
| optimization_parameters | small grid only — big grids feed overfitting |
| walk_forward_validation_plan | train/test windows, pass criteria |
| anti_overfitting_checks | parameter stability, deflated Sharpe, holdout assets |
| priority_score, status | filled by the scorer |
| hft_or_low_latency_dependency, non_applicable_reason | hard-policy fields |
| non_hft_adaptation | how a latency-flavored idea was slowed down (required to pass the HFT filter) |

## Example

See `examples/sample_hypothesis.json` — generated from
`examples/sample_manual_source.md` by the mock client: a realized-volatility
regime filter for BTC/ETH perpetuals at 1m–15m, with a 3-parameter grid,
12m/3m walk-forward plan, and explicit failure modes.

## Status lifecycle

```
candidate ──score──► scored ──export──► (backtest spec)
    │
    └── rejected_hft / rejected (hard filter) ──► report "Rejected" section only
```
