"""v0.1.2 research quality gate: weak sources must not become exported
backtest candidates, and defaults must never masquerade as source logic."""

from __future__ import annotations

from pathlib import Path

import pytest

from research_intel.collectors.manual_collector import ManualCollector
from research_intel.extraction.extractor import extract_pending
from research_intel.extraction.validators import validate_hypothesis
from research_intel.hypotheses.exporter import (
    candidate_rows,
    export_backtest_spec,
    render_backtest_spec_md,
)
from research_intel.hypotheses.generator import generate_pending
from research_intel.hypotheses.scorer import score_all
from research_intel.ingestion import ingest_records
from research_intel.llm.mock_client import MockLLMClient
from research_intel.storage.db import session_scope
from tests.conftest import EXAMPLES, MOMENTUM_TEXT

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROMPTS = PROJECT_ROOT / "prompts"

CLASSIC_HFT_KEYWORDS = (
    "microsecond", "nanosecond", "co-location", "colocation", "queue position",
    "latency arbitrage", "fpga", "tick-to-trade", "quote racing",
)


def _run_pipeline(settings, engine, paths: list[Path]):
    llm = MockLLMClient()
    collector = ManualCollector()
    with session_scope(engine) as session:
        for path in paths:
            records = collector.search(str(path), limit=10)
            ingest_records(session, settings, collector, records)
        extract_pending(session, llm)
        hypotheses = generate_pending(session, llm)
        score_all(session, llm)
        return {h.payload.get("status", h.status): h.hypothesis_id for h in hypotheses}


# ---- 1-3: vague source end-to-end ------------------------------------------


def test_vague_source_is_gated_end_to_end(settings, engine):
    statuses = _run_pipeline(
        settings, engine,
        [EXAMPLES / "sample_manual_source.md", EXAMPLES / "sample_vague_source.md"],
    )
    assert any(s in statuses for s in ("review_only", "rejected_unbacktestable"))
    vague_id = statuses.get("review_only") or statuses.get("rejected_unbacktestable")
    accepted_id = statuses["candidate"]

    with session_scope(engine) as session:
        rows = candidate_rows(session)
        ids = {r["hypothesis_id"] for r in rows}
        assert accepted_id in ids
        assert vague_id not in ids  # excluded from ranked exports

        with pytest.raises(ValueError, match="review_only|rejected"):
            export_backtest_spec(session, vague_id, settings.exports_dir / "specs")

        # The accepted one still exports fine, with enriched source references.
        path = export_backtest_spec(session, accepted_id, settings.exports_dir / "specs")
        spec = path.read_text()
        assert "Volatility Regime Conditioning" in spec  # source title, not just id
        assert "source_id:" in spec and "document_id:" in spec


def test_vague_hypothesis_has_no_fake_parameters(settings, engine):
    _run_pipeline(settings, engine, [EXAMPLES / "sample_vague_source.md"])
    from research_intel.storage import repositories as repo

    with session_scope(engine) as session:
        hyp = repo.list_hypotheses(session)[0]
        p = hyp.payload
        assert p["status"] in ("review_only", "rejected_unbacktestable")
        assert p["candidate_export_allowed"] is False
        assert p["backtest_spec_export_allowed"] is False
        assert p["strategy_parameters"] == {}  # no fake source-derived numbers
        assert p["parameterization_status"] in ("default_parameterized", "unparameterized")
        assert p["missing_for_backtest"], "must explain what is needed to make it testable"
        assert any("REVIEW" in r for r in p["entry_rules"])


# ---- 4-5: parameterization status and provenance ---------------------------


def _extraction(text: str) -> dict:
    payload = MockLLMClient().extract_research(text, {})
    payload["source_id"] = "1"
    payload["document_id"] = "1"
    return payload


def test_default_parameters_are_marked_default_not_source():
    ext = _extraction(MOMENTUM_TEXT)
    # Simulate a source that only disclosed some values.
    ext["extracted_parameters"] = {"rv_window_minutes": 60, "trend_strength_entry": 0.5}
    ext["parameter_source_quality"] = "partially_explicit"
    hyp = validate_hypothesis(MockLLMClient().generate_hypothesis(ext))
    assert hyp.parameterization_status == "partially_source_parameterized"
    assert hyp.parameter_provenance["rv_window_minutes"] == "source"
    assert hyp.parameter_provenance["trend_strength_entry"] == "source"
    assert hyp.parameter_provenance["vol_expansion_ratio"] == "default"
    assert hyp.parameter_provenance["time_stop_minutes"] == "default"


