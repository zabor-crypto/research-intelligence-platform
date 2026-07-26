"""Parameter alias normalization (v0.2 P5).

Batch v1 dropped correctly extracted values to defaults because parameter
names were rigid (a funding percentile captured as ``trend_strength_entry``
never reached the carry template). This module maps raw extracted parameter
names onto canonical per-archetype names, preserving raw keys, confidence,
and provenance. Nothing is silently dropped: values that cannot be mapped
land in ``unmapped`` and are surfaced in the backtest spec.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MappedParameter(BaseModel):
    raw_key: str
    canonical_key: str
    raw_value: Any
    value: Any
    confidence: float
    provenance: str = "source"


class NormalizedParameters(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)  # canonical -> value
    details: list[MappedParameter] = Field(default_factory=list)
    unmapped: dict[str, Any] = Field(default_factory=dict)  # raw_key -> value


# Aliases that hold regardless of archetype: raw name -> (canonical, confidence).
GLOBAL_ALIASES: dict[str, tuple[str, float]] = {
    "max_hold_minutes": ("time_stop_minutes", 0.95),
    "holding_period_limit": ("time_stop_minutes", 0.8),
    "time_exit": ("time_stop_minutes", 0.8),
    "max_bars_in_trade": ("time_stop_bars", 0.9),
    "funding_percentile_threshold": ("funding_entry_percentile", 0.95),
    "funding_rate_percentile": ("funding_entry_percentile", 0.9),
    "funding_extreme_percentile": ("funding_entry_percentile", 0.9),
    "carry_percentile": ("funding_entry_percentile", 0.8),
}

# Per-archetype overrides: raw name -> (canonical, confidence). These encode
# "a generic threshold extracted from a funding source is a funding
# percentile, not a trend-strength threshold".
ARCHETYPE_ALIASES: dict[str, dict[str, tuple[str, float]]] = {
    "funding_rate_mean_reversion": {
        "trend_strength_entry": ("funding_entry_percentile", 0.7),
        "trend_strength_exit": ("funding_exit_percentile", 0.7),
        "lookback_days": ("funding_lookback_days", 0.9),
    },
    "basis_carry": {
        "trend_strength_entry": ("funding_entry_percentile", 0.6),
        "trend_strength_exit": ("funding_exit_percentile", 0.6),
        "lookback_days": ("funding_lookback_days", 0.9),
    },
    "liquidation_reversal": {
        "trend_strength_entry": ("volume_spike_mult", 0.6),
        "lookback_days": ("baseline_window_days", 0.7),
    },
    "statistical_arbitrage_pairs": {
        "lookback_days": ("coint_window_days", 0.85),
        "trend_strength_entry": ("entry_zscore", 0.6),
        "trend_strength_exit": ("exit_zscore", 0.6),
    },
    "cross_sectional_momentum": {
        "lookback_days": ("rank_lookback_days", 0.85),
    },
    "generic_signal": {
        "lookback_days": ("signal_lookback_days", 0.7),
    },
}

PERCENTILE_SUFFIX = "_percentile"


def _scale_for(canonical: str, value: Any) -> Any:
    """Fractional percentiles (0.9) become percent form (90)."""
    if (
        canonical.endswith(PERCENTILE_SUFFIX)
        and isinstance(value, int | float)
        and 0 < value <= 1
    ):
        scaled = value * 100
        return int(scaled) if float(scaled).is_integer() else scaled
    return value


def normalize_strategy_parameters(
    raw_params: dict[str, Any],
    strategy_archetype: str,
    template_params: dict[str, Any] | None = None,
) -> NormalizedParameters:
    """Map raw extracted parameters to canonical names for the archetype.

    When ``template_params`` is given, only canonical names that exist in the
    template are treated as mapped; everything else is preserved in
    ``unmapped`` so it can be surfaced in the backtest spec instead of being
    silently replaced by defaults.
    """
    archetype_aliases = ARCHETYPE_ALIASES.get(strategy_archetype, {})
    result = NormalizedParameters()
    for raw_key, raw_value in raw_params.items():
        if raw_key in archetype_aliases:
            canonical, confidence = archetype_aliases[raw_key]
        elif raw_key in GLOBAL_ALIASES:
            canonical, confidence = GLOBAL_ALIASES[raw_key]
        else:
            canonical, confidence = raw_key, 1.0
        if template_params is not None and canonical not in template_params:
            result.unmapped[raw_key] = raw_value
            continue
        value = _scale_for(canonical, raw_value)
        result.parameters[canonical] = value
        result.details.append(
            MappedParameter(
                raw_key=raw_key, canonical_key=canonical,
                raw_value=raw_value, value=value, confidence=confidence,
            )
        )
    return result
