"""Convert extractions into crypto-testable strategy hypotheses.

Includes the source grounding gate: a vague/abstract-only source with no
usable parameterization must not become an exportable template strategy,
regardless of what the LLM returns. The gate is code, not prompts.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from research_intel.extraction.schemas import (
    HYPOTHESIS_STATUSES,
    NON_APPLICABLE_HFT,
    HypothesisRecord,
)
from research_intel.extraction.validators import validate_hypothesis
from research_intel.llm.base import LLMClient
from research_intel.storage import repositories as repo
from research_intel.storage.models import Extraction, StrategyHypothesis

logger = logging.getLogger(__name__)

GENERIC_LOGIC_MARKERS = ("review", "not specified", "unspecified", "n/a", "unknown")


def _logic_is_generic(text: str) -> bool:
    lowered = text.strip().lower()
    return not lowered or any(m in lowered for m in GENERIC_LOGIC_MARKERS)


def grounding_gate_status(extraction: dict[str, Any], record: HypothesisRecord) -> str:
    """Deterministic source grounding gate. Returns the enforced status.

    Precedence: rejected_hft > rejected_unbacktestable > review_only > candidate.
    """
    if record.hft_or_low_latency_dependency or record.adaptation_validity == "invalid":
        return "rejected_hft"

    param_quality = extraction.get("parameter_source_quality", "missing")
    backtestability = extraction.get("backtestability", "medium")
    rule_quality = extraction.get("source_rule_quality", "missing")
    evidence_type = extraction.get("source_evidence_type", "unknown")
    no_params = not extraction.get("extracted_parameters")

    if record.parameterization_status == "unparameterized":
        return "rejected_unbacktestable"
    if param_quality == "missing" and backtestability == "not_backtestable":
        return "rejected_unbacktestable"
    if param_quality == "missing" and backtestability == "low":
        return "review_only"
    if no_params and (
        rule_quality in ("vague", "missing")
        or (_logic_is_generic(extraction.get("entry_logic", ""))
            and _logic_is_generic(extraction.get("exit_logic", "")))
    ):
        return "review_only"
    if evidence_type in ("abstract_only", "blog_or_report") and no_params:
        return "review_only"
    if record.parameterization_status == "default_parameterized":
        return "review_only"
    if record.status in HYPOTHESIS_STATUSES:
        return record.status
    return "candidate"


def generate_for_extraction(
    session: Session, extraction: Extraction, llm: LLMClient
) -> StrategyHypothesis | None:
    """Generate, validate, and store one hypothesis for an extraction.

    HFT-dependent ideas without a non-HFT adaptation are stored with status
    'rejected_hft' so they remain queryable but never reach candidate exports.
    Returns None when generation/validation fails (failure is recorded).
    """
    payload = llm.generate_hypothesis(extraction.payload)
    payload.setdefault("source_ids", [str(extraction.source_id)])
    try:
        record = validate_hypothesis(payload)
    except Exception as exc:
        logger.error("hypothesis validation failed for extraction %s: %s", extraction.id, exc)
        repo.add_rejection(
            session, stage="hypothesis", entity_type="extraction",
            entity_ref=str(extraction.id), reason=str(exc),
        )
        return None

    return admit_hypothesis(session, extraction, record)


def admit_hypothesis(
    session: Session, extraction: Extraction, record: HypothesisRecord
) -> StrategyHypothesis | None:
    """Run every gate on a validated hypothesis record and store it.

    Shared by LLM generation and External Agent Mode imports — external
    outputs pass through exactly the same enforcement.
    """
    if repo.get_hypothesis(session, record.hypothesis_id) is not None:
        # A collision on the (source, document, archetype)-derived id across
        # different extractions is an error, never a silent skip (v0.2 P6).
        reason = (
            f"hypothesis_id_collision: {record.hypothesis_id} already exists; "
            f"extraction {extraction.id} produced no hypothesis"
        )
        logger.error(reason)
        repo.add_rejection(
            session, stage="hypothesis", entity_type="extraction",
            entity_ref=str(extraction.id), reason=reason,
        )
        return None

    status = grounding_gate_status(extraction.payload, record)
    # A "candidate" whose own export flags are false is inconsistent; demote.
    if status == "candidate" and not (
        record.candidate_export_allowed and record.backtest_spec_export_allowed
    ):
        status = "review_only"

    final = record.model_dump()

    # Archetype fidelity gate (v0.2 P3): recompute in code — never trust the
    # LLM's self-assessment — and demote weak/broken fidelity.
    from research_intel.hypotheses.fidelity import assess_fidelity

    fid = assess_fidelity(
        extraction.payload, record.entry_rules, record.generated_archetype
    )
    final.update(fid)
    if status == "candidate" and fid["archetype_fidelity"] in ("weak", "broken"):
        status = "review_only"
        final.setdefault("missing_for_backtest", []).append(
            "entry rules dropped source alpha trigger(s): "
            + ", ".join(fid["dropped_alpha_triggers"])
        )
        logger.warning(
            "hypothesis %s demoted: archetype fidelity %s (dropped: %s)",
            record.hypothesis_id, fid["archetype_fidelity"], fid["dropped_alpha_triggers"],
        )

    # Entry-condition fidelity gate (v0.2.1 P4): recomputed in code.
    from research_intel.hypotheses.fidelity import assess_entry_conditions

    cond = assess_entry_conditions(extraction.payload, record.entry_rules)
    final.update(cond)
    if status == "candidate" and cond["entry_condition_fidelity"] in ("weak", "broken"):
        status = "review_only"
        final.setdefault("missing_for_backtest", []).append(
            "entry rules dropped source entry condition(s): "
            + "; ".join(cond["dropped_entry_conditions"])
        )
        logger.warning(
            "hypothesis %s demoted: entry-condition fidelity %s (dropped: %s)",
            record.hypothesis_id, cond["entry_condition_fidelity"],
            cond["dropped_entry_conditions"],
        )

    # Source fact fidelity gate (v0.2 P4): source risk/cost facts must not be
    # dropped from an exported candidate.
    if status == "candidate":
        dropped_facts = [
            k for k in (extraction.payload.get("source_risk_parameters") or {})
            if k not in (final.get("generated_risk_parameters") or {})
        ] + [
            k for k in (extraction.payload.get("source_cost_parameters") or {})
            if k not in (final.get("generated_cost_parameters") or {})
        ]
        if dropped_facts:
            status = "review_only"
            final.setdefault("missing_for_backtest", []).append(
                "source risk/cost facts dropped: " + ", ".join(dropped_facts)
            )
            logger.warning(
                "hypothesis %s demoted: source facts dropped: %s",
                record.hypothesis_id, dropped_facts,
            )

    # Spec consistency gate (v0.2.1 P1): the executable sections must not
    # contradict the preserved source facts. Recomputed in code on the final
    # payload — never trusted from the LLM.
    from research_intel.hypotheses.spec_consistency import validate_spec_consistency

    consistency = validate_spec_consistency(final)
    final.update(consistency)
    if status == "candidate" and consistency["spec_consistency"] in ("weak", "broken"):
        status = "review_only"
        final.setdefault("missing_for_backtest", []).append(
            "spec consistency failures: " + "; ".join(consistency["consistency_failures"])
        )
        logger.warning(
            "hypothesis %s demoted: spec consistency %s (%s)",
            record.hypothesis_id, consistency["spec_consistency"],
            consistency["consistency_failures"],
        )

    final["status"] = status
    if status != "candidate":
        final["candidate_export_allowed"] = False
        final["backtest_spec_export_allowed"] = False
        reason = (
            NON_APPLICABLE_HFT if status == "rejected_hft"
            else f"{status}: source lacks concrete parameters/rules for a falsifiable backtest"
        )
        if status.startswith("rejected"):
            repo.add_rejection(
                session, stage="hypothesis", entity_type="hypothesis",
                entity_ref=record.hypothesis_id, reason=reason,
            )
        logger.warning("hypothesis %s gated: %s", record.hypothesis_id, reason)
    hyp = repo.add_hypothesis(session, extraction, final, status=status)
    logger.info("generated hypothesis %s (%s)", record.hypothesis_id, status)
    return hyp


def generate_pending(
    session: Session, llm: LLMClient, limit: int | None = None
) -> list[StrategyHypothesis]:
    generated: list[StrategyHypothesis] = []
    for extraction in repo.extractions_without_hypothesis(session, limit=limit):
        hyp = generate_for_extraction(session, extraction, llm)
        if hyp is not None:
            generated.append(hyp)
    return generated