def test_parameterization_status_controls_candidate_export(settings, engine):
    """A candidate-status row is only exportable while its gates agree."""
    _run_pipeline(settings, engine, [EXAMPLES / "sample_manual_source.md"])
    from research_intel.storage import repositories as repo

    with session_scope(engine) as session:
        hyp = repo.list_hypotheses(session)[0]
        assert hyp.payload["parameterization_status"] == "source_parameterized"
        assert len(candidate_rows(session)) == 1
        # Flip the export gate: the same hypothesis must vanish from exports
        # and refuse spec export.
        payload = dict(hyp.payload)
        payload["candidate_export_allowed"] = False
        payload["backtest_spec_export_allowed"] = False
        payload["parameterization_status"] = "default_parameterized"
        hyp.payload = payload
        session.flush()
        assert candidate_rows(session) == []
        with pytest.raises(ValueError, match="default_parameterized|export_allowed"):
            export_backtest_spec(session, hyp.hypothesis_id, settings.exports_dir / "specs")


# ---- 6: hidden HFT without classic keywords --------------------------------


def test_hidden_hft_example_has_no_classic_keywords_but_is_rejected():
    text = (EXAMPLES / "sample_hidden_hft_source.md").read_text()
    lower = text.lower()
    for keyword in CLASSIC_HFT_KEYWORDS:
        assert keyword not in lower, f"classic keyword '{keyword}' must not appear"
    ext = _extraction(text)
    assert ext["hft_or_low_latency_dependency"] is True
    assert ext["non_applicable_reason"] == "requires_hft_or_low_latency_edge"
    hyp = validate_hypothesis(MockLLMClient().generate_hypothesis(ext))
    assert hyp.hft_or_low_latency_dependency is True
    assert hyp.status == "rejected_hft"


# ---- 7-8: prompts match the schema ------------------------------------------


def test_generate_prompt_lists_all_new_hypothesis_fields():
    prompt = (PROMPTS / "generate_hypothesis.md").read_text()
    for field in (
        "strategy_parameters", "parameter_provenance", "feature_formulas",
        "parameter_source_quality", "parameterization_status",
        "source_reported_metrics", "order_assumptions", "baseline_comparisons",
        "original_source_has_latency_dependency", "adapted_to_non_hft",
        "adaptation_validity", "missing_for_backtest", "candidate_export_allowed",
        "backtest_spec_export_allowed", "optimization_constraints",
    ):
        assert field in prompt, f"prompt missing field '{field}'"


def test_score_prompt_says_all_13_and_penalizes_ungrounded():
    prompt = (PROMPTS / "score_hypothesis.md").read_text()
    assert "all 13" in prompt
    assert "all 12" not in prompt
    for term in ("default_parameterized", "unparameterized", "review_only",
                 "source_rule_quality", "source_data_quality"):
        assert term in prompt


# ---- 9-10: optimization constraints ------------------------------------------


def test_accepted_spec_contains_optimization_constraints():
    ext = _extraction(MOMENTUM_TEXT)
    hyp_payload = MockLLMClient().generate_hypothesis(ext)
    record = validate_hypothesis(hyp_payload)
    from research_intel.hypotheses.exporter import build_backtest_spec
    from research_intel.storage.models import StrategyHypothesis

    hyp = StrategyHypothesis(
        hypothesis_id=record.hypothesis_id, extraction_id=1,
        source_ids=record.source_ids, payload=record.model_dump(),
        status="candidate", priority_score=75.0,
    )
    spec_md = render_backtest_spec_md(build_backtest_spec(hyp, None))
    for constraint in (
        "vol_expansion_ratio > vol_contraction_ratio",
        "trend_strength_entry > trend_strength_exit",
        "time_stop_minutes > momentum_lookback_minutes",
    ):
        assert constraint in spec_md
    assert "Optimization Constraints" in spec_md
    assert "MUST enforce" in spec_md


def test_grid_invalid_combinations_are_explicitly_constrained():
    """Per-parameter grids can produce invalid tuples (e.g. expansion 0.6 with
    contraction 1.2); every such pair must be covered by an exported constraint."""
    record = validate_hypothesis(MockLLMClient().generate_hypothesis(_extraction(MOMENTUM_TEXT)))
    grid = record.optimization_parameters
    constraints = record.optimization_constraints
    # The known cross-parameter orderings whose grids overlap:
    risky_pairs = [
        ("vol_expansion_ratio", "vol_contraction_ratio"),
        ("trend_strength_entry", "trend_strength_exit"),
        ("time_stop_minutes", "momentum_lookback_minutes"),
    ]
    for high, low in risky_pairs:
        if high in grid and low in grid and min(grid[high]) <= max(grid[low]):
            assert any(high in c and low in c for c in constraints), (
                f"grids for {high}/{low} allow invalid combinations without a constraint"
            )
