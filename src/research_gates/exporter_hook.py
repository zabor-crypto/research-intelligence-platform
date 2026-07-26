"""Pure, DB-free cost-gate hook for the export path.

Lives in `research_gates` (no `research_intel.storage` dependency) so it can be
unit-tested straight from the bundle. `research_intel.hypotheses.exporter` imports
`enforce_cost_gate_export_hook` from here and calls it inside `export_backtest_spec`.

Rules (unchanged):
- no `cost_gate_record` and no `requires_cost_gate` → None (legacy, no enforcement)
- `requires_cost_gate=true` without a record → `blocked_missing_cost_gate`
- `cost_gate_record` present → `enforce_cost_gate_before_export(...)`
- a false `export_allowed` → the caller must block the export
- `conditional_after_data` never permits export (only current pass_fail_status matters)
- invalid cost-gate status raises
"""

from __future__ import annotations

from research_gates.promotion_guard import enforce_cost_gate_before_export


def enforce_cost_gate_export_hook(candidate_payload: dict) -> dict | None:
    """Return the cost-gate export guard for a candidate payload, or ``None`` for
    legacy candidates that neither carry a ``cost_gate_record`` nor set
    ``requires_cost_gate`` (backward-compatible). Pure and DB-free."""
    candidate_payload = candidate_payload or {}
    has_record = candidate_payload.get("cost_gate_record") is not None
    requires = bool(candidate_payload.get("requires_cost_gate"))
    if not has_record and not requires:
        return None
    candidate = {
        "candidate_id": candidate_payload.get("candidate_id")
        or candidate_payload.get("hypothesis_id"),
        "component_id": candidate_payload.get("component_id"),
    }
    return enforce_cost_gate_before_export(candidate, candidate_payload.get("cost_gate_record"))
