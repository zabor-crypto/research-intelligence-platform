# Compact Release Checklist

**Config:** [`research_pipeline_config/compact_release_checklist.yaml`](../research_pipeline_config/compact_release_checklist.yaml)
**Since:** v0.6.10

A reusable release checklist so future tasks do not restate the full release
procedure. A task says "use `compact_release_checklist.yaml`" and works the gates
below. The safety-relevant gates are enforced in code by
`operator_contract.py`; the rest are operator-verified.

## Gates

### 1. Preflight
- Base tag and base commit recorded and match the intended base.
- Working on a task branch, not `main`.
- No unrelated staged/unstaged changes before starting.
- Required tooling present (`python`, `pytest`, `ruff`).

### 2. Changed-file scope
- Every changed file is listed in the change manifest (`files_added` / `files_modified`).
- No prior-release artifact directory amended.
- No dataset, VPS, cron, or systemd file touched.
- No secret, key, or token added to any tracked file.

### 3. Artifact verification
- README, outcome JSON, and change manifest present for the release.
- Every JSON artifact parses.
- Reported counts (records, demos, tests) match the artifacts on disk.

### 4. Test policy
Follows [`test_execution_policy.md`](test_execution_policy.md):
- Implementation phase ran targeted + affected regression tests.
- Pre-release phase ran the full suite once on the final commit.
- Publish phase reused the passing full-suite result for the exact commit.
- `ruff check` run before commit/release.

### 5. Tag policy
- No force-push.
- No force-update of any tag.
- No mutation of a prior released tag.
- A new tag (if any) is created only after the full suite passes on the final commit.

### 6. No-promotion verification
Enforced by `validate_no_promotion_against_contract`:
- No A-spec created or approved.
- No candidate, handoff, or intake launched.
- No testing stage or backtest started.
- No deployment or capital authorized.

### 7. Security verification
Enforced by `validate_security_against_contract`:
- No local dataset mutation.
- No remote / VPS file mutation.
- No cron / systemd / service mutation.
- No secret, key, or token printed or stored.

## Related
- [`operator_safety_contract.md`](operator_safety_contract.md)
- [`compact_outcome_schema.md`](compact_outcome_schema.md)
- [`test_execution_policy.md`](test_execution_policy.md)
