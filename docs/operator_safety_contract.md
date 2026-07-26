# Operator Safety Contract

**Config:** [`research_pipeline_config/operator_safety_contract.yaml`](../research_pipeline_config/operator_safety_contract.yaml)
**Validator:** `src/research_pipeline/source_discovery/operator_contract.py`
**Since:** v0.6.10

## Why this exists

By v0.6.9 every research-pipeline task and release prompt was re-stating the same
safety constraints — the no-promotion boundaries, the read-only data posture, the
release/tag rules. That repetition made prompts and release tasks large, slow, and
expensive, and every restatement is a chance to weaken a boundary by accident.

The operator safety contract is the **single source of truth** for those boundaries.
A task now inherits it by reference instead of copying it, and its release outcome is
validated against it in code. Reducing token/time cost — **without weakening safety**.

## What the contract guarantees

### No-promotion boundaries

Nothing in the research pipeline may advance a source toward capital without an
explicit, validated operator decision. Each field defaults to "no":

| Boundary | Default |
|---|---|
| `a_spec_created` | false |
| `a_spec_approved` | false |
| `handoff_candidates_later` | 0 |
| `handoff_recommended_now` | false |
| `handoff_intake_launched` | false |
| `new_candidate_launched` | false |
| `testing_stage_launched` | false |
| `backtest_started` | false |
| `deployment_authorized` | false |
| `capital_authorized` | false |

A `*_by_default` / `0_by_default` sentinel means: the outcome must report that default
**unless** an explicit operator decision flips it. Task-specific instructions can never
imply the flip; only a recorded operator decision can.

### Data safety (absolute — no override)

| Rule | Value |
|---|---|
| `local_dataset_mutation_allowed` | false |
| `remote_dataset_mutation_allowed` | false |
| `vps_file_mutation_allowed` | false |
| `cron_systemd_service_mutation_allowed` | false |
| `secret_printing_allowed` | false |

There is no operator-decision override for data safety. A task that genuinely needs a
mutation is a different task governed by a different contract.

### Release safety (append-only history)

| Rule | Value |
|---|---|
| `force_push_allowed` | false |
| `force_tag_update_allowed` | false |
| `prior_tag_mutation_allowed` | false |

## How a task uses it

A task prompt states:

```text
Inherit and enforce operator_safety_contract.yaml.
```

and its release outcome carries `no_promotion`, `security`, and `release_safety`
blocks. At release time the validators confirm the outcome satisfies the contract:

```python
from research_pipeline.source_discovery import operator_contract as OC

contract = OC.load_operator_safety_contract()
OC.validate_no_promotion_against_contract(outcome["no_promotion"], contract)
OC.validate_security_against_contract(outcome["security"], contract)
OC.validate_release_outcome_against_contract(outcome, contract)   # shape + all safety
```

Each returns a `ContractCheck` with `.ok` and `.violations`.

### Operator-decision escape hatch (no-promotion only)

If — and only if — the operator has made an explicit decision to cross a no-promotion
boundary, the outcome attaches:

```json
"operator_decisions": {
  "a_spec_created": {
    "decided_by": "operator",
    "decision": true,
    "rationale": "…explicit validated reason…"
  }
}
```

Absent a well-formed decision (with `decided_by` and `rationale`), any crossed boundary
is a violation. Data-safety and release-safety have **no** escape hatch.

## Related

- [`compact_release_checklist.md`](compact_release_checklist.md) — the reusable release gates.
- [`compact_outcome_schema.md`](compact_outcome_schema.md) — the outcome shape the validator checks.
- [`test_execution_policy.md`](test_execution_policy.md) — how much testing each phase requires.
- [`compact_claude_task_template.md`](compact_claude_task_template.md) — the compact task prompt.
