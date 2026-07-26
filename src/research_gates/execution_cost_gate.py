"""Execution / Cost Feasibility Gate — reusable, dependency-light.

A pre-backtest screen: given a candidate's turnover, cost assumptions, gross-edge
units, and liquidity-data availability, decide whether it may proceed to A-spec /
backtest — WITHOUT running a backtest and WITHOUT generating strategy P&L.

This is deliberately NOT a backtester. It provides small deterministic helpers and
a rule-based classifier so the platform stops spending full replication effort on
strategies whose gross edge cannot plausibly survive turnover × cost.

Conventions (documented so downstream readers can't misread the numbers):
- `turnover` is expressed as a fraction of GROSS book traded ONE-WAY per rebalance.
  `round_trip_turnover = 2 * one_way` (enter + later exit).
- `round_trip_cost_bps` = 2 * (fee + half_spread + slippage) per side.
- `cost_per_rebalance_bps` (of gross) = one_way_turnover * round_trip_cost_bps.
- All figures are feasibility ESTIMATES, not measured backtest results.
"""

from __future__ import annotations

# ---- statuses ----
COST_GATE_PASS = "cost_gate_pass"
COST_GATE_PASS_CAPACITY_LIMITED = "cost_gate_pass_but_capacity_limited"
COST_GATE_NEEDS_DATA = "cost_gate_needs_data"
COST_GATE_FAIL_COST_HURDLE = "cost_gate_fail_cost_hurdle"
COST_GATE_FAIL_MISSING_EXEC = "cost_gate_fail_missing_execution_model"
COST_GATE_FAIL_TURNOVER = "cost_gate_fail_turnover"
COST_GATE_FAIL_MISSING_LIQUIDITY = "cost_gate_fail_missing_liquidity_data"

ALL_STATUSES = (
    COST_GATE_PASS,
    COST_GATE_PASS_CAPACITY_LIMITED,
    COST_GATE_NEEDS_DATA,
    COST_GATE_FAIL_COST_HURDLE,
    COST_GATE_FAIL_MISSING_EXEC,
    COST_GATE_FAIL_TURNOVER,
    COST_GATE_FAIL_MISSING_LIQUIDITY,
)

# required fields for a gate record (mirrors execution_cost_gate_schema.yaml)
REQUIRED_FIELDS = (
    "candidate_id",
    "component_id",
    "strategy_family",
    "source_logic_status",
    "expected_holding_period",
    "rebalance_frequency",
    "estimated_turnover_per_period",
    "legs_per_rebalance",
    "gross_edge_estimate",
    "gross_edge_source",
    "fee_model_status",
    "spread_model_status",
    "slippage_model_status",
    "depth_model_status",
    "capacity_model_status",
    "required_cost_assumption",
    "break_even_cost_bps",
    "tested_cost_bps",
    "pass_fail_status",
    "blocking_issues",
    "allowed_next_step",
    "forbidden_next_steps",
    "notes",
)

_MISSING = {"missing", "unknown", "none", "absent", None, ""}


# ---------------------------------------------------------------------------
# deterministic helpers
# ---------------------------------------------------------------------------
def estimate_rebalance_turnover(
    names_per_leg: int,
    n_legs: int,
    replacement_fraction: float,
    rank_weight_churn: float = 0.0,
) -> dict[str, float]:
    """One-way turnover (fraction of GROSS book) per rebalance for a rank-weighted
    long/short book, counting ALL legs.

    - `replacement_fraction`: fraction of names swapped out (0=no change, 1=full).
    - `rank_weight_churn`: weight drift on RETAINED names (0..1).
    Returns one_way and round_trip_equiv turnover. Both legs are counted (a
    dollar-neutral long/short book trades on both sides), so n_legs scales nothing
    beyond confirming a 2-sided book; the fraction is already of total gross.
    """
    if names_per_leg <= 0 or n_legs <= 0:
        raise ValueError("names_per_leg and n_legs must be positive")
    replacement_fraction = max(0.0, min(1.0, replacement_fraction))
    rank_weight_churn = max(0.0, min(1.0, rank_weight_churn))
    one_way = replacement_fraction + (1.0 - replacement_fraction) * rank_weight_churn
    return {
        "names_per_leg": names_per_leg,
        "n_legs": n_legs,
        "one_way_turnover": round(one_way, 6),
        "round_trip_turnover": round(2.0 * one_way, 6),
    }


def estimate_round_trip_cost_bps(
    fee_bps_per_side: float, half_spread_bps: float, slippage_bps_per_side: float
) -> float:
    """Round-trip execution cost in bps = 2 * (fee + half_spread + slippage)."""
    per_side = fee_bps_per_side + half_spread_bps + slippage_bps_per_side
    return round(2.0 * per_side, 6)


