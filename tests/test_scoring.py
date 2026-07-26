"""Scoring weights and hard filters."""

from __future__ import annotations

import pytest

from research_intel.extraction.schemas import NON_APPLICABLE_HFT, SCORING_DIMENSIONS
from research_intel.hypotheses.scorer import (
    WEIGHTS,
    apply_hard_filters,
    weighted_total,
)


def test_weights_cover_all_dimensions_and_sum_to_one():
    assert set(WEIGHTS) == set(SCORING_DIMENSIONS)
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)


def test_weighted_total_scales_to_100():
    assert weighted_total(dict.fromkeys(SCORING_DIMENSIONS, 10.0)) == 100.0
    assert weighted_total(dict.fromkeys(SCORING_DIMENSIONS, 0.0)) == 0.0
    assert weighted_total(dict.fromkeys(SCORING_DIMENSIONS, 5.0)) == 50.0


def _dims(**overrides) -> dict[str, float]:
    dims = dict.fromkeys(SCORING_DIMENSIONS, 7.0)
    dims.update(overrides)
    return dims


def test_hft_hard_filter_excludes():
    payload = {"hft_or_low_latency_dependency": True, "non_hft_adaptation": ""}
    excluded, reason, flags = apply_hard_filters(payload, _dims())
    assert excluded
    assert reason == NON_APPLICABLE_HFT


def test_hft_flag_excludes_even_with_adaptation_text():
    # There is no escape hatch: if the hypothesis itself is flagged
    # latency-dependent, adaptation prose must not rescue it.
    payload = {
        "hft_or_low_latency_dependency": True,
        "non_hft_adaptation": "we claim it can be aggregated to 1m bars",
        "adapted_to_non_hft": True,
        "adaptation_validity": "strong",
    }
    excluded, reason, _ = apply_hard_filters(payload, _dims())
    assert excluded
    assert reason == NON_APPLICABLE_HFT


def test_genuinely_adapted_idea_passes():
    payload = {
        "hft_or_low_latency_dependency": False,
        "original_source_has_latency_dependency": True,
        "adapted_to_non_hft": True,
        "adaptation_validity": "strong",
        "non_hft_adaptation": "signal aggregated to 1m bars",
    }
    excluded, _, _ = apply_hard_filters(payload, _dims())
    assert not excluded


@pytest.mark.parametrize("validity", ["weak", "invalid"])
def test_weak_or_invalid_adaptation_excludes(validity: str):
    payload = {"hft_or_low_latency_dependency": False, "adaptation_validity": validity}
    excluded, reason, _ = apply_hard_filters(payload, _dims())
    assert excluded
    assert reason == "weak_or_invalid_non_hft_adaptation"


def test_soft_penalty_for_abstract_only_without_parameters():
    from research_intel.hypotheses.scorer import SOFT_PENALTY_FLAG, apply_soft_penalties

    dims = _dims(source_evidence_quality=2.0)
    payload = {"parameter_source_quality": "missing"}
    total, flags = apply_soft_penalties(payload, dims, 70.0)
    assert total == 35.0
    assert flags == [SOFT_PENALTY_FLAG]
    # Good evidence: no penalty.
    total, flags = apply_soft_penalties(
        {"parameter_source_quality": "explicit"}, _dims(source_evidence_quality=8.0), 70.0
    )
    assert total == 70.0 and flags == []


def test_low_data_availability_excludes():
    excluded, reason, _ = apply_hard_filters({}, _dims(data_availability=1.0))
    assert excluded
    assert reason == "required_data_unavailable_or_unrealistic"


def test_vague_logic_excludes():
    excluded, reason, _ = apply_hard_filters({}, _dims(signal_clarity=2.0))
    assert excluded
    assert reason == "strategy_logic_too_vague"


def test_unfalsifiable_excludes():
    excluded, reason, _ = apply_hard_filters({}, _dims(backtest_feasibility=0.0))
    assert excluded
    assert reason == "not_falsifiable_with_clear_backtest"


def test_clean_hypothesis_passes():
    excluded, reason, flags = apply_hard_filters({}, _dims())
    assert not excluded
    assert reason is None
    assert flags == []
