"""Exact dataset-intersection gate: "we have data for that venue" is not a dataset."""

from __future__ import annotations

import dataclasses

from research_process.pre_freeze import dataset_gate as DG

REQUIRED = {
    "venue": "examplex",
    "market_type": "perpetual",
    "symbol_or_universe": "BTCUSDT",
    "timeframe": "1h",
    "timestamp_semantics": "bar_open_time",
    "timezone": "UTC",
}


def mapping(**overrides) -> DG.DatasetMapping:
    base = dict(
        dataset_id="ds-examplex-btcusdt-1h-v3",
        manifest_id="mf-0091",
        content_identity="sha256:2c1f…",
        storage_location="snapshots/examplex/btcusdt/1h/v3",
        venue="examplex",
        market_type="perpetual",
        symbol_or_universe="BTCUSDT",
        timeframe="1h",
        coverage_start="2024-01-01",
        coverage_end="2026-06-30",
        required_warmup="200 bars",
        row_or_event_count=21_912,
        required_columns=("open", "high", "low", "close", "volume"),
        available_columns=("open", "high", "low", "close", "volume", "quote_volume"),
        timestamp_semantics="bar_open_time",
        timezone="UTC",
        known_gaps=(),
        lifecycle_coverage="listed 2019-09; no delisting in range",
        causal_availability="causal",
        source_field_mapping={"price": "close"},
        recent_causal_coverage_days=365.0,
    )
    base.update(overrides)
    return DG.DatasetMapping(**base)


def test_exact_mapping_passes():
    r = DG.evaluate(mapping(), REQUIRED)
    assert r["state"] == DG.EXACT_PASS
    assert r["passed"] is True
    assert r["freeze_allowed"] is True
    assert r["block_reasons"] == []


def test_incomplete_mapping_is_unverifiable():
    r = DG.evaluate(mapping(manifest_id=""), REQUIRED)
    assert r["state"] == DG.BLOCKED_IDENTITY
    assert "manifest_id" in r["missing_mapping_fields"]


def test_broad_category_claim_is_not_a_dataset_identity():
    r = DG.evaluate(mapping(dataset_id="data exists"), REQUIRED)
    assert r["state"] == DG.BLOCKED_IDENTITY
    assert any("broad category claim" in reason for reason in r["block_reasons"])


def test_a_mapping_that_needs_new_acquisition_is_blocked_not_satisfied():
    r = DG.evaluate(mapping(requires_new_acquisition=True), REQUIRED)
    assert r["state"] == DG.BLOCKED_IDENTITY
    assert r["new_acquisition_required"] is True


def test_normalisation_outside_the_bounded_set_is_a_mismatch():
    r = DG.evaluate(mapping(normalizations_applied=("interpolate_missing_bars",)), REQUIRED)
    assert r["state"] == DG.BLOCKED_IDENTITY


def test_venue_mismatch_blocks_on_market():
    r = DG.evaluate(mapping(venue="exampley"), REQUIRED)
    assert r["state"] == DG.BLOCKED_MARKET


def test_market_type_mismatch_blocks_on_market():
    r = DG.evaluate(mapping(market_type="spot"), REQUIRED)
    assert r["state"] == DG.BLOCKED_MARKET


def test_symbol_mismatch_blocks_on_instrument():
    r = DG.evaluate(mapping(symbol_or_universe="ETHUSDT"), REQUIRED)
    assert r["state"] == DG.BLOCKED_INSTRUMENT


def test_timeframe_mismatch_blocks_without_a_declared_resample():
    r = DG.evaluate(mapping(timeframe="1m"), REQUIRED)
    assert r["state"] == DG.BLOCKED_TIMEFRAME


def test_declared_resample_turns_a_timeframe_mismatch_into_a_normalised_pass():
    r = DG.evaluate(
        mapping(timeframe="1m", normalizations_applied=("bar_resample_finer_to_coarser",)),
        REQUIRED,
    )
    assert r["state"] == DG.NORMALIZED_PASS
    assert r["passed"] is True


def test_timestamp_semantics_mismatch_blocks():
    r = DG.evaluate(mapping(timestamp_semantics="bar_close_time"), REQUIRED)
    assert r["state"] == DG.BLOCKED_TIMEFRAME


def test_missing_required_column_blocks():
    r = DG.evaluate(mapping(available_columns=("open", "high", "low", "close")), REQUIRED)
    assert r["state"] == DG.BLOCKED_FIELDS
    assert any("volume" in reason for reason in r["block_reasons"])


def test_unverified_causality_blocks():
    assert DG.evaluate(mapping(causal_availability="unknown"), REQUIRED)["state"] == (
        DG.BLOCKED_CAUSALITY)


def test_lookahead_field_blocks():
    r = DG.evaluate(mapping(causal_availability="lookahead"), REQUIRED)
    assert r["state"] == DG.BLOCKED_CAUSALITY
    assert any("decision time" in reason for reason in r["block_reasons"])


def test_unmeasured_and_insufficient_recent_coverage_block():
    assert DG.evaluate(mapping(recent_causal_coverage_days=None), REQUIRED)["state"] == (
        DG.BLOCKED_COVERAGE)
    assert DG.evaluate(mapping(recent_causal_coverage_days=30.0), REQUIRED)["state"] == (
        DG.BLOCKED_COVERAGE)


def test_case_and_hyphen_differences_do_not_manufacture_a_mismatch():
    r = DG.evaluate(mapping(venue="ExampleX", market_type="Perpetual"), REQUIRED)
    assert r["passed"] is True


def test_every_mapping_must_pass_for_a_source_to_be_screenable():
    good = mapping()
    bad = dataclasses.replace(good, venue="exampley")
    assert DG.evaluate_all([good], REQUIRED)["passed"] is True
    r = DG.evaluate_all([good, bad], REQUIRED)
    assert r["passed"] is False
    assert r["failed_count"] == 1
    assert r["mapping_count"] == 2


def test_no_mapping_at_all_is_blocked():
    r = DG.evaluate_all([], REQUIRED)
    assert r["passed"] is False
    assert r["state"] == DG.BLOCKED_IDENTITY
