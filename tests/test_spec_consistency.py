"""v0.2.1 spec consistency: source facts must drive the executable sections,
and multi-condition entry logic must survive generation."""

from __future__ import annotations

from pathlib import Path

from research_intel.extraction.validators import validate_hypothesis
from research_intel.hypotheses.exporter import build_backtest_spec, render_backtest_spec_md
from research_intel.hypotheses.fidelity import assess_entry_conditions
from research_intel.hypotheses.spec_consistency import validate_spec_consistency
from research_intel.llm.mock_client import MockLLMClient
from research_intel.storage.models import StrategyHypothesis

EVAL = Path(__file__).resolve().parents[1] / "eval_sources" / "batch_v1"


def _hyp(name: str, sid: str = "1"):
    llm = MockLLMClient()
    ext = llm.extract_research((EVAL / f"{name}.md").read_text(), {})
    ext["source_id"] = sid
    ext["document_id"] = sid
    hyp = llm.generate_hypothesis(ext)
    validate_hypothesis(hyp)
    return ext, hyp


def _spec_md(hyp: dict) -> str:
    record = StrategyHypothesis(
        hypothesis_id=hyp["hypothesis_id"], extraction_id=1, source_ids=["1"],
        payload=hyp, status="candidate", priority_score=75.0,
    )
    return render_backtest_spec_md(build_backtest_spec(record, None))


# 1-2: volatility


def test_volatility_position_sizing_uses_source_12_not_15():
    _, hyp = _hyp("note_volatility_regime_momentum")
    assert "12% annualized" in hyp["position_sizing"]
    assert "15%" not in hyp["position_sizing"]
    assert hyp["spec_consistency"] == "strong"


def test_volatility_mvb_primary_is_eth_usdt():
    _, hyp = _hyp("note_volatility_regime_momentum")
    mvb = hyp["minimum_viable_backtest"]
    assert mvb.startswith("Primary: ETH-USDT perpetual futures")
    assert "Optional robustness: BTC/ETH perpetuals" in mvb
    assert "Backtest on BTC and ETH" not in mvb


# 3-4: funding


def test_funding_position_sizing_uses_cap_and_leverage_not_atr():
    _, hyp = _hyp("note_funding_mean_reversion")
    sizing = hyp["position_sizing"]
    assert "per-pair notional <= 5% of equity" in sizing
    assert "perp leg leverage <= 2x" in sizing
    assert "hedged perp/spot" in sizing
    # No generic 1%-risk / ATR-stop sizing (ATR only mentioned as optional).
    assert "1% of equity per trade" not in sizing
    assert "no ATR stop" in sizing and "optional" in sizing
    assert hyp["spec_consistency"] == "strong"


def test_funding_mvb_uses_top10_perps_plus_spot():
    _, hyp = _hyp("note_funding_mean_reversion")
    mvb = hyp["minimum_viable_backtest"]
    assert mvb.startswith("Primary: top-10 liquid USDT perpetuals plus matching spot markets")
    assert "Backtest on BTC and ETH" not in mvb


# 5-7: liquidation


def test_liquidation_position_sizing_uses_half_percent_not_one():
    _, hyp = _hyp("note_liquidation_reversal")
    sizing = hyp["position_sizing"]
    assert "0.5% of equity per trade" in sizing
    assert "1% of equity per trade" not in sizing
    assert "below the cascade low" in sizing


def test_liquidation_feature_formulas_present():
    _, hyp = _hyp("note_liquidation_reversal")
    formulas = hyp["feature_formulas"]
    assert formulas["liq_spike_ratio"] == "liq_5m / liq_baseline_24h"
    assert "rolling 24h mean" in formulas["liq_baseline_24h"]
    assert "close_5m / close_5m.shift(1) - 1" in formulas["ret_5m"]
    assert "percentile" in formulas["ret_5m_percentile"]
    assert "close > open" in formulas["stabilization"]


