"""Validation helpers for LLM outputs before they enter the database.

Includes rule-shape validation: a hypothesis whose entry/exit/risk rules are
only generic prose ("enter when the signal is strong") is rejected, even if
every schema field is technically populated.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import ValidationError

from research_intel.extraction.schemas import (
    SCORING_DIMENSIONS,
    ExtractionRecord,
    HypothesisRecord,
)

logger = logging.getLogger(__name__)


class ExtractionValidationError(ValueError):
    """LLM output did not conform to the extraction/hypothesis contract."""


# ---------------------------------------------------------------- rule shapes

# A measurable signal: a finance quantity or a snake_case feature identifier.
SIGNAL_RE = re.compile(
    r"return|ret_\w+|volatil|rv_\w+|vol_ratio|z.?score|imbalance|funding|spread|volume"
    r"|ratio|atr\b|atr_\w+|trend_strength|momentum|price|basis|liquidation|vwap"
    r"|cointegrat|inventory|drawdown|correlation|percentile|premium",
    re.IGNORECASE,
)
COMPARATOR_RE = re.compile(
    r"[<>]=?|crosses|exceed\w*|above|below|greater than|less than|falls under|rises over",
    re.IGNORECASE,
)
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
# Named parameter reference such as entry_threshold or {trend_strength_entry}.
PARAM_REF_RE = re.compile(r"\b\w+_(?:threshold|entry|exit|lookback|window|mult|limit|target)\b")
TIMEFRAME_RE = re.compile(
    r"\d+\s*[- ]?(?:m\b|min\b|minute|h\b|hour|d\b|day|bar|week)|rolling|lookback|window",
    re.IGNORECASE,
)
TIME_STOP_RE = re.compile(r"time[- ]stop|after \d+\s*[- ]?(?:bar|minute|hour|day)", re.IGNORECASE)
STOP_LOSS_RE = re.compile(r"stop[- ]?loss|stop[- ]?out|hard stop|stopped? at", re.IGNORECASE)
TAKE_PROFIT_RE = re.compile(r"take[- ]?profit|profit target", re.IGNORECASE)
REGIME_RE = re.compile(r"regime (?:switch|transition|change)", re.IGNORECASE)
RISK_RE = re.compile(
    r"\d+(?:\.\d+)?\s?%|max(?:imum)? position|position size|position risk|volatility target"
    r"|vol[- ]target|drawdown|leverage|capital allocation|inventory (?:limit|cap)|exposure (?:cap|limit)",
    re.IGNORECASE,
)


def _entry_rule_is_concrete(rule: str) -> bool:
    """Measurable signal + comparator + threshold/parameter + timeframe reference."""
    has_threshold = bool(NUMBER_RE.search(rule)) or bool(PARAM_REF_RE.search(rule))
    return bool(
        SIGNAL_RE.search(rule)
        and COMPARATOR_RE.search(rule)
        and has_threshold
        and TIMEFRAME_RE.search(rule)
    )


def _exit_rule_is_concrete(rule: str) -> bool:
    """Explicit threshold, time stop, stop-loss, take-profit, or regime transition."""
    has_threshold = bool(COMPARATOR_RE.search(rule)) and bool(NUMBER_RE.search(rule))
    return bool(
        has_threshold
        or TIME_STOP_RE.search(rule)
        or STOP_LOSS_RE.search(rule)
        or TAKE_PROFIT_RE.search(rule)
        or REGIME_RE.search(rule)
    )


def _risk_rule_is_concrete(rule: str) -> bool:
    """Size limit, stop-loss, vol target, drawdown rule, or leverage/allocation limit."""
    return bool(RISK_RE.search(rule) or STOP_LOSS_RE.search(rule))


def validate_rule_shapes(record: HypothesisRecord) -> None:
    """Reject hypotheses whose strategy logic is generic prose."""
    problems: list[str] = []
    if not any(_entry_rule_is_concrete(r) for r in record.entry_rules):
        problems.append(
            "no concrete entry rule (need signal + comparator + threshold + timeframe)"
        )
    if not any(_exit_rule_is_concrete(r) for r in record.exit_rules):
        problems.append(
            "no concrete exit rule (need threshold, time stop, stop-loss, "
            "take-profit, or regime transition)"
        )
    if not any(_risk_rule_is_concrete(r) for r in record.risk_rules):
        problems.append(
            "no concrete risk rule (need size limit, stop-loss, vol target, "
            "drawdown rule, or leverage limit)"
        )
    if problems:
        raise ExtractionValidationError(
            f"hypothesis {record.hypothesis_id} failed rule-shape validation: "
            + "; ".join(problems)
        )


def validate_extraction(payload: dict[str, Any]) -> ExtractionRecord:
    try:
        return ExtractionRecord.model_validate(payload)
    except ValidationError as exc:
        raise ExtractionValidationError(f"invalid extraction payload: {exc}") from exc


def validate_hypothesis(payload: dict[str, Any]) -> HypothesisRecord:
    try:
        record = HypothesisRecord.model_validate(payload)
    except ValidationError as exc:
        raise ExtractionValidationError(f"invalid hypothesis payload: {exc}") from exc
    if not record.entry_rules or not record.exit_rules:
        raise ExtractionValidationError(
            f"hypothesis {record.hypothesis_id} has no entry or exit rules; "
            "vague strategy logic is not allowed"
        )
    # Rule-shape validation gates export-eligible hypotheses. review_only /
    # rejected hypotheses (candidate_export_allowed=false) carry explanatory
    # placeholder rules instead of codable rules and can never be exported,
    # so shape validation does not apply to them.
    if record.candidate_export_allowed:
        validate_rule_shapes(record)
    return record


def validate_dimension_scores(dimensions: dict[str, Any]) -> dict[str, float]:
    """Ensure every scoring dimension is present and within 0-10."""
    missing = set(SCORING_DIMENSIONS) - set(dimensions)
    if missing:
        raise ExtractionValidationError(f"missing scoring dimensions: {sorted(missing)}")
    clean: dict[str, float] = {}
    for name in SCORING_DIMENSIONS:
        value = float(dimensions[name])
        if not 0.0 <= value <= 10.0:
            raise ExtractionValidationError(f"dimension {name}={value} out of range 0-10")
        clean[name] = value
    return clean
