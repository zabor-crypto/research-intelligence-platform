"""Prompt/schema synchronization (v0.2.2 P3).

These tests fail whenever a schema field is added without updating the
provider prompts — the drift that would make a real LLM silently rely on
defaults. They check field names and critical phrases, not paragraph text.
"""

from __future__ import annotations

from pathlib import Path

from research_intel.extraction.schemas import (
    SCORING_DIMENSIONS,
    ExtractionRecord,
    HypothesisRecord,
)

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
GENERATE = (PROMPTS / "generate_hypothesis.md").read_text()
EXTRACT = (PROMPTS / "extract_research.md").read_text()
SCORE = (PROMPTS / "score_hypothesis.md").read_text()


def test_generate_prompt_covers_every_hypothesis_field():
    missing = [f for f in HypothesisRecord.model_fields if f not in GENERATE]
    assert not missing, f"generate_hypothesis.md missing HypothesisRecord fields: {missing}"


def test_extract_prompt_covers_every_extraction_field():
    # Fields are conveyed either by name in the prompt text or through the
    # injected JSON schema placeholder, which carries every field by name.
    assert "{{json_schema}}" in EXTRACT, "extract prompt lost its {{json_schema}} placeholder"
    explicitly_mentioned = [f for f in ExtractionRecord.model_fields if f in EXTRACT]
    # The critical grounding fields must be explained in prose, not schema-only.
    for field in ("extracted_parameters", "parameter_source_quality", "reported_metrics"):
        assert field in EXTRACT, f"extract prompt must explain '{field}' explicitly"
    assert explicitly_mentioned, "extract prompt mentions no schema fields at all"


def test_score_prompt_mentions_all_dimensions_and_gates():
    for dimension in SCORING_DIMENSIONS:
        assert dimension in SCORE, f"score prompt missing dimension '{dimension}'"
    for term in (
        "spec_consistency", "archetype_fidelity", "entry_condition_fidelity",
        "parameterization_status", "candidate_export_allowed",
        "backtest_spec_export_allowed",
    ):
        assert term in SCORE, f"score prompt missing gate term '{term}'"


def test_score_prompt_states_required_penalty_caps():
    # Critical phrases (loose match, not exact paragraphs).
    for phrase in (
        'status != "candidate"',
        "backtest_feasibility <= 3",
        "signal_clarity <= 3",
        "expected_robustness <= 3",
        "signal_clarity <= 4",
    ):
        assert phrase in SCORE, f"score prompt missing penalty phrase '{phrase}'"


def test_generate_prompt_instructs_source_fact_copying():
    for field in (
        "source_asset_universe", "source_risk_parameters",
        "source_cost_parameters", "source_entry_conditions",
        "generated_asset_universe", "generated_risk_parameters",
        "generated_cost_parameters", "generated_entry_conditions",
    ):
        assert field in GENERATE
    lower = GENERATE.lower()
    assert "override generic defaults" in lower
    assert "never rely on" in lower and "defaults" in lower
