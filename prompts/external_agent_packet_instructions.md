# External Agent Work Packet — {{packet_id}}

You are an external agent (e.g. Claude Code) acting as the LLM operator for
the Research Intelligence Platform. Read `source.md` and produce structured
outputs. **Your outputs are re-validated and re-gated by platform code; a
plausible-looking but ungrounded output will be demoted or rejected.**

## Files in this packet

- `source.md` — the research source (the ONLY ground truth)
- `metadata.json` — packet identity and provenance
- `extraction_schema.json` — JSON Schema for `extraction.json`
- `hypothesis_schema.json` — JSON Schema for `hypothesis.json`
- `scoring_schema.json` — format for `score.json` (advisory: the platform
  recomputes scores internally by default)
- `expected_outputs.json` — machine-readable output list

## Outputs to write (into the matching `agent_outputs/.../{{packet_id}}/`)

- `extraction.json` — structured extraction conforming to `extraction_schema.json`
- `hypothesis.json` — crypto-testable hypothesis conforming to `hypothesis_schema.json`
- `score.json` — 13-dimension 0-10 scores per `scoring_schema.json`
- `backtest_spec.md` — only if status=candidate and both export flags are true
- `rejection_reason.md` — if status is review_only / rejected_hft /
  rejected_unbacktestable: explain why and what the source would need

## Hard requirements (violations are gated, not forgiven)

1. **Source-faithful extraction.** Extract only what `source.md` actually
   states. Every number in `extracted_parameters` must appear in the source.
2. **No invented parameters.** Never invent, round, or substitute values. A
   parameter you did not find must be absent; set `parameter_source_quality`
   honestly (explicit / partially_explicit / inferred / missing).
3. **No generic defaults masquerading as source facts.** Platform defaults are
   allowed only with `parameter_provenance` / `risk_parameter_provenance` /
   `cost_parameter_provenance` = "default". Defaults must never overwrite
   source risk/cost facts.
4. **Concrete entry/exit/risk rules.** At least one entry rule with a
   measurable signal + comparator + threshold + timeframe; exits with
   thresholds/time stops/stop-losses; risk rules with size/stop/vol-target/
   drawdown limits. Prose like "enter when the signal is strong" is rejected.
5. **Source asset universe preservation.** Copy the source's universe into
   `source_asset_universe`; the primary backtest and
   `minimum_viable_backtest` must use it ("Primary: <source universe>");
   broader universes go into `optional_robustness_universe` only.
6. **Risk/cost preservation.** Copy the source's risk and cost numbers into
   `source_risk_parameters` / `source_cost_parameters` and use them in
   `risk_rules`, `position_sizing`, and `fees_slippage_model`.
7. **Non-HFT compatibility classification.** Judge whether profitability
   depends on latency (queue position, same-update reaction, being first in
   the book, edge vanishing when delayed ~1 second/tick). If yes — including
   operational phrasing without classic keywords — set
   `hft_or_low_latency_dependency: true` and
   `non_applicable_reason: "requires_hft_or_low_latency_edge"`.
8. **HFT rejection.** Latency-dependent ideas get `status: "rejected_hft"`,
   `candidate_export_allowed: false`, `backtest_spec_export_allowed: false`,
   and a `rejection_reason.md`. Do not "adapt" a pure-speed edge.
9. **review_only for vague sources.** If the source lacks usable parameters,
   codable rules, or a data path, set `status: "review_only"` (or
   `"rejected_unbacktestable"` when nothing is salvageable), empty
   `strategy_parameters`, export flags false, and list what is missing in
   `missing_for_backtest`. Do not fabricate a template strategy.
10. **Source condition preservation.** List every distinct entry condition
    the source states in `source_entry_conditions` and preserve each one in
    `entry_rules` / `generated_entry_conditions`; report drops honestly in
    `dropped_entry_conditions` and `entry_condition_fidelity`.
11. **Spec consistency.** Executable sections (`position_sizing`,
    `minimum_viable_backtest`) must use the preserved source facts — never
    contradict them with generic values. Self-report in `spec_consistency`,
    `consistency_failures`, `consistency_warnings`.

## After you finish

The operator imports your outputs with:

```bash
research-intel import-agent-outputs --path agent_outputs/<batch>
research-intel evaluate-agent-batch --outputs agent_outputs/<batch> --report-dir reports/<batch>
```

The platform re-runs the HFT, grounding, parameterization, archetype
fidelity, source-fact fidelity, entry-condition fidelity, and spec
consistency gates on your outputs and recomputes scores. Honest review_only
output is worth more than a confident fabrication.
