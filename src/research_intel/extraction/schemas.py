"""Pydantic schemas for extractions and strategy hypotheses.

These are the platform's core contracts: extractors must produce
``ExtractionRecord``s and hypothesis generators must produce
``HypothesisRecord``s. Both are stored as JSON payloads in SQLite.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

NON_APPLICABLE_HFT = "requires_hft_or_low_latency_edge"

Backtestability = Literal["high", "medium", "low", "not_backtestable"]
ParameterSourceQuality = Literal["explicit", "partially_explicit", "inferred", "missing"]
AdaptationValidity = Literal["not_needed", "strong", "weak", "invalid"]
SourceQuality = Literal["explicit", "partial", "vague", "missing"]
SourceEvidenceType = Literal[
    "full_paper", "preprint", "abstract_only", "blog_or_report",
    "github_readme", "manual_note", "unknown",
]
ParameterizationStatus = Literal[
    "source_parameterized",
    "partially_source_parameterized",
    "default_parameterized",
    "unparameterized",
]

# Hypothesis status lifecycle. Only "candidate" is ever export-eligible.
HYPOTHESIS_STATUSES = (
    "candidate",  # concrete enough for a falsifiable backtest
    "review_only",  # interesting idea, insufficient parameterization
    "rejected_hft",  # latency/HFT dependency
    "rejected_unbacktestable",  # no data/rules/parameters to support a backtest
    "rejected",  # failed scoring hard filters
)


class ExtractionRecord(BaseModel):
    """Structured trading-relevant information extracted from one document."""

    source_id: str
    document_id: str
    title: str
    research_domain: str = ""
    asset_class: str = ""
    market_type: str = ""
    timeframe: str = ""
    strategy_style: str = ""
    alpha_mechanism: str = ""
    signal_description: str = ""
    features: list[str] = Field(default_factory=list)
    indicators: list[str] = Field(default_factory=list)
    entry_logic: str = ""
    exit_logic: str = ""
    risk_management: str = ""
    position_sizing: str = ""
    data_requirements: list[str] = Field(default_factory=list)
    # Concrete numeric strategy mechanics found in the source (lookbacks,
    # thresholds, stops, costs). Names should be snake_case with units,
    # e.g. rv_window_minutes, trend_strength_entry, fee_slippage_bps_per_side.
    extracted_parameters: dict[str, Any] = Field(default_factory=dict)
    # explicit: parameters directly found in source; partially_explicit: some
    # found, some defaults; inferred: reasonable defaults only; missing: none.
    parameter_source_quality: ParameterSourceQuality = "missing"
    # Grounding metadata: how concrete the source's own rules/data are, and
    # what kind of evidence the document is. Used for gating and scoring.
    source_rule_quality: SourceQuality = "missing"
    source_data_quality: SourceQuality = "missing"
    source_evidence_type: SourceEvidenceType = "unknown"
    # Source facts that must survive into the hypothesis/spec (v0.2 P4):
    # the universe as the source stated it, and its own risk/cost numbers.
    source_asset_universe: str = ""
    source_risk_parameters: dict[str, Any] = Field(default_factory=dict)
    source_cost_parameters: dict[str, Any] = Field(default_factory=dict)
    # Every distinct entry condition the source states (v0.2.1 P4); the
    # generated rules must preserve them or be downgraded.
    source_entry_conditions: list[str] = Field(default_factory=list)
    transaction_cost_assumptions: str = ""
    market_regime_conditions: str = ""
    reported_metrics: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    implementation_complexity: str = ""
    crypto_transferability: str = ""
    hft_or_low_latency_dependency: bool = False
    non_applicable_reason: str = ""
    backtestability: Backtestability = "medium"
    falsification_tests: list[str] = Field(default_factory=list)
    notes: str = ""

    @classmethod
    def json_schema_for_llm(cls) -> dict[str, Any]:
        """JSON Schema handed to LLM clients for structured output."""
        return cls.model_json_schema()


class HypothesisRecord(BaseModel):
    """A crypto-testable strategy hypothesis derived from an extraction."""

    hypothesis_id: str
    source_ids: list[str] = Field(default_factory=list)
    hypothesis_name: str
    one_sentence_idea: str
    market: str = "crypto"
    asset_universe: str = ""
    timeframe: str = ""
    strategy_style: str = ""
    core_alpha_hypothesis: str = ""
    required_data: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    entry_rules: list[str] = Field(default_factory=list)
    exit_rules: list[str] = Field(default_factory=list)
    risk_rules: list[str] = Field(default_factory=list)
    position_sizing: str = ""
    fees_slippage_model: str = ""
    expected_failure_modes: list[str] = Field(default_factory=list)
    minimum_viable_backtest: str = ""
    optimization_parameters: dict[str, Any] = Field(default_factory=dict)
    walk_forward_validation_plan: str = ""
    anti_overfitting_checks: list[str] = Field(default_factory=list)
    priority_score: float = 0.0
    status: str = "candidate"
    # ---- concrete parameterization (source-derived where possible) ----
    # All numeric parameters the rules reference, by name.
    strategy_parameters: dict[str, Any] = Field(default_factory=dict)
    # Per-parameter provenance: "source" (found in the document) or "default".
    parameter_provenance: dict[str, str] = Field(default_factory=dict)
    # Feature name -> computable formula, e.g. "ret_30m": "close/close.shift(30) - 1".
    feature_formulas: dict[str, str] = Field(default_factory=dict)
    parameter_source_quality: ParameterSourceQuality = "missing"
    # Whether the concrete rules rest on source-derived numbers or platform
    # defaults. Only source/partially-source parameterized hypotheses are
    # backtest-export eligible.
    parameterization_status: ParameterizationStatus = "unparameterized"
    # What the source would need to provide to make this testable.
    missing_for_backtest: list[str] = Field(default_factory=list)
    # Export gates (set false for review_only and rejected statuses).
    candidate_export_allowed: bool = True
    backtest_spec_export_allowed: bool = True
    source_reported_metrics: dict[str, Any] = Field(default_factory=dict)
    order_assumptions: str = ""
    baseline_comparisons: list[str] = Field(default_factory=list)
    # Constraints the backtester must enforce over optimization_parameters
    # (grids are per-parameter; not all combinations are valid).
    optimization_constraints: list[str] = Field(default_factory=list)
    # Source values that could not be mapped onto template parameters; they
    # are surfaced in the spec instead of being silently dropped (v0.2 P5).
    unmapped_extracted_parameters: dict[str, Any] = Field(default_factory=dict)
    # ---- archetype fidelity (v0.2 P3) ----
    source_archetype: str = "unknown"
    generated_archetype: str = "unknown"
    core_alpha_triggers: list[str] = Field(default_factory=list)
    preserved_alpha_triggers: list[str] = Field(default_factory=list)
    dropped_alpha_triggers: list[str] = Field(default_factory=list)
    archetype_fidelity: Literal["strong", "partial", "weak", "broken"] = "strong"
    # ---- condition-level entry fidelity (v0.2.1 P4) ----
    source_entry_conditions: list[str] = Field(default_factory=list)
    generated_entry_conditions: list[str] = Field(default_factory=list)
    preserved_entry_conditions: list[str] = Field(default_factory=list)
    dropped_entry_conditions: list[str] = Field(default_factory=list)
    entry_condition_fidelity: Literal["strong", "partial", "weak", "broken"] = "strong"
    # ---- executable-spec consistency (v0.2.1 P1) ----
    spec_consistency: Literal["strong", "partial", "weak", "broken"] = "strong"
    consistency_failures: list[str] = Field(default_factory=list)
    consistency_warnings: list[str] = Field(default_factory=list)
    # ---- source fact fidelity (v0.2 P4) ----
    source_asset_universe: str = ""
    generated_asset_universe: str = ""
    asset_universe_provenance: Literal["source", "expanded_for_robustness", "default"] = "default"
    optional_robustness_universe: str = ""
    source_timeframe: str = ""
    generated_timeframe: str = ""
    timeframe_provenance: Literal["source", "inferred", "default"] = "default"
    source_risk_parameters: dict[str, Any] = Field(default_factory=dict)
    generated_risk_parameters: dict[str, Any] = Field(default_factory=dict)
    risk_parameter_provenance: dict[str, str] = Field(default_factory=dict)
    source_cost_parameters: dict[str, Any] = Field(default_factory=dict)
    generated_cost_parameters: dict[str, Any] = Field(default_factory=dict)
    cost_parameter_provenance: dict[str, str] = Field(default_factory=dict)
    # ---- non-HFT policy fields (hard-filtered at scoring/export time) ----
    # True => the hypothesis itself needs latency edge => always excluded.
    hft_or_low_latency_dependency: bool = False
    non_applicable_reason: str = ""
    # Provenance of any adaptation away from a latency-dependent source.
    original_source_has_latency_dependency: bool = False
    adapted_to_non_hft: bool = False
    adaptation_validity: AdaptationValidity = "not_needed"
    non_hft_adaptation: str = ""  # how the idea was adapted away from latency edge, if it was


SCORING_DIMENSIONS: tuple[str, ...] = (
    "crypto_relevance",
    "non_hft_compatibility",
    "data_availability",
    "backtest_feasibility",
    "signal_clarity",
    "expected_robustness",
    "novelty",
    "implementation_complexity",  # higher = simpler to implement
    "overfitting_risk",  # higher = lower risk
    "transaction_cost_sensitivity",  # higher = less sensitive
    "portfolio_diversification_value",
    "expected_edge_decay_risk",  # higher = slower expected decay
    "source_evidence_quality",  # 10 = full paper w/ OOS tests & costs; 1 = pure opinion
)


class ScoreRecord(BaseModel):
    """Per-dimension scores on a 0-10 scale (10 is always better)."""

    hypothesis_id: str
    dimensions: dict[str, float]
    rationale: dict[str, str] = Field(default_factory=dict)
