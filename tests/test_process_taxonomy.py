"""Process taxonomies: artifact completeness, solvency classification, replay causes."""

from __future__ import annotations

import pytest

from research_process.process_taxonomy import backtest_artifact_contract as BAC
from research_process.process_taxonomy import insolvency as INS
from research_process.process_taxonomy import replay as RP

# --- artifact contract ----------------------------------------------------------------------


def test_a_summary_only_backtest_is_not_valid():
    assert BAC.historical_backtest_validity(False) == BAC.BLOCKED_MISSING_EVENT_EQUITY
    assert BAC.historical_backtest_validity(True) == BAC.VALID


def test_a_complete_event_row_carries_every_required_field():
    row = dict.fromkeys(BAC.REQUIRED_EVENT_FIELDS, 0)
    assert BAC.event_row_complete(row) is True
    assert BAC.missing_event_fields(row) == ()


def test_missing_event_fields_are_named():
    row = dict.fromkeys(BAC.REQUIRED_EVENT_FIELDS, 0)
    del row["cumulative_funding"]
    del row["source_hashes"]
    assert BAC.event_row_complete(row) is False
    assert set(BAC.missing_event_fields(row)) == {"cumulative_funding", "source_hashes"}


def test_the_contract_demands_a_cost_decomposition_not_just_pnl():
    for field in ("reference_price_gross_pnl", "cumulative_slippage", "cumulative_fees",
                  "cumulative_funding", "net_pnl", "equity"):
        assert field in BAC.REQUIRED_EVENT_FIELDS


# --- insolvency -----------------------------------------------------------------------------


def test_minimum_equity_is_reconstructed_from_the_drawdown_block():
    # peak = -5000 / -0.5 = 10000; trough = 10000 - 5000 = 5000
    assert INS.reconstruct_minimum_equity(-0.5, -5000.0) == pytest.approx(5000.0)


def test_a_zero_drawdown_fraction_cannot_be_reconstructed():
    with pytest.raises(ValueError):
        INS.reconstruct_minimum_equity(0.0, -5000.0)


def test_a_solvent_run_keeps_its_return_metrics():
    rec = INS.classify_from_max_drawdown("R1", 12000.0, -0.5, -5000.0, 1717200000)
    assert rec.terminal_state == INS.TERMINAL_SOLVENT_THROUGHOUT
    assert rec.ever_nonpositive_equity is False
    assert rec.percentage_return_metrics_economically_interpretable is True
    assert rec.sharpe_economically_interpretable is True
    INS.validate_record(rec)


def test_a_run_that_touches_zero_equity_loses_its_return_metrics_even_if_it_recovers():
    # peak = -12000 / -1.2 = 10000; trough = 10000 - 12000 = -2000
    rec = INS.classify_from_max_drawdown("R3", 2583.53, -1.2, -12000.0, 1717200000)
    assert rec.ever_nonpositive_equity is True
    assert rec.terminal_nonpositive_equity is False
    assert rec.recovered_after_nonpositive_equity is True
    assert rec.terminal_state == INS.TERMINAL_RECOVERED
    assert rec.percentage_return_metrics_economically_interpretable is False
    assert rec.sortino_economically_interpretable is False
    INS.validate_record(rec)


def test_a_run_that_ends_below_zero_is_terminally_insolvent():
    rec = INS.classify_from_max_drawdown("R2", -504.60, -1.2, -12000.0, 1717200000)
    assert rec.terminal_state == INS.TERMINAL_NONPOSITIVE
    assert rec.terminal_nonpositive_equity is True
    assert rec.recovered_after_nonpositive_equity is False
    assert rec.unconstrained_accounting_continued_after_insolvency is True
    INS.validate_record(rec)


def test_the_classifier_introduces_no_liquidation_model():
    """Accounting continues mechanically; nothing is rescued after the fact."""
    rec = INS.classify_from_max_drawdown(
        "R2", -504.60, -1.2, -12000.0, 1717200000, unconstrained_accounting=False)
    assert rec.unconstrained_accounting_continued_after_insolvency is False
    assert rec.terminal_state == INS.TERMINAL_NONPOSITIVE  # the verdict is unchanged


def test_an_inconsistent_record_is_rejected():
    rec = INS.classify_from_max_drawdown("R2", -504.60, -1.2, -12000.0, None)
    tampered = type(rec)(**{**rec.to_dict(), "recovered_after_nonpositive_equity": True})
    with pytest.raises(ValueError):
        INS.validate_record(tampered)


def test_a_record_cannot_claim_interpretable_returns_through_a_zero_crossing():
    rec = INS.classify_from_max_drawdown("R3", 2583.53, -1.2, -12000.0, None)
    tampered = type(rec)(
        **{**rec.to_dict(), "percentage_return_metrics_economically_interpretable": True})
    with pytest.raises(ValueError):
        INS.validate_record(tampered)


def test_the_record_round_trips_as_a_dict():
    rec = INS.classify_from_max_drawdown("R1", 12000.0, -0.5, -5000.0, 1)
    assert rec.to_dict()["run_id"] == "R1"
    assert type(rec)(**rec.to_dict()) == rec


# --- replay taxonomy ------------------------------------------------------------------------


def taxonomy(**overrides) -> RP.ReplayTaxonomy:
    base = dict(
        result_conditioned_rerun_count=0,
        rescue_rerun_count=0,
        optimization_rerun_count=0,
        determinism_reproduction_batch_count=0,
        determinism_reproduced_scenario_count=0,
        infrastructure_retry_count=0,
        byte_identical_replay_count=0,
        semantic_input_change_count=0,
    )
    base.update(overrides)
    return RP.ReplayTaxonomy(**base)


def test_a_clean_release_records_no_recomputation():
    tax = taxonomy()
    RP.validate(tax)
    assert RP.describes_zero_historical_recomputation(tax) is True
    assert RP.result_conditioned_total(tax) == 0


def test_a_determinism_reproduction_is_not_zero_recomputation():
    tax = taxonomy(
        determinism_reproduction_batch_count=1,
        determinism_reproduced_scenario_count=4,
        byte_identical_replay_count=4,
    )
    RP.validate(tax)
    assert RP.describes_zero_historical_recomputation(tax) is False
    # ...but it is also not a rescue
    assert RP.result_conditioned_total(tax) == 0


def test_rescue_and_optimization_reruns_are_counted_against_the_verdict():
    tax = taxonomy(rescue_rerun_count=1, optimization_rerun_count=2, result_conditioned_rerun_count=1)
    RP.validate(tax)
    assert RP.result_conditioned_total(tax) == 4
    assert RP.describes_zero_historical_recomputation(tax) is False


def test_negative_counts_are_rejected():
    with pytest.raises(ValueError):
        RP.validate(taxonomy(rescue_rerun_count=-1))


def test_reproduced_scenarios_require_a_reproduction_batch():
    with pytest.raises(ValueError):
        RP.validate(taxonomy(determinism_reproduced_scenario_count=3))


def test_byte_identical_replays_cannot_exceed_reproduced_scenarios():
    with pytest.raises(ValueError):
        RP.validate(taxonomy(
            determinism_reproduction_batch_count=1,
            determinism_reproduced_scenario_count=2,
            byte_identical_replay_count=3,
        ))


def test_an_infrastructure_retry_is_not_a_historical_recomputation():
    tax = taxonomy(infrastructure_retry_count=2)
    RP.validate(tax)
    assert RP.describes_zero_historical_recomputation(tax) is True