def estimate_break_even_cost_bps(
    gross_edge_bps_per_period: float | None, round_trip_turnover: float
) -> float | None:
    """Max round-trip cost (bps) the gross edge can absorb before net<=0.

    net = gross_edge - cost_bps * round_trip_turnover  ->  break_even = edge / turnover.
    Returns None when the gross edge is not available in bps (IR/Sharpe units) — the
    caller must then classify `cost_gate_needs_data`, NOT pass.
    """
    if gross_edge_bps_per_period is None:
        return None
    if round_trip_turnover <= 0:
        return float("inf")
    return round(gross_edge_bps_per_period / round_trip_turnover, 6)


def cost_per_rebalance_bps(one_way_turnover: float, round_trip_cost_bps: float) -> float:
    """Cost per rebalance in bps of gross = one_way_turnover * round_trip_cost_bps."""
    return round(one_way_turnover * round_trip_cost_bps, 6)


# ---------------------------------------------------------------------------
# classifier
# ---------------------------------------------------------------------------
def classify_cost_gate(rec: dict) -> str:
    """Rule-based cost-gate status from a (partial) gate record. Precedence:

    1. gross edge not convertible to bps/period -> needs_data (can't screen cost)
    2. fee/spread/slippage model missing -> fail_missing_execution_model
    3. depth/liquidity model missing -> fail_missing_liquidity_data
    4. turnover flagged excessive -> fail_turnover
    5. break_even < tested cost (edge can't absorb cost) -> fail_cost_hurdle
    6. tested cost <= 0 (zero-cost cannot certify) -> needs_data
    7. capacity limited -> pass_but_capacity_limited
    8. else -> pass
    """
    if not rec.get("gross_edge_convertible", False):
        return COST_GATE_NEEDS_DATA
    if any(str(rec.get(k)).lower() in _MISSING for k in ("fee_model_status", "spread_model_status", "slippage_model_status")):
        return COST_GATE_FAIL_MISSING_EXEC
    if str(rec.get("depth_model_status")).lower() in _MISSING:
        return COST_GATE_FAIL_MISSING_LIQUIDITY
    if str(rec.get("turnover_status", "")).lower() in {"excessive", "too_high"}:
        return COST_GATE_FAIL_TURNOVER
    tested = float(rec.get("tested_cost_bps") or 0.0)
    be = rec.get("break_even_cost_bps")
    if be is not None and tested > 0 and float(be) < tested:
        return COST_GATE_FAIL_COST_HURDLE
    if tested <= 0:
        return COST_GATE_NEEDS_DATA  # zero-cost diagnostic never passes by itself
    if str(rec.get("capacity_model_status", "")).lower() in {"limited", "capacity_limited"}:
        return COST_GATE_PASS_CAPACITY_LIMITED
    return COST_GATE_PASS


def validate_gate_record(rec: dict, required: tuple[str, ...] = REQUIRED_FIELDS) -> tuple[bool, list[str]]:
    """Return (ok, missing_fields). A record is valid if all schema fields present
    and pass_fail_status (if set) is a known status."""
    missing = [f for f in required if f not in rec]
    status = rec.get("pass_fail_status")
    if status is not None and status not in ALL_STATUSES:
        missing.append(f"invalid:pass_fail_status={status}")
    return (not missing, missing)


# next-step policy per status (machine-usable by the parser/tester pipeline)
_PASS_LIKE = {COST_GATE_PASS, COST_GATE_PASS_CAPACITY_LIMITED}
_FORBIDDEN_ALWAYS = ("deploy_capital", "skip_cost_kill_criteria")


def next_steps_for_status(status: str) -> dict[str, object]:
    """Allowed next step + forbidden next steps for a cost-gate status.

    A non-pass status may never lead straight to backtest/A-spec; every status
    forbids deploying capital and skipping cost-kill criteria.
    """
    if status not in ALL_STATUSES:
        raise ValueError(f"unknown status {status!r}")
    if status == COST_GATE_PASS:
        allowed = "proceed_to_A_spec"
    elif status == COST_GATE_PASS_CAPACITY_LIMITED:
        allowed = "proceed_to_A_spec_small_size_only"
    elif status == COST_GATE_NEEDS_DATA:
        allowed = "acquire_liquidity_or_edge_unit_data_then_re_gate"
    elif status in (COST_GATE_FAIL_MISSING_EXEC, COST_GATE_FAIL_MISSING_LIQUIDITY):
        allowed = "build_execution_or_liquidity_model_then_re_gate"
    else:  # cost_hurdle / turnover
        allowed = "park_or_redesign_construction"
    forbidden = list(_FORBIDDEN_ALWAYS)
    if status not in _PASS_LIKE:
        forbidden = ["proceed_to_backtest", "clean_A_spec", *forbidden]
    return {"allowed_next_step": allowed, "forbidden_next_steps": forbidden}
