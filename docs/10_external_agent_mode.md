# External Agent Mode

File-based LLM operation without any API calls or billing: the platform
prepares work packets, an external agent (typically Claude Code) reads them
and writes structured outputs, and the platform imports, validates, gates,
scores, and reports. Enable with:

```env
LLM_PROVIDER=external_agent
```

In this mode API-driven commands (`extract-all`, `generate-hypotheses`,
`score`) refuse to run and point to the workflow below. No key is required.

## 1. Generate packets

```bash
research-intel prepare-agent-batch \
  --input eval_sources/batch_v1 \
  --out agent_work_packets/batch_v1
```

Each `agent_work_packets/<batch>/<packet_id>/` contains `source.md`,
`metadata.json`, `extraction_schema.json`, `hypothesis_schema.json`,
`scoring_schema.json`, `instructions.md`, `expected_outputs.json`.

## 2. How the agent processes a packet

For each packet, the agent reads `instructions.md` (rendered from
`prompts/external_agent_packet_instructions.md`) and `source.md`, then writes
into a mirrored `agent_outputs/<batch>/<packet_id>/`:

- `extraction.json` (must validate against `extraction_schema.json`)
- `hypothesis.json` (must validate against `hypothesis_schema.json`)
- `score.json` (advisory; platform recomputes by default)
- `backtest_spec.md` (only for export-eligible candidates)
- `rejection_reason.md` (for review_only / rejected outputs)

The instructions enforce the anti-hallucination contract: source-faithful
extraction, no invented parameters, provenance-labeled defaults, concrete
rules, source universe/risk/cost preservation, non-HFT classification,
review_only for vague sources, entry-condition preservation, and spec
consistency.

## 3. Import outputs

```bash
research-intel import-agent-outputs --path agent_outputs/batch_v1
# add --trust-agent-score to use the agent's (validated) dimension scores
```

Import rules:
1. All JSON validated with the current pydantic schemas; failures logged to
   `reports/agent_import_errors.jsonl` (never abort the batch).
2. Sources/documents/extractions/hypotheses stored in SQLite with
   platform-authoritative ids.
3. **Every existing gate re-runs in code** via the same `admit_hypothesis()`
   path as LLM generation: grounding, HFT (unconditional), parameterization,
   archetype fidelity, source-fact fidelity, entry-condition fidelity, spec
   consistency. Gate violations demote/reject regardless of what the agent
   claimed.
4. Scores are recomputed internally by default; `--trust-agent-score` uses
   the agent's dimensions but hard filters and weighting still run in code.
5. Re-importing the same packet is a logged skip, not a duplicate.

## 4. Evaluate a batch

```bash
research-intel evaluate-agent-batch \
  --outputs agent_outputs/batch_v1 \
  --report-dir reports/eval_batch_v1_external_agent
```

Produces: `source_inventory.csv`, `manual_grading_table.csv` (grade column to
fill by hand), `manual_grading_report.md`, `failure_analysis.md`,
`ranked_candidates.{md,csv,jsonl}`, `research_digest.md`,
`agent_import_errors.jsonl`, and `top_A_candidates/` (gate-passing candidates
with hypothesis/score JSON + backtest spec), `top_B_candidates/` (for manual
B-grades), `rejected_or_review_only/`. Specs are exported only for
hypotheses satisfying: status=candidate, both export flags true,
source/partially-source parameterized, archetype fidelity strong/partial,
spec consistency strong, entry-condition fidelity strong/partial.

## 5. Auditing final reports

- `manual_grading_table.csv`: grade every hypothesis A/B/C/D
  (A = backtest-ready with source facts preserved; B = promising, minor
  manual refinement; C = weak/abstract; D = HFT / unfalsifiable / fabricated /
  contradicting source facts).
- `agent_import_errors.jsonl`: every schema/validation failure with stage,
  packet, reason, file path.
- `rejected_or_review_only/*_hypothesis.json`: check `missing_for_backtest`,
  `dropped_entry_conditions`, `consistency_failures` to see exactly why an
  output was gated.
- Cross-check exported specs against `source.md` in the corresponding packet
  — the spec must be implementable without re-reading the source, and no
  section may contradict the Source Risk & Cost Facts block.

## Guarantees

No gate is loosened in this mode; external outputs get *more* scrutiny than
internal ones (schema validation at the file boundary plus full gate re-run).
The platform never calls an LLM API while `LLM_PROVIDER=external_agent`.
