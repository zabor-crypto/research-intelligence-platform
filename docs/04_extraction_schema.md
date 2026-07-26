# Extraction Schema

Defined as `ExtractionRecord` in `src/research_intel/extraction/schemas.py`
and enforced with pydantic before anything enters the database. The extractor
does **not** summarize papers — it extracts tradable hypothesis components.

Every extraction must implicitly answer: Can this become a concrete backtest?
What data is required? What rules would be tested? Why might it work / fail?
Is it compatible with non-HFT crypto execution?

## Fields

| Field | Type | Meaning |
|---|---|---|
| source_id, document_id | str | DB ids (set by the extractor, not the LLM) |
| title | str | source title |
| research_domain | str | e.g. market_microstructure, econometrics, financial_ml |
| asset_class | str | crypto / equities / futures / multi_asset |
| market_type | str | spot / perpetual_futures / options / prediction_market |
| timeframe | str | `1m-15m`, `1h-4h`, `daily`, or `unspecified` |
| strategy_style | str | momentum, mean_reversion, volatility_regime, statistical_arbitrage, flow_imbalance, carry_basis, market_making, cross_sectional, event_driven, portfolio_risk, generic |
| alpha_mechanism | str | *why* the edge should exist |
| signal_description | str | the signal in concrete terms |
| features, indicators | list[str] | named features / indicators |
| entry_logic, exit_logic | str | rule mechanics (thresholds, lookbacks) |
| risk_management, position_sizing | str | as documented |
| data_requirements | list[str] | canonical names: ohlcv, volume, order_book_snapshots, trades, funding_rates, futures_basis, liquidations, cross_sectional_universe |
| transaction_cost_assumptions | str | costs modeled or "not discussed" |
| market_regime_conditions | str | when the effect holds |
| reported_metrics | dict | Sharpe, returns, hit rate as reported |
| limitations | list[str] | caveats, in-sample choices, universe limits |
| implementation_complexity | str | low / medium / high |
| crypto_transferability | str | direct / adaptation_required / not_transferable_latency_edge |
| hft_or_low_latency_dependency | bool | **hard-policy field** (docs/09) |
| non_applicable_reason | str | `requires_hft_or_low_latency_edge` when flagged |
| backtestability | enum | high / medium / low / not_backtestable |
| falsification_tests | list[str] | what would disprove the idea |
| notes | str | anything else useful |

## Example (abridged; full file: `examples/sample_extraction.json`)

```json
{
  "title": "Volatility Regime Conditioning of Intraday Momentum in Crypto Markets",
  "strategy_style": "volatility_regime",
  "timeframe": "1m-15m",
  "alpha_mechanism": "Volatility regimes condition the profitability of directional signals...",
  "data_requirements": ["ohlcv", "volume", "funding_rates", "futures_basis"],
  "hft_or_low_latency_dependency": false,
  "backtestability": "high",
  "falsification_tests": [
    "signal has no predictive power out-of-sample",
    "edge disappears after realistic fees and slippage"
  ]
}
```

A bad extraction ("This paper discusses market efficiency and machine
learning.") fails the platform's purpose; extractors must produce mechanics
(regime definitions, thresholds, horizons) or leave fields empty and lower
`backtestability` — validators reject hypotheses downstream if the logic
stays vague.
