"""Tests for the cost-gate pipeline admission stage."""

from __future__ import annotations

import pytest

from research_gates import admit_after_cost_gate
from research_gates.execution_cost_gate import (
    COST_GATE_FAIL_COST_HURDLE,
    COST_GATE_FAIL_MISSING_LIQUIDITY,
    COST_GATE_NEEDS_DATA,
    COST_GATE_PASS,
    COST_GATE_PASS_CAPACITY_LIMITED,
    classify_cost_gate,
)


def _rec(status, **extra):
    return {"candidate_id": "c", "component_id": "leg", "pass_fail_status": status, **extra}


def test_pass_admits_to_a_spec():
    d = admit_after_cost_gate(_rec(COST_GATE_PASS))
    assert d["admission_decision"] == "admit_to_A_spec"
    # even a pass forbids deploying capital / skipping kill criteria
    assert "deploy_capital" in d["forbidden_next_steps"]
    assert "skip_cost_kill_criteria" in d["forbidden_next_steps"]


def test_capacity_limited_admits_capacity_limited():
    d = admit_after_cost_gate(_rec(COST_GATE_PASS_CAPACITY_LIMITED))
    assert d["admission_decision"] == "admit_to_A_spec_capacity_limited"


def test_needs_data_blocks_and_forbids_a_spec_and_backtest():
    d = admit_after_cost_gate(_rec(COST_GATE_NEEDS_DATA))
    assert d["admission_decision"] == "block_pending_data"
    assert "clean_A_spec" in d["forbidden_next_steps"]
    assert "proceed_to_backtest" in d["forbidden_next_steps"]
    assert d["allowed_next_step"] != "proceed_to_A_spec"


def test_cost_hurdle_rejects():
    d = admit_after_cost_gate(_rec(COST_GATE_FAIL_COST_HURDLE))
    assert d["admission_decision"] == "reject_cost_hurdle"
    assert "proceed_to_backtest" in d["forbidden_next_steps"]


def test_missing_liquidity_rejects():
    d = admit_after_cost_gate(_rec(COST_GATE_FAIL_MISSING_LIQUIDITY))
    assert d["admission_decision"] == "reject_missing_liquidity_data"


def test_zero_cost_diagnostic_cannot_admit():
    # a would-be pass with zero tested cost classifies to needs_data -> block, never admit
    status = classify_cost_gate({
        "gross_edge_convertible": True, "fee_model_status": "assumed",
        "spread_model_status": "assumed", "slippage_model_status": "assumed",
        "depth_model_status": "assumed", "capacity_model_status": "adequate",
        "break_even_cost_bps": 40.0, "tested_cost_bps": 0.0,
    })
    assert status == COST_GATE_NEEDS_DATA
    d = admit_after_cost_gate(_rec(status))
    assert d["admission_decision"] == "block_pending_data"
    assert d["admission_decision"] not in {"admit_to_A_spec", "admit_to_A_spec_capacity_limited"}


def test_conditional_after_data_cannot_override_needs_data():
    d = admit_after_cost_gate(_rec(
        COST_GATE_NEEDS_DATA,
        conditional_after_data="allow_narrow_A_spec_with_strict_cost_kill",
    ))
    # the conditional note is advisory only; decision stays block_pending_data
    assert d["admission_decision"] == "block_pending_data"
    assert "conditional_after_data_note" in d
    assert "advisory only" in d["conditional_after_data_note"]


def test_invalid_gate_status_fails():
    with pytest.raises(ValueError):
        admit_after_cost_gate(_rec("bogus_status"))
    with pytest.raises(ValueError):
        admit_after_cost_gate({"candidate_id": "c"})  # no status
