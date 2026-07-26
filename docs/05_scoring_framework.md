# Scoring Framework

Implemented in `src/research_intel/hypotheses/scorer.py`. Dimension scores
come from the LLM layer (0–10, **10 is always better**); weights and hard
filters are code and cannot be bypassed by a permissive model.

## Dimensions and weights

| # | Dimension | Weight | 10 means |
|---|---|---|---|
| 1 | crypto_relevance | 0.11 | directly applicable to liquid crypto markets |
| 2 | non_hft_compatibility | 0.11 | fully executable at 1m+ cadence; latency dependence caps at 2 |
| 3 | data_availability | 0.11 | data obtainable by a prosumer quant (OHLCV, funding, liquidations) |
| 4 | backtest_feasibility | 0.11 | a falsifying backtest is clearly specified |
| 5 | signal_clarity | 0.09 | concrete entry/exit rules with thresholds and lookbacks |
| 6 | expected_robustness | 0.07 | effect likely real, not noise |
| 7 | novelty | 0.05 | not already heavily arbitraged |
| 8 | implementation_complexity | 0.06 | trivially simple to implement (higher = simpler) |
| 9 | overfitting_risk | 0.07 | few parameters, strong validation (higher = lower risk) |
| 10 | transaction_cost_sensitivity | 0.05 | wide margin over fees/slippage (higher = less sensitive) |
| 11 | portfolio_diversification_value | 0.04 | adds uncorrelated exposure |
| 12 | expected_edge_decay_risk | 0.05 | structural edge, slow decay (higher = slower) |
| 13 | source_evidence_quality | 0.08 | full paper, explicit rules, OOS tests, costs (1 = pure opinion) |

Weights sum to 1.0 (unit-tested). Final priority score =
`sum(dim * weight) * 10`, i.e. 0–100.

`source_evidence_quality` guidance: 10 = full paper with explicit rules,
OOS/robustness tests, costs included; 7 = preprint with adequate
methods/results; 5 = idea present but weakly validated; 3 = abstract-only or
blog-like claim; 1 = pure opinion.

## Hard filters (any flag ⇒ excluded from candidate exports)

| Flag | Trigger |
|---|---|
| `requires_hft_or_low_latency_edge` | `hft_or_low_latency_dependency = true` — **unconditional**; adaptation text does not rescue it |
| `weak_or_invalid_non_hft_adaptation` | `adaptation_validity` is `weak` or `invalid` |
| `required_data_unavailable_or_unrealistic` | data_availability < 3 |
| `strategy_logic_too_vague` | signal_clarity < 3 |
| `not_falsifiable_with_clear_backtest` | backtest_feasibility < 3 |

A latency-flavored source that is genuinely adapted must set
`hft_or_low_latency_dependency = false` and document the adaptation via
`original_source_has_latency_dependency = true`, `adapted_to_non_hft = true`,
`adaptation_validity = "strong"`, and `non_hft_adaptation`.

## Soft penalties (demoted, not excluded)

| Flag | Trigger | Effect |
|---|---|---|
| `soft_penalty:abstract_only_without_parameters` | `parameter_source_quality = missing` AND source_evidence_quality ≤ 3 | priority score × 0.5 |

Excluded hypotheses keep their score for the record, get status
`rejected`/`rejected_hft`, appear in the report's "Rejected / Low Priority
Ideas" section, and **cannot** be exported as backtest specs.

## Examples

- *Volatility-regime momentum filter on BTC/ETH perps (1m–15m)*: high
  crypto_relevance (9), non_hft (9), easy data (9), clear rules (8) → ~75/100,
  candidate.
- *Queue-position market making*: non_hft_compatibility 0 + hard filter →
  excluded, `requires_hft_or_low_latency_edge`, regardless of other scores.
- *"ML predicts markets" survey with no rules*: signal_clarity 1 → excluded,
  `strategy_logic_too_vague`.

## Recalibrating

Edit `WEIGHTS` in `scorer.py` (keep the sum at 1.0 — a test enforces it) and
re-run `research-intel score --all --rescore`. Scores are append-only, so the
history of calibrations is preserved in the `scores` table.
