# Compact Claude Task Template

**Since:** v0.6.10

Use this template to author a research-pipeline task without restating the safety
constraints, release procedure, or report structure. The four config artifacts carry
all of that; the task only supplies its own logic.

## Template

```text
Research Pipeline vX.Y.Z — <task title>

Base:
  repo: <repository-url>
  base tag: research-pipeline-vX.Y.(Z-1)
  base commit: <commit>

Inherit and enforce operator_safety_contract.yaml.
Use compact_release_checklist.yaml.
Use compact_outcome_schema.yaml.
Follow test_execution_policy.md.

Only specify task-specific logic below.
─────────────────────────────────────────────
<task-specific goal>
<task-specific modules / files to add or change>
<task-specific tests to add>
<task-specific artifacts to emit (compact only)>
```

## What "inherit and enforce" means

By writing the four lines above, the task automatically carries:

1. **All safety boundaries** — no A-spec / candidate / handoff / testing / backtest /
   deployment / capital; no dataset/VPS/cron/systemd mutation; no secret printing; no
   force-push / force-tag-update / prior-tag mutation. See
   [`operator_safety_contract.md`](operator_safety_contract.md). These do **not** need
   to be re-listed in the task body.
2. **The release gates** — preflight, changed-file scope, artifact verification, test
   policy, tag policy, no-promotion, security. See
   [`compact_release_checklist.md`](compact_release_checklist.md).
3. **The outcome shape** — a compact outcome with `no_promotion`, `security`,
   `release_safety`, and `tests` blocks that the validator checks. See
   [`compact_outcome_schema.md`](compact_outcome_schema.md).
4. **The test depth per phase** — targeted+regression while implementing, full suite
   once pre-release, git/tag verification at publish, ruff always. See
   [`test_execution_policy.md`](test_execution_policy.md).

## Enforcement at release

The task's outcome is validated in code before it is recommended for accept:

```python
from research_pipeline.source_discovery import operator_contract as OC

check = OC.validate_release_outcome_against_contract(outcome)
assert check.ok, check.violations
```

If `check.ok` is false, the release is `fix_*`, not `accept_*`.

## Compact reports only

Emit only the compact release artifacts (`README.md`, `<...>_outcome.json`,
`<...>_change_manifest.json`, plus at most a short contract/feature report). Do **not**
produce large repeated demo reports — the schema + validator replace them.
