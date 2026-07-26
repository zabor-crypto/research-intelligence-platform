"""Regression tests for the cost-gate export hook.

The hook is the pure, DB-free `enforce_cost_gate_export_hook` in `research_gates`, so
these tests import it from `research_gates` and never import the DB-backed exporter module
(which would pull in the storage layer). A separate static-audit test proves the real
exporter still calls the hook, by reading the file text (no import).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from research_gates import enforce_cost_gate_export_hook


def _gate(status, **extra):
    return {"candidate_id": "c", "component_id": "leg", "pass_fail_status": status, **extra}


# --- legacy backward-compatibility ------------------------------------------
def test_legacy_export_without_gate_is_unaffected():
    assert enforce_cost_gate_export_hook(
        {"hypothesis_id": "legacy", "parameterization_status": "source_parameterized"}
    ) is None


# --- requires_cost_gate without a record ------------------------------------
def test_requires_cost_gate_without_record_blocks_missing():
    g = enforce_cost_gate_export_hook({"candidate_id": "c", "requires_cost_gate": True})
    assert g is not None
    assert g["export_allowed"] is False
    assert g["reason"] == "blocked_missing_cost_gate"
    assert g["admission_decision"] == "block_missing_cost_gate"


# --- blocked / rejected statuses --------------------------------------------
def test_needs_data_blocks_export():
    g = enforce_cost_gate_export_hook({"cost_gate_record": _gate("cost_gate_needs_data")})
    assert g["export_allowed"] is False
    assert g["reason"] == "blocked_pending_data"


def test_cost_hurdle_blocks_export():
    g = enforce_cost_gate_export_hook({"cost_gate_record": _gate("cost_gate_fail_cost_hurdle")})
    assert g["export_allowed"] is False
    assert g["reason"] == "rejected_cost_hurdle"


# --- allowed statuses -------------------------------------------------------
def test_pass_allows_export():
    g = enforce_cost_gate_export_hook({"cost_gate_record": _gate("cost_gate_pass")})
    assert g["export_allowed"] is True
    assert g["admission_decision"] == "admit_to_A_spec"


def test_capacity_limited_pass_carries_scope_metadata():
    g = enforce_cost_gate_export_hook({"cost_gate_record": _gate("cost_gate_pass_but_capacity_limited")})
    assert g["export_allowed"] is True
    assert g["export_scope"] == "capacity_limited_A_spec_only"


# --- conditional_after_data cannot override needs_data -----------------------
def test_conditional_after_data_cannot_allow_needs_data_export():
    g = enforce_cost_gate_export_hook(
        {"cost_gate_record": _gate("cost_gate_needs_data", conditional_after_data="allow_narrow_A_spec_with_strict_cost_kill")}
    )
    assert g["export_allowed"] is False
    assert g["admission_decision"] == "block_pending_data"
    assert "conditional_after_data_note" in g


# --- invalid status raises (audit signal) -----------------------------------
def test_invalid_status_raises():
    with pytest.raises(ValueError):
        enforce_cost_gate_export_hook({"cost_gate_record": _gate("bogus_status")})


# --- static audit: the real exporter still calls the hook (no import) -------
def test_exporter_still_calls_hook_static_audit():
    text = Path("src/research_intel/hypotheses/exporter.py").read_text()
    for token in (
        "enforce_cost_gate_export_hook",
        "cost_gate_export_blocked",
        "cost_gate_export_guard",
        "requires_cost_gate",
        "cost_gate_record",
    ):
        assert token in text, f"exporter.py missing token: {token}"
