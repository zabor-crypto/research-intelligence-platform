"""Tests for the cost-gate export/promotion guard."""

from __future__ import annotations

from research_gates import enforce_cost_gate_before_export
from research_gates.execution_cost_gate import (
    COST_GATE_FAIL_COST_HURDLE,
    COST_GATE_FAIL_MISSING_LIQUIDITY,
    COST_GATE_NEEDS_DATA,
    COST_GATE_PASS,
    COST_GATE_PASS_CAPACITY_LIMITED,
)


def _cand(cid="c", comp="leg"):
    return {"candidate_id": cid, "component_id": comp}


def _gate(status, **extra):
    return {"candidate_id": "c", "component_id": "leg", "pass_fail_status": status, **extra}


def test_missing_gate_record_blocks_export():
    r = enforce_cost_gate_before_export(_cand(), None)
    assert r["export_allowed"] is False
    assert r["reason"] == "blocked_missing_cost_gate"
    assert "deploy_capital" in r["forbidden_next_steps"]


def test_needs_data_blocks_export():
    r = enforce_cost_gate_before_export(_cand(), _gate(COST_GATE_NEEDS_DATA))
    assert r["export_allowed"] is False
    assert r["admission_decision"] == "block_pending_data"
    assert r["reason"] == "blocked_pending_data"
    assert "clean_A_spec" in r["forbidden_next_steps"]
    assert "proceed_to_backtest" in r["forbidden_next_steps"]


def test_cost_hurdle_blocks_export():
    r = enforce_cost_gate_before_export(_cand(), _gate(COST_GATE_FAIL_COST_HURDLE))
    assert r["export_allowed"] is False
    assert r["reason"] == "rejected_cost_hurdle"


def test_missing_liquidity_blocks_export():
    r = enforce_cost_gate_before_export(_cand(), _gate(COST_GATE_FAIL_MISSING_LIQUIDITY))
    assert r["export_allowed"] is False
    assert r["reason"] == "rejected_missing_liquidity_data"


def test_pass_allows_export():
    r = enforce_cost_gate_before_export(_cand(), _gate(COST_GATE_PASS))
    assert r["export_allowed"] is True
    assert r["admission_decision"] == "admit_to_A_spec"
    # even an allowed export forbids deploying capital / skipping kill criteria
    assert "deploy_capital" in r["forbidden_next_steps"]
    assert "skip_cost_kill_criteria" in r["forbidden_next_steps"]


def test_capacity_limited_pass_scope():
    r = enforce_cost_gate_before_export(_cand(), _gate(COST_GATE_PASS_CAPACITY_LIMITED))
    assert r["export_allowed"] is True
    assert r["export_scope"] == "capacity_limited_A_spec_only"


def test_conditional_after_data_cannot_override_needs_data():
    r = enforce_cost_gate_before_export(
        _cand(), _gate(COST_GATE_NEEDS_DATA, conditional_after_data="allow_narrow_A_spec_with_strict_cost_kill")
    )
    assert r["export_allowed"] is False
    assert r["admission_decision"] == "block_pending_data"
    assert "conditional_after_data_note" in r
    assert "advisory only" in r["conditional_after_data_note"]


def test_deploy_capital_always_forbidden():
    for status in (COST_GATE_PASS, COST_GATE_PASS_CAPACITY_LIMITED, COST_GATE_NEEDS_DATA,
                   COST_GATE_FAIL_COST_HURDLE):
        r = enforce_cost_gate_before_export(_cand(), _gate(status))
        assert "deploy_capital" in r["forbidden_next_steps"]
        assert "skip_cost_kill_criteria" in r["forbidden_next_steps"]
    # even with no gate record
    r = enforce_cost_gate_before_export(_cand(), None)
    assert "deploy_capital" in r["forbidden_next_steps"]
