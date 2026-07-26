# Compact Outcome Schema

**Config:** [`research_pipeline_config/compact_outcome_schema.yaml`](../research_pipeline_config/compact_outcome_schema.yaml)
**Validator:** `operator_contract.py::validate_release_outcome_against_contract`
**Since:** v0.6.10

Future releases emit a **compact** outcome that satisfies this schema instead of
copying a large bespoke report each time. The schema pins the minimum required shape;
task-specific detail can still be added, but the required safety blocks are always
present and always validated.

## Required top-level fields

| Field | Type | Notes |
|---|---|---|
| `schema_version` | str | e.g. `pipeline_outcome/0.6.10` |
| `pipeline_version` | str | e.g. `0.6.10` |
| `base_tag` | str | release base tag |
| `base_commit` | str | release base commit |
| `implementation_status` | str | short status string |
| `no_promotion` | mapping | validated against contract no-promotion boundaries |
| `security` | mapping | validated against contract data-safety |
| `release_safety` | mapping | validated against contract release-safety |
| `tests` | mapping | test summary |
| `lint_status` | str | `clean` \| `issues` |
| `release_recommendation` | str | `accept_*` \| `fix_*` |

## Required block sub-fields

**`no_promotion`** — all ten boundaries:
`a_spec_created`, `a_spec_approved`, `handoff_candidates_later`,
`handoff_recommended_now`, `handoff_intake_launched`, `new_candidate_launched`,
`testing_stage_launched`, `backtest_started`, `deployment_authorized`,
`capital_authorized`.

**`security`** — `local_datasets_modified`, `remote_files_modified`,
`vps_files_modified`, `cron_modified`, `systemd_modified`,
`secrets_printed_or_stored`.

**`release_safety`** — `force_push`, `force_tag_update`, `prior_tag_mutation`.

**`tests`** — `total_passed`, `total_failed`, `command`.

## Validation semantics

`validate_release_outcome_against_contract(outcome)` checks, in order:

1. Every required top-level field is present and correctly typed.
2. Every required sub-field is present in each safety block.
3. `no_promotion` satisfies the contract (bools false, counts 0, unless an explicit
   `operator_decisions` entry authorizes it).
4. `security` satisfies the contract data-safety rules (all false; no override).
5. `release_safety` satisfies the contract (all false).

It returns a `ContractCheck` aggregating every violation, so a fixer sees the whole
list at once rather than one failure at a time.

## Minimal valid example

```json
{
  "schema_version": "pipeline_outcome/0.6.10",
  "pipeline_version": "0.6.10",
  "base_tag": "research-pipeline-v0.6.9",
  "base_commit": "b0ffc60…",
  "implementation_status": "operator_contract_and_compact_release_workflow",
  "no_promotion": {
    "a_spec_created": false, "a_spec_approved": false,
    "handoff_candidates_later": 0, "handoff_recommended_now": false,
    "handoff_intake_launched": false, "new_candidate_launched": false,
    "testing_stage_launched": false, "backtest_started": false,
    "deployment_authorized": false, "capital_authorized": false
  },
  "security": {
    "local_datasets_modified": false, "remote_files_modified": false,
    "vps_files_modified": false, "cron_modified": false,
    "systemd_modified": false, "secrets_printed_or_stored": false
  },
  "release_safety": {
    "force_push": false, "force_tag_update": false, "prior_tag_mutation": false
  },
  "tests": {"total_passed": 0, "total_failed": 0, "command": "python -m pytest -q"},
  "lint_status": "clean",
  "release_recommendation": "accept_v0.6.10"
}
```

## Related
- [`operator_safety_contract.md`](operator_safety_contract.md)
- [`compact_release_checklist.md`](compact_release_checklist.md)
