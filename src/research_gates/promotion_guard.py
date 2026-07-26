"""Promotion guard: enforce the Execution / Cost Feasibility Gate at export time.

`enforce_cost_gate_before_export` is the chokepoint any A-spec / backtest-spec /
bounded-replication / handoff producer must call. No candidate may move from
research/deconstruction into an executable research artifact unless the returned
`export_allowed` is True.

Hard rules:
- missing gate_record            -> export_allowed False (blocked_missing_cost_gate)
- cost_gate_needs_data           -> export_allowed False (blocked_pending_data)
- any cost_gate_fail_*           -> export_allowed False (rejected_*)
- cost_gate_pass                 -> export_allowed True
- cost_gate_pass_but_capacity_limited -> export_allowed True, export_scope capacity_limited_A_spec_only
- conditional_after_data never permits export (only current pass_fail_status matters)
- deploy_capital / skip_cost_kill_criteria always forbidden
"""

from __future__ import annotations

from research_gates.pipeline_admission import (
    ADMIT_A_SPEC,
    ADMIT_A_SPEC_CAPACITY_LIMITED,
    BLOCK_PENDING_DATA,
    REJECT_COST_HURDLE,
    REJECT_MISSING_EXEC,
    REJECT_MISSING_LIQUIDITY,
    REJECT_TURNOVER,
    admit_after_cost_gate,
)

BLOCK_MISSING_COST_GATE = "block_missing_cost_gate"

_ADMIT_LIKE = {ADMIT_A_SPEC, ADMIT_A_SPEC_CAPACITY_LIMITED}

# admission_decision -> machine-readable export reason code
_REASON_CODE = {
    ADMIT_A_SPEC: "cost_gate_admitted",
    ADMIT_A_SPEC_CAPACITY_LIMITED: "cost_gate_admitted_capacity_limited",
    BLOCK_PENDING_DATA: "blocked_pending_data",
    REJECT_COST_HURDLE: "rejected_cost_hurdle",
    REJECT_MISSING_EXEC: "rejected_missing_execution_model",
    REJECT_TURNOVER: "rejected_turnover",
    REJECT_MISSING_LIQUIDITY: "rejected_missing_liquidity_data",
    BLOCK_MISSING_COST_GATE: "blocked_missing_cost_gate",
}

_BASE_FORBIDDEN = ("clean_A_spec", "proceed_to_backtest", "deploy_capital", "skip_cost_kill_criteria")


def enforce_cost_gate_before_export(candidate: dict, gate_record: dict | None) -> dict:
    """Decide whether a candidate may be exported into an executable research artifact,
    based on its current cost-gate record. See module docstring for the rules."""
    candidate = candidate or {}
    cid = candidate.get("candidate_id") or (gate_record or {}).get("candidate_id")
    comp = candidate.get("component_id") or (gate_record or {}).get("component_id")

    if gate_record is None:
        return {
            "candidate_id": cid,
            "component_id": comp,
            "export_allowed": False,
            "admission_decision": BLOCK_MISSING_COST_GATE,
            "cost_gate_status": None,
            "allowed_next_step": "run_cost_gate_first",
            "forbidden_next_steps": list(_BASE_FORBIDDEN),
            "reason": _REASON_CODE[BLOCK_MISSING_COST_GATE],
        }

    adm = admit_after_cost_gate(gate_record)  # raises ValueError on invalid/absent status
    decision = adm["admission_decision"]
    export_allowed = decision in _ADMIT_LIKE

    forbidden = list(dict.fromkeys(adm["forbidden_next_steps"]))
    # deploy_capital + skip_cost_kill_criteria are ALWAYS forbidden, incl. on an admit
    for f in ("deploy_capital", "skip_cost_kill_criteria"):
        if f not in forbidden:
            forbidden.append(f)

    out = {
        "candidate_id": cid,
        "component_id": comp,
        "export_allowed": export_allowed,
        "admission_decision": decision,
        "cost_gate_status": adm["cost_gate_status"],
        "allowed_next_step": adm["allowed_next_step"],
        "forbidden_next_steps": forbidden,
        "reason": _REASON_CODE[decision],
    }
    if decision == ADMIT_A_SPEC_CAPACITY_LIMITED:
        out["export_scope"] = "capacity_limited_A_spec_only"
    # a conditional-future note never permits export; surface it as advisory only
    if gate_record.get("conditional_after_data"):
        out["conditional_after_data_note"] = (
            f"advisory only (does not permit export): {gate_record['conditional_after_data']}"
        )
    return out
