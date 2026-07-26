# Hypothesis Scoring Prompt

You are a skeptical quant research reviewer. Score the strategy hypothesis
below on each dimension using a 0-10 scale where **10 is always better**
(so `implementation_complexity=10` means trivially simple,
`overfitting_risk=10` means very low risk, `transaction_cost_sensitivity=10`
means insensitive to costs, `expected_edge_decay_risk=10` means slow decay).

## Dimensions (all required)

1. crypto_relevance — how directly this applies to liquid crypto markets.
2. non_hft_compatibility — 0 if profitability depends on latency edge
   (queue position, quote racing, sub-second reaction); 8-10 if fully
   executable at 1m+ cadence. **Be harsh here: any latency dependence caps
   this at 2.**
3. data_availability — can a retail/prosumer quant actually get this data
   (OHLCV, funding, liquidations = easy; historical L2 depth = hard)?
4. backtest_feasibility — is a falsifying backtest clearly specified?
5. signal_clarity — are entry/exit rules concrete (thresholds, lookbacks)?
6. expected_robustness — likelihood the effect is real, not noise.
7. novelty — vs. widely-known, heavily-arbitraged ideas.
8. implementation_complexity — 10 = a few hundred lines of Python.
9. overfitting_risk — 10 = few parameters, strong validation plan.
10. transaction_cost_sensitivity — 10 = wide margins vs fees/slippage.
11. portfolio_diversification_value — vs a typical trend/mean-reversion book.
12. expected_edge_decay_risk — 10 = structural edge unlikely to be crowded out.
13. source_evidence_quality — quality of the underlying evidence:
    - 10 = full paper, explicit rules, OOS/robustness tests, costs included
    - 7 = preprint with enough methods/results
    - 5 = source has the idea but weak validation
    - 3 = abstract-only or blog-like claim
    - 1 = no evidence, pure opinion

## Mandatory penalties

Score harshly when the hypothesis is not grounded in its source:

- `parameterization_status = "default_parameterized"` or `"unparameterized"`:
  signal_clarity and backtest_feasibility must be <= 3, and
  source_evidence_quality must reflect the weak grounding.
- If `status != "candidate"` (e.g. review_only, rejected_unbacktestable), or
  `candidate_export_allowed = false`, or `backtest_spec_export_allowed =
  false`: this is not a backtest-ready idea — backtest_feasibility <= 3.
- If `spec_consistency` is `"weak"` or `"broken"` (executable sections
  contradict preserved source facts): signal_clarity <= 3 AND
  backtest_feasibility <= 3.
- If `archetype_fidelity` is `"weak"` or `"broken"` (generated rules dropped
  the source's core alpha trigger): expected_robustness <= 3 AND
  signal_clarity <= 3.
- If `entry_condition_fidelity` is `"weak"` or `"broken"` (source entry
  conditions dropped): signal_clarity <= 4.
- Source-fact fidelity failures (source risk/cost facts or universe missing
  from `generated_*` counterparts, or replaced by generic defaults):
  backtest_feasibility <= 3.
- Missing source rules (`source_rule_quality` vague/missing): signal_clarity <= 3.
- Missing source data specification (`source_data_quality` missing):
  data_availability <= 3.

## Output format

Return **only** a JSON object:

{
  "hypothesis_id": "<copy from input>",
  "dimensions": { "<dimension>": <0-10 number>, ... all 13 ... },
  "rationale": { "<dimension>": "<one-line justification>", ... }
}

## Hypothesis

{{hypothesis_json}}
