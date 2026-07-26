"""Weighted scoring with non-HFT hard filters.

Dimension scores (0-10, higher is always better) come from the LLM layer;
this module owns the weights, the hard filters, and the final 0-100
priority score. Hard filters are code, not prompts — they cannot be
bypassed by a permissive model.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from research_intel.extraction.schemas import NON_APPLICABLE_HFT
from research_intel.extraction.validators import validate_dimension_scores
from research_intel.llm.base import LLMClient
from research_intel.storage import repositories as repo
from research_intel.storage.models import Score, StrategyHypothesis

logger = logging.getLogger(__name__)

# Weights sum to 1.0. Practical testability dominates; see docs/05_scoring_framework.md.
WEIGHTS: dict[str, float] = {
    "crypto_relevance": 0.11,
    "non_hft_compatibility": 0.11,
    "data_availability": 0.11,
    "backtest_feasibility": 0.11,
    "signal_clarity": 0.09,
    "expected_robustness": 0.07,
    "novelty": 0.05,
    "implementation_complexity": 0.06,
    "overfitting_risk": 0.07,
    "transaction_cost_sensitivity": 0.05,
    "portfolio_diversification_value": 0.04,
    "expected_edge_decay_risk": 0.05,
    "source_evidence_quality": 0.08,
}

# Hard-filter thresholds (0-10 scale).
MIN_DATA_AVAILABILITY = 3.0
MIN_SIGNAL_CLARITY = 3.0
MIN_BACKTEST_FEASIBILITY = 3.0

# Soft penalty: abstract-only sources with no usable parameterization are
# demoted (not excluded) — they may still be worth manual review.
SOFT_PENALTY_EVIDENCE_MAX = 3.0
SOFT_PENALTY_FACTOR = 0.5
SOFT_PENALTY_FLAG = "soft_penalty:abstract_only_without_parameters"


@dataclass(frozen=True)
class ScoringResult:
    dimensions: dict[str, float]
    weighted_total: float  # 0-100
    excluded: bool
    exclusion_reason: str | None
    hard_filter_flags: list[str]


def weighted_total(dimensions: dict[str, float]) -> float:
    """Weighted 0-10 average scaled to 0-100."""
    total = sum(dimensions[name] * weight for name, weight in WEIGHTS.items())
    return round(total * 10, 1)


def apply_hard_filters(
    hypothesis_payload: dict, dimensions: dict[str, float]
) -> tuple[bool, str | None, list[str]]:
    """Returns (excluded, reason, flags). Any flag excludes the candidate.

    There is deliberately NO adaptation escape hatch here: if the hypothesis
    itself still depends on latency edge, it is excluded regardless of any
    `non_hft_adaptation` text. A genuinely adapted idea must instead set
    hft_or_low_latency_dependency=false and document the adaptation via
    original_source_has_latency_dependency / adapted_to_non_hft /
    adaptation_validity.
    """
    flags: list[str] = []
    if hypothesis_payload.get("hft_or_low_latency_dependency"):
        flags.append(NON_APPLICABLE_HFT)
    if hypothesis_payload.get("adaptation_validity") in ("weak", "invalid"):
        flags.append("weak_or_invalid_non_hft_adaptation")
    if hypothesis_payload.get("archetype_fidelity") in ("weak", "broken"):
        flags.append(
            "archetype_fidelity_failure:"
            + ",".join(hypothesis_payload.get("dropped_alpha_triggers", []) or ["unknown"])
        )
    if hypothesis_payload.get("entry_condition_fidelity") in ("weak", "broken"):
        flags.append("entry_condition_fidelity_failure")
    if hypothesis_payload.get("spec_consistency") in ("weak", "broken"):
        flags.append("spec_consistency_failure")
    if dimensions["data_availability"] < MIN_DATA_AVAILABILITY:
        flags.append("required_data_unavailable_or_unrealistic")
    if dimensions["signal_clarity"] < MIN_SIGNAL_CLARITY:
        flags.append("strategy_logic_too_vague")
    if dimensions["backtest_feasibility"] < MIN_BACKTEST_FEASIBILITY:
        flags.append("not_falsifiable_with_clear_backtest")
    excluded = bool(flags)
    return excluded, (flags[0] if flags else None), flags


def apply_soft_penalties(
    hypothesis_payload: dict, dimensions: dict[str, float], total: float
) -> tuple[float, list[str]]:
    """Demote (without excluding) abstract-only ideas lacking parameters."""
    flags: list[str] = []
    if (
        hypothesis_payload.get("parameter_source_quality") == "missing"
        and dimensions["source_evidence_quality"] <= SOFT_PENALTY_EVIDENCE_MAX
    ):
        total = round(total * SOFT_PENALTY_FACTOR, 1)
        flags.append(SOFT_PENALTY_FLAG)
    return total, flags


def score_one(session: Session, hypothesis: StrategyHypothesis, llm: LLMClient) -> Score:
    raw = llm.score_hypothesis(hypothesis.payload)
    dimensions = validate_dimension_scores(raw.get("dimensions", {}))
    excluded, reason, flags = apply_hard_filters(hypothesis.payload, dimensions)
    total = weighted_total(dimensions)
    total, soft_flags = apply_soft_penalties(hypothesis.payload, dimensions, total)
    flags = flags + soft_flags
    if excluded:
        logger.warning("hypothesis %s excluded: %s", hypothesis.hypothesis_id, reason)
    elif soft_flags:
        logger.info("hypothesis %s soft-penalized: %s", hypothesis.hypothesis_id, soft_flags)
    score = repo.add_score(
        session, hypothesis,
        dimensions=dimensions, weighted_total=total,
        excluded=excluded, exclusion_reason=reason, hard_filter_flags=flags,
    )
    return score


def score_all(session: Session, llm: LLMClient, rescore: bool = False) -> list[Score]:
    targets = (
        repo.list_hypotheses(session) if rescore else repo.unscored_hypotheses(session)
    )
    scores: list[Score] = []
    for hyp in targets:
        try:
            scores.append(score_one(session, hyp, llm))
        except Exception as exc:
            logger.error("scoring failed for %s: %s", hyp.hypothesis_id, exc)
            repo.add_rejection(
                session, stage="scoring", entity_type="hypothesis",
                entity_ref=hyp.hypothesis_id, reason=str(exc),
            )
    return scores
