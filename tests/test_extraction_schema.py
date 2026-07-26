"""Extraction schema validation and mock extraction behavior."""

from __future__ import annotations

import pytest

from research_intel.extraction.schemas import NON_APPLICABLE_HFT, ExtractionRecord
from research_intel.extraction.validators import (
    ExtractionValidationError,
    validate_dimension_scores,
    validate_extraction,
)
from research_intel.llm.mock_client import MockLLMClient
from tests.conftest import HFT_TEXT, MOMENTUM_TEXT


def test_mock_extraction_conforms_to_schema():
    payload = MockLLMClient().extract_research(
        MOMENTUM_TEXT, ExtractionRecord.json_schema_for_llm()
    )
    record = validate_extraction(payload)
    assert record.strategy_style == "volatility_regime"
    assert record.hft_or_low_latency_dependency is False
    assert record.backtestability == "high"
    assert "ohlcv" in record.data_requirements


def test_extraction_preserves_source_parameters():
    record = validate_extraction(MockLLMClient().extract_research(MOMENTUM_TEXT, {}))
    assert record.parameter_source_quality == "explicit"
    assert record.extracted_parameters == {
        "rv_window_minutes": 60,
        "vol_expansion_ratio": 1.2,
        "vol_contraction_ratio": 0.8,
        "momentum_lookback_minutes": 30,
        "trend_strength_entry": 0.5,
        "trend_strength_exit": 0.2,
        "time_stop_minutes": 120,
        "stop_loss_atr_mult": 1.5,
        "fee_slippage_bps_per_side": 7,
    }
    assert record.reported_metrics == {
        "sharpe_after_costs": 1.4,
        "sharpe_unconditional": 0.4,
    }


def test_extraction_without_parameters_is_marked_missing():
    text = "# Idea\n\nMarkets are inefficient and momentum exists in prices."
    record = validate_extraction(MockLLMClient().extract_research(text, {}))
    assert record.parameter_source_quality == "missing"
    assert record.extracted_parameters == {}


def test_required_data_excludes_irrelevant_fields():
    # The momentum sample mentions perpetual futures and funding for
    # robustness, but never basis trading or order books.
    record = validate_extraction(MockLLMClient().extract_research(MOMENTUM_TEXT, {}))
    assert "futures_basis" not in record.data_requirements
    assert "order_book_snapshots" not in record.data_requirements
    assert "trades" not in record.data_requirements


def test_mock_extraction_detects_hft():
    payload = MockLLMClient().extract_research(HFT_TEXT, ExtractionRecord.json_schema_for_llm())
    record = validate_extraction(payload)
    assert record.hft_or_low_latency_dependency is True
    assert record.non_applicable_reason == NON_APPLICABLE_HFT
    assert record.crypto_transferability == "not_transferable_latency_edge"


ADVERSARIAL_HFT_PHRASES = [
    "profits require reacting within the same order-book update",
    "the strategy loses edge if delayed by one second",
    "we must cancel and repost before competitors update quotes",
    "the model requires immediate response to depth changes",
    "the edge comes from being first in the book after each update",
    "profitability vanishes when orders are delayed beyond one tick",
]


@pytest.mark.parametrize("phrase", ADVERSARIAL_HFT_PHRASES)
def test_hidden_hft_phrasing_is_detected(phrase: str):
    # No classic keywords (microsecond, queue position, ...) present.
    text = f"# A Trading Study\n\nWe document a signal in prices. However, {phrase}."
    record = validate_extraction(MockLLMClient().extract_research(text, {}))
    assert record.hft_or_low_latency_dependency is True
    assert record.non_applicable_reason == NON_APPLICABLE_HFT


def test_extraction_keyword_matching_uses_word_boundaries():
    # 'profitable' contains 'ofi'; must NOT classify as flow_imbalance.
    text = "This profitable approach is a market making strategy for market making desks."
    payload = MockLLMClient().extract_research(text, {})
    assert payload["strategy_style"] == "market_making"


def test_invalid_extraction_rejected():
    with pytest.raises(ExtractionValidationError):
        validate_extraction({"title": 123})  # missing required fields / wrong types


def test_dimension_validation():
    from research_intel.extraction.schemas import SCORING_DIMENSIONS

    good = dict.fromkeys(SCORING_DIMENSIONS, 5.0)
    assert validate_dimension_scores(good)["novelty"] == 5.0
    with pytest.raises(ExtractionValidationError):
        validate_dimension_scores({**good, "novelty": 11})
    bad = dict(good)
    del bad["novelty"]
    with pytest.raises(ExtractionValidationError):
        validate_dimension_scores(bad)
