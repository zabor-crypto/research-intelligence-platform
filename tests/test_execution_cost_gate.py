"""Tests for the reusable Execution / Cost Feasibility Gate. Pure logic, no data."""

from __future__ import annotations

import pytest

from research_gates import (
    COST_GATE_FAIL_COST_HURDLE,
    COST_GATE_FAIL_MISSING_LIQUIDITY,
    COST_GATE_NEEDS_DATA,
    COST_GATE_PASS,
    COST_GATE_PASS_CAPACITY_LIMITED,
    REQUIRED_FIELDS,
    classify_cost_gate,
    estimate_break_even_cost_bps,
    estimate_rebalance_turnover,
    estimate_round_trip_cost_bps,
    next_steps_for_status,
    validate_gate_record,
)


def _passing_rec(**over):
    rec = {
        "gross_edge_convertible": True,
        "fee_model_status": "assumed",
        "spread_model_status": "assumed",
        "slippage_model_status": "assumed",
        "depth_model_status": "assumed",
        "capacity_model_status": "adequate",
        "turnover_status": "ok",
        "break_even_cost_bps": 40.0,
        "tested_cost_bps": 20.0,
    }
    rec.update(over)
    return rec


# --- high turnover / gross edge < cost -> cost hurdle -----------------------
def test_high_turnover_fails_when_edge_below_cost():
    # break-even (edge-absorbable cost) below the tested cost -> cost hurdle
    rec = _passing_rec(break_even_cost_bps=8.0, tested_cost_bps=20.0)
    assert classify_cost_gate(rec) == COST_GATE_FAIL_COST_HURDLE


# --- missing depth model ----------------------------------------------------
def test_missing_depth_model_blocks():
    rec = _passing_rec(depth_model_status="missing")
    assert classify_cost_gate(rec) in {COST_GATE_FAIL_MISSING_LIQUIDITY, COST_GATE_NEEDS_DATA}
    # with convertible edge + exec present, it is specifically a liquidity-data fail
    assert classify_cost_gate(rec) == COST_GATE_FAIL_MISSING_LIQUIDITY


def test_unconvertible_edge_is_needs_data():
    rec = _passing_rec(gross_edge_convertible=False)
    assert classify_cost_gate(rec) == COST_GATE_NEEDS_DATA


# --- capacity limited is not a clean pass -----------------------------------
def test_capacity_limited_not_clean_pass():
    rec = _passing_rec(capacity_model_status="limited")
    status = classify_cost_gate(rec)
    assert status == COST_GATE_PASS_CAPACITY_LIMITED
    assert status != COST_GATE_PASS


# --- long-short counts both legs -------------------------------------------
def test_long_short_counts_both_legs():
    t = estimate_rebalance_turnover(names_per_leg=3, n_legs=2, replacement_fraction=1.0)
    assert t["n_legs"] == 2
    assert t["one_way_turnover"] == 1.0            # full rotation of the gross book
    assert t["round_trip_turnover"] == 2.0         # enter + exit
    # partial replacement + weight churn on retained names
    p = estimate_rebalance_turnover(3, 2, replacement_fraction=1 / 3, rank_weight_churn=0.15)
    assert 0.30 < p["one_way_turnover"] < 0.55


# --- zero-cost never passes by itself ---------------------------------------
def test_zero_cost_never_passes():
    rec = _passing_rec(tested_cost_bps=0.0)
    assert classify_cost_gate(rec) == COST_GATE_NEEDS_DATA
    assert classify_cost_gate(rec) != COST_GATE_PASS


# --- break-even bps ---------------------------------------------------------
def test_break_even_calc():
    # edge 36 bps/rebalance, round-trip turnover 0.86 -> break-even ~41.9 bps
    be = estimate_break_even_cost_bps(36.0, 0.86)
    assert be is not None and abs(be - 41.86) < 0.1
    # unconvertible edge -> None (forces needs_data)
    assert estimate_break_even_cost_bps(None, 0.86) is None
    # round-trip cost helper
    assert estimate_round_trip_cost_bps(1.5, 1.0, 0.5) == 6.0


# --- schema-required fields -------------------------------------------------
def test_schema_required_fields_validation():
    ok, missing = validate_gate_record({"candidate_id": "x"})
    assert not ok and len(missing) == len(REQUIRED_FIELDS) - 1
    full = {f: "x" for f in REQUIRED_FIELDS}
    full["pass_fail_status"] = COST_GATE_NEEDS_DATA
    ok2, missing2 = validate_gate_record(full)
    assert ok2 and not missing2
    # bad status flagged
    full["pass_fail_status"] = "bogus"
    ok3, missing3 = validate_gate_record(full)
    assert not ok3 and any("invalid:pass_fail_status" in m for m in missing3)


# --- allowed / forbidden next steps consistency -----------------------------
def test_next_steps_consistency():
    # a pass allows A-spec; every status forbids deploying capital
    p = next_steps_for_status(COST_GATE_PASS)
    assert p["allowed_next_step"] == "proceed_to_A_spec"
    assert "deploy_capital" in p["forbidden_next_steps"]
    # non-pass statuses forbid going straight to backtest / clean A-spec
    for s in (COST_GATE_NEEDS_DATA, COST_GATE_FAIL_COST_HURDLE, COST_GATE_FAIL_MISSING_LIQUIDITY):
        ns = next_steps_for_status(s)
        assert "proceed_to_backtest" in ns["forbidden_next_steps"]
        assert "clean_A_spec" in ns["forbidden_next_steps"]
        assert ns["allowed_next_step"] != "proceed_to_A_spec"
    with pytest.raises(ValueError):
        next_steps_for_status("not_a_status")
