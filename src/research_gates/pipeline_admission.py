"""Pipeline admission for the Execution / Cost Feasibility Gate.

Turns a cost-gate record into a machine-readable admission decision for the RI
parser/tester pipeline. This is the standing stage that sits AFTER the
trade-construction / accounting gates and BEFORE bounded replication:

    ... → trade-construction gate → accounting gate
        → [ cost gate → ADMISSION (this module) ] → bounded replication → registry

Hard rule: `cost_gate_needs_data` is NOT admissible to an A-spec. Only a pass
status admits. A `conditional_after_data` note on a record is advisory only and
NEVER changes the admission decision — only the current `pass_fail_status` does.
"""

from __future__ import annotations

from research_gates.execution_cost_gate import (
    ALL_STATUSES,
    COST_GATE_FAIL_COST_HURDLE,
    COST_GATE_FAIL_MISSING_EXEC,
    COST_GATE_FAIL_MISSING_LIQUIDITY,
    COST_GATE_FAIL_TURNOVER,
    COST_GATE_NEEDS_DATA,
    COST_GATE_PASS,
    COST_GATE_PASS_CAPACITY_LIMITED,
    next_steps_for_status,
)

# admission decisions
ADMIT_A_SPEC = "admit_to_A_spec"
ADMIT_A_SPEC_CAPACITY_LIMITED = "admit_to_A_spec_capacity_limited"
BLOCK_PENDING_DATA = "block_pending_data"
REJECT_COST_HURDLE = "reject_cost_hurdle"
REJECT_MISSING_EXEC = "reject_missing_execution_model"
REJECT_TURNOVER = "reject_turnover"
REJECT_MISSING_LIQUIDITY = "reject_missing_liquidity_data"

ALL_ADMISSION_DECISIONS = (
    ADMIT_A_SPEC,
    ADMIT_A_SPEC_CAPACITY_LIMITED,
    BLOCK_PENDING_DATA,
    REJECT_COST_HURDLE,
    REJECT_MISSING_EXEC,
    REJECT_TURNOVER,
    REJECT_MISSING_LIQUIDITY,
)

_STATUS_TO_DECISION = {
    COST_GATE_PASS: ADMIT_A_SPEC,
    COST_GATE_PASS_CAPACITY_LIMITED: ADMIT_A_SPEC_CAPACITY_LIMITED,
    COST_GATE_NEEDS_DATA: BLOCK_PENDING_DATA,
    COST_GATE_FAIL_COST_HURDLE: REJECT_COST_HURDLE,
    COST_GATE_FAIL_MISSING_EXEC: REJECT_MISSING_EXEC,
    COST_GATE_FAIL_TURNOVER: REJECT_TURNOVER,
    COST_GATE_FAIL_MISSING_LIQUIDITY: REJECT_MISSING_LIQUIDITY,
}

_ADMIT_LIKE = {ADMIT_A_SPEC, ADMIT_A_SPEC_CAPACITY_LIMITED}
# forbidden for every non-pass (non-admit) status
_NON_PASS_FORBIDDEN = ("clean_A_spec", "proceed_to_backtest")
# forbidden for EVERY status, including pass
_ALWAYS_FORBIDDEN = ("deploy_capital", "skip_cost_kill_criteria")

_REASONS = {
    ADMIT_A_SPEC: "cost gate passed; edge absorbs cost at the tested assumption",
    ADMIT_A_SPEC_CAPACITY_LIMITED: "cost gate passed but capacity-limited; small-size A-spec only",
    BLOCK_PENDING_DATA: "cost gate needs data (edge un-unitized and/or liquidity data missing); acquire data and re-gate before any A-spec",
    REJECT_COST_HURDLE: "break-even cost below the tested cost; gross edge cannot absorb realistic cost",
    REJECT_MISSING_EXEC: "no fee/spread/slippage model; execution model must be built before re-gate",
    REJECT_TURNOVER: "turnover-adjusted cost is prohibitive for the available edge",
    REJECT_MISSING_LIQUIDITY: "no depth/liquidity data; fill/capacity assumption cannot be verified",
}


def admit_after_cost_gate(gate_record: dict) -> dict:
    """Map a cost-gate record to a machine-readable admission decision.

    Only the current `pass_fail_status` controls admission. Any
    `conditional_after_data` field is ignored for the decision (surfaced only as
    a note). Raises ValueError on an unknown/absent status.
    """
    status = gate_record.get("pass_fail_status")
    if status not in ALL_STATUSES:
        raise ValueError(f"invalid or missing pass_fail_status: {status!r}")

    decision = _STATUS_TO_DECISION[status]
    steps = next_steps_for_status(status)

    forbidden = list(dict.fromkeys(steps["forbidden_next_steps"]))
    for f in _ALWAYS_FORBIDDEN:  # belt-and-suspenders: always forbidden
        if f not in forbidden:
            forbidden.append(f)
    if decision not in _ADMIT_LIKE:
        for f in _NON_PASS_FORBIDDEN:
            if f not in forbidden:
                forbidden.append(f)

    out = {
        "candidate_id": gate_record.get("candidate_id"),
        "component_id": gate_record.get("component_id"),
        "cost_gate_status": status,
        "admission_decision": decision,
        "allowed_next_step": steps["allowed_next_step"],
        "forbidden_next_steps": forbidden,
        "reason": _REASONS[decision],
    }
    # advisory-only: a conditional-future note NEVER changes the decision
    if gate_record.get("conditional_after_data"):
        out["conditional_after_data_note"] = (
            f"advisory only (not admission): {gate_record['conditional_after_data']} "
            f"— requires a future passing re-gate"
        )
    return out