def test_liquidation_entry_preserves_bottom_percentile_condition():
    _, hyp = _hyp("note_liquidation_reversal")
    assert "5-minute return in bottom 1 percentile" in hyp["source_entry_conditions"]
    assert "5-minute return in bottom 1 percentile" in hyp["preserved_entry_conditions"]
    entry_text = " ".join(hyp["entry_rules"])
    assert "ret_5m_percentile <= 1" in entry_text
    assert "stabilization" in entry_text.lower()
    assert hyp["entry_condition_fidelity"] == "strong"
    assert hyp["status"] == "candidate"


# 8: dropped conditions are reported


def test_condition_fidelity_reports_dropped_conditions():
    ext, _ = _hyp("note_liquidation_reversal")
    generic_rules = [
        "Enter counter-trend when zscore of 12-bar liquidation-adjusted return "
        "over rolling 100 bars exceeds 2.0"
    ]
    cond = assess_entry_conditions(ext, generic_rules)
    assert cond["dropped_entry_conditions"]
    assert "5-minute return in bottom 1 percentile" in cond["dropped_entry_conditions"]
    assert cond["entry_condition_fidelity"] in ("weak", "broken")
    # Exactly one dropped -> partial (B-cap, still candidate-eligible).
    partial = assess_entry_conditions(
        ext,
        ["liq spike > 8x rolling 24h average", "ret in bottom 1 percentile of 5-minute returns",
         "stabilization: next 5-minute bar closes above open"],
    )
    assert partial["entry_condition_fidelity"] == "partial"
    assert len(partial["dropped_entry_conditions"]) == 1


# 9: broken consistency demotes


def test_broken_spec_consistency_demotes_to_review_only(settings, engine):
    from sqlalchemy import select

    from research_intel.collectors.manual_collector import ManualCollector
    from research_intel.extraction.extractor import extract_pending
    from research_intel.hypotheses.generator import generate_for_extraction
    from research_intel.ingestion import ingest_records
    from research_intel.storage.db import session_scope
    from research_intel.storage.models import Extraction

    class InconsistentLLM(MockLLMClient):
        def generate_hypothesis(self, extraction):
            hyp = super().generate_hypothesis(extraction)
            # Contradict the preserved source facts downstream.
            hyp["position_sizing"] = (
                "size = (1% equity risk) / stop distance with stop at 1.5x ATR; "
                "scaled to 15% annualized portfolio target"
            )
            hyp["minimum_viable_backtest"] = "Backtest on BTC and ETH 1m bars over 3 years."
            return hyp

    with session_scope(engine) as session:
        records = ManualCollector().search(
            str(EVAL / "note_volatility_regime_momentum.md"), limit=1
        )
        ingest_records(session, settings, ManualCollector(), records)
        extract_pending(session, MockLLMClient())
        extraction = session.scalars(select(Extraction)).first()
        hyp = generate_for_extraction(session, extraction, InconsistentLLM())
        assert hyp.status == "review_only"
        assert hyp.payload["spec_consistency"] in ("weak", "broken")
        assert hyp.payload["candidate_export_allowed"] is False
        assert hyp.payload["backtest_spec_export_allowed"] is False
        assert any("spec consistency" in m for m in hyp.payload["missing_for_backtest"])


# 10: exported specs carry no contradictions


def test_exported_specs_have_no_fact_vs_sizing_contradictions():
    for name in ("note_volatility_regime_momentum", "note_funding_mean_reversion",
                 "note_liquidation_reversal"):
        _, hyp = _hyp(name)
        assert hyp["status"] == "candidate", name
        result = validate_spec_consistency(hyp)
        assert result["spec_consistency"] in ("strong", "partial"), (name, result)
        assert result["consistency_failures"] == [], (name, result)
        spec = _spec_md(hyp)
        assert "Spec consistency: strong" in spec or "Spec consistency: partial" in spec
        # The facts section and the executable sections must agree on numbers.
        if "Portfolio volatility target: 12% annualized (source)" in spec:
            assert "12% annualized" in hyp["position_sizing"]
        if "Risk per trade: 0.5% of equity (source)" in spec:
            assert "0.5%" in hyp["position_sizing"]
