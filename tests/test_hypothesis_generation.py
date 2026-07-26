"""Hypothesis generation from extractions."""

from __future__ import annotations

import pytest

from research_intel.extraction.schemas import ExtractionRecord
from research_intel.extraction.validators import validate_hypothesis
from research_intel.llm.mock_client import MockLLMClient
from tests.conftest import HFT_TEXT, MOMENTUM_TEXT


def _extraction(text: str) -> dict:
    payload = MockLLMClient().extract_research(text, ExtractionRecord.json_schema_for_llm())
    payload["source_id"] = "1"
    payload["document_id"] = "1"
    return payload


def test_hypothesis_from_momentum_paper_is_candidate():
    hyp = MockLLMClient().generate_hypothesis(_extraction(MOMENTUM_TEXT))
    record = validate_hypothesis(hyp)
    assert record.market == "crypto"
    assert record.entry_rules and record.exit_rules and record.risk_rules
    assert record.hft_or_low_latency_dependency is False
    assert record.minimum_viable_backtest
    assert record.walk_forward_validation_plan
    assert record.anti_overfitting_checks


def test_hypothesis_from_pure_hft_paper_stays_flagged():
    hyp = MockLLMClient().generate_hypothesis(_extraction(HFT_TEXT))
    record = validate_hypothesis(hyp)
    assert record.hft_or_low_latency_dependency is True
    assert record.non_applicable_reason == "requires_hft_or_low_latency_edge"
    assert record.original_source_has_latency_dependency is True
    assert record.adapted_to_non_hft is False
    assert record.adaptation_validity == "invalid"
    assert record.non_hft_adaptation == ""


def test_adaptable_flow_idea_records_adaptation():
    text = (
        "# Order Flow Imbalance and Returns\n\n"
        "Order flow imbalance in the order book predicts returns. Results rely on "
        "microsecond timestamps but the signal aggregates to minute bars."
    )
    hyp = MockLLMClient().generate_hypothesis(_extraction(text))
    record = validate_hypothesis(hyp)
    # HFT-flavored but adaptable style: adapted with full provenance, not rejected.
    assert record.hft_or_low_latency_dependency is False
    assert record.original_source_has_latency_dependency is True
    assert record.adapted_to_non_hft is True
    assert record.adaptation_validity == "strong"
    assert record.non_hft_adaptation


def test_hypothesis_preserves_source_parameters():
    record = validate_hypothesis(MockLLMClient().generate_hypothesis(_extraction(MOMENTUM_TEXT)))
    p = record.strategy_parameters
    assert p["rv_window_minutes"] == 60
    assert p["vol_expansion_ratio"] == 1.2
    assert p["vol_contraction_ratio"] == 0.8
    assert p["momentum_lookback_minutes"] == 30
    assert p["trend_strength_entry"] == 0.5
    assert p["trend_strength_exit"] == 0.2
    assert p["time_stop_minutes"] == 120
    assert p["stop_loss_atr_mult"] == 1.5
    assert p["fee_slippage_bps_per_side"] == 7
    assert all(v == "source" for v in record.parameter_provenance.values())
    # Rules must reference the actual source values, not template placeholders.
    entry_text = " ".join(record.entry_rules)
    exit_text = " ".join(record.exit_rules)
    assert "ret_30m" in entry_text and "> 1.2" in entry_text and "> 0.5" in entry_text
    assert "< 0.2" in exit_text and "120 minutes" in exit_text and "1.5x ATR_60m" in exit_text
    assert record.source_reported_metrics["sharpe_after_costs"] == 1.4


def test_optimization_grid_keys_reference_strategy_parameters():
    record = validate_hypothesis(MockLLMClient().generate_hypothesis(_extraction(MOMENTUM_TEXT)))
    assert record.optimization_parameters, "grid must not be empty"
    assert set(record.optimization_parameters) <= set(record.strategy_parameters)
    # Source values sit inside their own grids.
    assert 30 in record.optimization_parameters["momentum_lookback_minutes"]
    assert 0.5 in record.optimization_parameters["trend_strength_entry"]


def test_vague_hypothesis_is_rejected():
    from research_intel.extraction.validators import ExtractionValidationError

    vague = MockLLMClient().generate_hypothesis(_extraction(MOMENTUM_TEXT))
    vague["entry_rules"] = ["Enter when signal is strong.", "Trade when market momentum appears."]
    vague["exit_rules"] = ["Exit during unfavorable regimes."]
    vague["risk_rules"] = ["Manage risk prudently."]
    with pytest.raises(ExtractionValidationError, match="rule-shape"):
        validate_hypothesis(vague)


def test_hypothesis_ids_are_deterministic():
    a = MockLLMClient().generate_hypothesis(_extraction(MOMENTUM_TEXT))
    b = MockLLMClient().generate_hypothesis(_extraction(MOMENTUM_TEXT))
    assert a["hypothesis_id"] == b["hypothesis_id"]
