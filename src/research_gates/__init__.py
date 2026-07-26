"""Reusable research gates for the Research Intelligence Platform.

Currently: the Execution / Cost Feasibility Gate — a pre-backtest screen that
decides whether a candidate strategy may proceed to A-spec / backtest based on
turnover, cost assumptions, gross-edge units, and liquidity-data availability.
Not a backtester; produces no strategy P&L.
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
    REQUIRED_FIELDS,
    classify_cost_gate,
    cost_per_rebalance_bps,
    estimate_break_even_cost_bps,
    estimate_rebalance_turnover,
    estimate_round_trip_cost_bps,
    next_steps_for_status,
    validate_gate_record,
)
from research_gates.exporter_hook import enforce_cost_gate_export_hook
from research_gates.pipeline_admission import (
    ALL_ADMISSION_DECISIONS,
    admit_after_cost_gate,
)
from research_gates.promotion_guard import enforce_cost_gate_before_export
from research_gates.side_liquidity_gate import (
    GATE_ID as SIDE_LIQUIDITY_GATE_ID,
)
from research_gates.side_liquidity_gate import (
    CandidateAdmission,
    LegResult,
    SideLiquidityContract,
    evaluate_leg,
    evaluate_market_neutral,
    required_book_side,
    required_book_side_for,
)

__all__ = [
    "ALL_ADMISSION_DECISIONS",
    "admit_after_cost_gate",
    "enforce_cost_gate_before_export",
    "enforce_cost_gate_export_hook",
    "SIDE_LIQUIDITY_GATE_ID",
    "SideLiquidityContract",
    "CandidateAdmission",
    "LegResult",
    "evaluate_leg",
    "evaluate_market_neutral",
    "required_book_side",
    "required_book_side_for",
    "ALL_STATUSES",
    "COST_GATE_PASS",
    "COST_GATE_PASS_CAPACITY_LIMITED",
    "COST_GATE_NEEDS_DATA",
    "COST_GATE_FAIL_COST_HURDLE",
    "COST_GATE_FAIL_MISSING_EXEC",
    "COST_GATE_FAIL_TURNOVER",
    "COST_GATE_FAIL_MISSING_LIQUIDITY",
    "REQUIRED_FIELDS",
    "classify_cost_gate",
    "cost_per_rebalance_bps",
    "estimate_break_even_cost_bps",
    "estimate_rebalance_turnover",
    "estimate_round_trip_cost_bps",
    "next_steps_for_status",
    "validate_gate_record",
]
