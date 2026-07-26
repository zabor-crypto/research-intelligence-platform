"""Archetype fidelity check (v0.2 P3).

Batch v1 exported a liquidation-reversal source as a generic z-score fade —
an executable spec that tested the wrong strategy. This module derives the
source's archetype from the extraction, checks that the generated entry rules
preserve the archetype's core alpha triggers, and grades fidelity. The
generator enforces the result in code: weak/broken fidelity can never reach
candidate exports.
"""

from __future__ import annotations

import re
from typing import Any

ALLOWED_ARCHETYPES = (
    "volatility_regime_momentum",
    "funding_rate_mean_reversion",
    "liquidation_reversal",
    "cross_sectional_momentum",
    "statistical_arbitrage_pairs",
    "order_flow_imbalance",
    "basis_carry",
    "non_hft_market_making",
    "generic_signal",
    "unknown",
)

# Style -> archetype (before data-driven overrides).
STYLE_TO_ARCHETYPE = {
    "volatility_regime": "volatility_regime_momentum",
    "momentum": "volatility_regime_momentum",
    "carry_basis": "basis_carry",
    "event_driven": "generic_signal",
    "flow_imbalance": "order_flow_imbalance",
    "statistical_arbitrage": "statistical_arbitrage_pairs",
    "cross_sectional": "cross_sectional_momentum",
    "market_making": "non_hft_market_making",
    "mean_reversion": "generic_signal",
    "portfolio_risk": "generic_signal",
    "generic": "generic_signal",
}

# Per-archetype core alpha triggers: every group must be represented in the
# generated entry rules by at least one of its alternative terms.
ARCHETYPE_TRIGGERS: dict[str, list[tuple[str, ...]]] = {
    "liquidation_reversal": [
        ("liquidation", "forced selling", "forced-selling", "cascade"),
    ],
    "funding_rate_mean_reversion": [("funding",)],
    "volatility_regime_momentum": [
        ("volatility", "vol_ratio", "rv_", "vol regime", "volatility regime"),
        ("momentum", "trend", "ret_", "return"),
    ],
    "order_flow_imbalance": [("imbalance", "order flow", "signed_volume", "signed volume")],
    "basis_carry": [("basis", "funding", "carry", "premium")],
}


def derive_source_archetype(extraction: dict[str, Any]) -> str:
    """Data-aware archetype derivation from the extraction."""
    style = extraction.get("strategy_style", "generic")
    data = set(extraction.get("data_requirements", []))
    text = " ".join([
        extraction.get("title", ""), extraction.get("signal_description", ""),
        extraction.get("alpha_mechanism", ""),
    ]).lower()

    # Distinctive data feeds override keyword-style routing.
    if "liquidations" in data or "liquidation" in text or "forced selling" in text:
        return "liquidation_reversal"
    if style == "carry_basis":
        return (
            "funding_rate_mean_reversion"
            if "funding_rates" in data or "funding" in text else "basis_carry"
        )
    return STYLE_TO_ARCHETYPE.get(style, "unknown")


def _condition_preserved(condition: str, rules_text: str) -> bool:
    """A source entry condition survives if its numbers all appear (with
    number boundaries), or — for number-free conditions — if at least half of
    its distinctive keywords appear."""
    numbers = re.findall(r"\d+(?:\.\d+)?", condition)
    if numbers:
        return all(
            re.search(rf"(?<![\d.]){re.escape(n)}(?![\d.])", rules_text) for n in numbers
        )
    keywords = [w for w in re.findall(r"[a-z_]{5,}", condition.lower())]
    if not keywords:
        return False
    hits = sum(1 for w in keywords if w in rules_text)
    return hits / len(keywords) >= 0.5


def assess_entry_conditions(
    extraction: dict[str, Any], entry_rules: list[str]
) -> dict[str, Any]:
    """Condition-level fidelity (v0.2.1 P4): every source entry condition must
    survive into the generated rules or the drop is graded and gated.

    Grading: all preserved (or none stated) -> strong; exactly one dropped ->
    partial (candidate may stay, capped at grade B); more than one dropped ->
    weak; all dropped -> broken. weak/broken are hard-gated by the generator.
    """
    conditions = list(extraction.get("source_entry_conditions", []) or [])
    rules_text = " ".join(entry_rules).lower()
    preserved = [c for c in conditions if _condition_preserved(c, rules_text)]
    dropped = [c for c in conditions if c not in preserved]

    if not conditions or not dropped:
        fidelity = "strong"
    elif len(dropped) == 1:
        fidelity = "partial"
    elif preserved:
        fidelity = "weak"
    else:
        fidelity = "broken"

    return {
        "source_entry_conditions": conditions,
        "generated_entry_conditions": list(entry_rules),
        "preserved_entry_conditions": preserved,
        "dropped_entry_conditions": dropped,
        "entry_condition_fidelity": fidelity,
    }


def assess_fidelity(
    extraction: dict[str, Any],
    entry_rules: list[str],
    generated_archetype: str,
) -> dict[str, Any]:
    """Check that generated entry rules preserve the source's alpha triggers.

    Returns the P3 schema fields. Grading: all trigger groups preserved ->
    strong; some missing -> weak; all missing -> broken; archetype without
    trigger requirements -> strong (nothing to preserve).
    """
    source_archetype = derive_source_archetype(extraction)
    groups = ARCHETYPE_TRIGGERS.get(source_archetype, [])
    rules_text = " ".join(entry_rules).lower()

    core = [group[0] for group in groups]
    preserved: list[str] = []
    dropped: list[str] = []
    for group in groups:
        if any(term in rules_text for term in group):
            preserved.append(group[0])
        else:
            dropped.append(group[0])

    if not groups:
        fidelity = "strong"
    elif not dropped:
        fidelity = "strong"
    elif preserved:
        fidelity = "weak"
    else:
        fidelity = "broken"

    return {
        "source_archetype": source_archetype,
        "generated_archetype": generated_archetype
        if generated_archetype in ALLOWED_ARCHETYPES else "unknown",
        "core_alpha_triggers": core,
        "preserved_alpha_triggers": preserved,
        "dropped_alpha_triggers": dropped,
        "archetype_fidelity": fidelity,
    }
